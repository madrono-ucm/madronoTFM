"""Invocación headless de `claude` para implementar una tarea, y detección de fallos reintentables."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import tasks_store

RATE_LIMIT_KEYWORDS = (
    "usage limit",
    "rate limit",
    "quota",
    "overloaded",
    "429",
    "limit reached",
)

# Tope de caracteres del contexto acumulado (doc/*.md) inyectado en cada prompt, para
# que el coste por tarea no crezca sin límite a medida que el proyecto avanza.
MAX_CONTEXT_CHARS = 40_000

INFRA_APPLY_FORBIDDEN = """\
- NO ejecutes comandos con efectos reales fuera de este worktree ni con coste
  económico o difíciles de revertir (`terraform apply`/`destroy`, `aws ... create/
  delete/deploy`, llamadas a APIs de pago, etc.). Si la tarea implica infraestructura,
  deja el código (Terraform, scripts...) escrito y listo, pero sin aplicarlo — eso lo
  decide un humano tras revisar el PR."""

INFRA_APPLY_ALLOWED = """\
- EXCEPCIÓN explícita para esta tarea concreta (`allow_infra_apply: true` en su
  front-matter): SÍ puedes ejecutar comandos `aws`/`terraform` con efectos reales
  (crear recursos, `terraform apply`...), pero ÚNICAMENTE los que el prompt de esta
  tarea describe explícitamente — no soluciones espontáneas, no incluye
  `terraform destroy` ni borrar/recrear nada salvo que el prompt lo pida
  explícitamente. Este permiso NO se extiende a ninguna otra tarea ni a esta misma en
  un reintento con un alcance distinto al descrito. Deja constancia detallada en
  `doc/{doc_filename}` de exactamente qué se creó/aplicó en AWS (recursos, nombres,
  región) para que quede como referencia auditable."""

SYSTEM_PROMPT_ADDENDUM_TEMPLATE = """\
Estás operando de forma autónoma en un pipeline sin supervisión humana en tiempo real,
dentro de un git worktree aislado en la rama "{branch}" (creada desde {base_branch}).
- Implementa completamente la tarea del prompt de usuario.
- Haz commit de tus cambios (uno o varios, con mensajes claros). NO ejecutes `git push`
  ni `gh pr create` bajo ninguna circunstancia: un orquestador externo se encarga de eso
  después de que termines.
{infra_apply_policy}
- Esta EC2 tiene disco muy limitado (unos pocos GB libres, compartidos con el propio
  pipeline). NO escribas ni dejes programado (cron, systemd timer, bucles
  `--interval`/`--daemon`, etc.) nada que escriba datos de forma continua o sin
  acotar en el disco local — ni durante la tarea ni como resultado de ella. Si la
  tarea es un productor/captura de datos: una muestra pequeña y de tamaño acotado
  (unos pocos registros) commiteada como fixture es correcto; un bucle que aterriza
  lotes sin parar en disco local no lo es. El destino final de datos en volumen
  (S3, base de datos...) llega con la infraestructura correspondiente, no antes.
- Además del código, crea (o actualiza) el archivo `doc/{doc_filename}` como parte de
  tus commits: un resumen breve en markdown de qué implementaste, por qué, y cualquier
  decisión relevante para tareas futuras. Este archivo se revisa junto con el resto del
  PR y pasa a formar parte del contexto acumulado del proyecto que verán las próximas
  tareas (sesiones nuevas, sin memoria de esta) — sé conciso y concreto, no reescribas
  el código, solo resume qué cambió y por qué.
- No hay ningún humano para pedir confirmación; ante ambigüedad, toma la decisión más
  razonable y documenta el porqué en el mensaje de commit y en el resumen de doc/.
- Al terminar, deja el worktree limpio (sin cambios sin commitear).
"""


@dataclass
class ClaudeResult:
    ok: bool
    is_retryable: bool
    made_commits: bool
    error_snippet: str | None
    total_cost_usd: float | None


def _load_accumulated_context(worktree_dir: Path) -> str:
    """Concatena doc/*.md ya mergeados en main (resúmenes de tareas anteriores)."""
    doc_dir = worktree_dir / "doc"
    if not doc_dir.is_dir():
        return ""

    paths = sorted(p for p in doc_dir.glob("*.md") if p.name != "README.md")
    if not paths:
        return ""

    sections = [f"### {p.name}\n\n{p.read_text(encoding='utf-8').strip()}" for p in paths]
    combined = "\n\n".join(sections)

    if len(combined) > MAX_CONTEXT_CHARS:
        combined = (
            "[...resúmenes más antiguos omitidos por tamaño, siguen disponibles en doc/...]\n\n"
            + combined[-MAX_CONTEXT_CHARS:]
        )

    return combined


def build_prompt(task, worktree_dir: Path) -> str:
    parts = [f"Tarea #{task.id}: {task.title}\n"]

    context = _load_accumulated_context(worktree_dir)
    if context:
        parts.append(
            "## Contexto acumulado del proyecto\n\n"
            "Resúmenes de tareas anteriores ya mergeadas en main (carpeta doc/), para "
            "que tengas continuidad aunque esta sea una sesión nueva sin memoria de "
            "ellas:\n\n"
            f"{context}\n"
        )
        parts.append("## Tarea a implementar\n")

    parts.append(task.body)
    return "\n".join(parts) + "\n"


def _looks_like_rate_limit(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in RATE_LIMIT_KEYWORDS)


def _has_new_commits(worktree_dir: Path, base_branch: str) -> bool:
    proc = subprocess.run(
        ["git", "rev-list", "--count", f"{base_branch}..HEAD"],
        cwd=worktree_dir,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False
    return proc.stdout.strip() not in ("", "0")


def _parse_json_output(stdout: str) -> tuple[bool | None, str | None, float | None]:
    if not stdout:
        return None, None, None
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None, None, None
    return bool(data.get("is_error")), data.get("result"), data.get("total_cost_usd")


def invoke_claude(task, worktree_dir: Path, config) -> ClaudeResult:
    doc_filename = tasks_store.doc_filename_for(task)
    infra_apply_policy = (
        INFRA_APPLY_ALLOWED.format(doc_filename=doc_filename)
        if task.allow_infra_apply
        else INFRA_APPLY_FORBIDDEN
    )
    system_prompt_addendum = SYSTEM_PROMPT_ADDENDUM_TEMPLATE.format(
        branch=task.branch,
        base_branch=config.git_base_branch,
        doc_filename=doc_filename,
        infra_apply_policy=infra_apply_policy,
    )

    cmd = [
        config.claude_bin,
        "-p",
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--model", config.claude_model,
        "--max-budget-usd", str(config.claude_max_budget_usd),
        "--add-dir", str(worktree_dir),
        "--no-session-persistence",
        "--append-system-prompt", system_prompt_addendum,
    ]
    if config.claude_fallback_model:
        cmd += ["--fallback-model", config.claude_fallback_model]

    prompt = build_prompt(task, worktree_dir)

    try:
        proc = subprocess.run(
            cmd,
            cwd=worktree_dir,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=config.claude_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        combined = (exc.stdout or "") + (exc.stderr or "")
        return ClaudeResult(
            ok=False,
            is_retryable=True,
            made_commits=_has_new_commits(worktree_dir, config.git_base_branch),
            error_snippet=f"timeout tras {config.claude_timeout_seconds}s: {combined[-500:]}",
            total_cost_usd=None,
        )

    made_commits = _has_new_commits(worktree_dir, config.git_base_branch)
    combined_output = (proc.stdout or "") + (proc.stderr or "")
    is_error, result_text, total_cost = _parse_json_output(proc.stdout)
    if is_error is None:
        # Salida no parseable como JSON: cae a la heurística sobre el código de salida.
        is_error = proc.returncode != 0

    if proc.returncode == 0 and not is_error:
        return ClaudeResult(
            ok=True, is_retryable=False, made_commits=made_commits,
            error_snippet=None, total_cost_usd=total_cost,
        )

    error_snippet = (result_text or combined_output)[-500:]
    retryable = _looks_like_rate_limit(combined_output + (result_text or ""))
    return ClaudeResult(
        ok=False, is_retryable=retryable, made_commits=made_commits,
        error_snippet=error_snippet, total_cost_usd=total_cost,
    )
