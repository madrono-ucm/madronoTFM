"""Invocación headless de `claude` para implementar una tarea, y detección de fallos reintentables."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

RATE_LIMIT_KEYWORDS = (
    "usage limit",
    "rate limit",
    "quota",
    "overloaded",
    "429",
    "limit reached",
)

SYSTEM_PROMPT_ADDENDUM_TEMPLATE = """\
Estás operando de forma autónoma en un pipeline sin supervisión humana en tiempo real,
dentro de un git worktree aislado en la rama "{branch}" (creada desde {base_branch}).
- Implementa completamente la tarea del prompt de usuario.
- Haz commit de tus cambios (uno o varios, con mensajes claros). NO ejecutes `git push`
  ni `gh pr create` bajo ninguna circunstancia: un orquestador externo se encarga de eso
  después de que termines.
- No hay ningún humano para pedir confirmación; ante ambigüedad, toma la decisión más
  razonable y documenta el porqué en el mensaje de commit.
- Al terminar, deja el worktree limpio (sin cambios sin commitear).
"""


@dataclass
class ClaudeResult:
    ok: bool
    is_retryable: bool
    made_commits: bool
    error_snippet: str | None
    total_cost_usd: float | None


def build_prompt(task) -> str:
    return f"Tarea #{task.id}: {task.title}\n\n{task.body}\n"


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
    system_prompt_addendum = SYSTEM_PROMPT_ADDENDUM_TEMPLATE.format(
        branch=task.branch, base_branch=config.git_base_branch
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

    prompt = build_prompt(task)

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
