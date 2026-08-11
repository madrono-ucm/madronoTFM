"""Demonio 24/7: procesa las tareas de tasks/*.md una a una y en orden.

Bucle principal simple: en cada ciclo da un único paso de estado (process_once) y
duerme POLL_INTERVAL_SECONDS. Pensado para correr como servicio systemd
(Restart=always) sobre un clon dedicado del repo (ver tasks/scripts/config.example.env).
"""

from __future__ import annotations

import json
import logging
import os
import random
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import claude_runner
import gh_git
import tasks_store
from tasks_store import (
    STATUS_BLOCKED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_IN_REVIEW,
    Task,
)

log = logging.getLogger("madrono-agent")


@dataclass
class Config:
    repo_path: Path
    github_repo: str
    git_base_branch: str
    poll_interval_seconds: int
    backoff_base_seconds: int
    backoff_factor: float
    backoff_max_seconds: int
    backoff_jitter_pct: float
    claude_bin: str
    claude_model: str
    claude_fallback_model: str
    claude_max_budget_usd: float
    claude_timeout_seconds: int
    gh_bin: str
    gh_merge_method: str

    @property
    def tasks_dir(self) -> Path:
        return self.repo_path / "tasks"

    @property
    def worktrees_dir(self) -> Path:
        return self.repo_path / "tasks" / "scripts" / ".worktrees"

    @property
    def heartbeat_path(self) -> Path:
        return self.repo_path / "tasks" / "scripts" / ".state" / "health.json"


def load_config() -> Config:
    def env(name: str, default: str | None = None, required: bool = False) -> str:
        value = os.environ.get(name, default)
        if required and not value:
            raise RuntimeError(f"falta la variable de entorno {name}")
        return value or ""

    return Config(
        repo_path=Path(env("REPO_PATH", required=True)),
        github_repo=env("GITHUB_REPO", required=True),
        git_base_branch=env("GIT_BASE_BRANCH", "main"),
        poll_interval_seconds=int(env("POLL_INTERVAL_SECONDS", "60")),
        backoff_base_seconds=int(env("BACKOFF_BASE_SECONDS", "300")),
        backoff_factor=float(env("BACKOFF_FACTOR", "2")),
        backoff_max_seconds=int(env("BACKOFF_MAX_SECONDS", "14400")),
        backoff_jitter_pct=float(env("BACKOFF_JITTER_PCT", "0.2")),
        claude_bin=env("CLAUDE_BIN", "claude"),
        claude_model=env("CLAUDE_MODEL", "sonnet"),
        claude_fallback_model=env("CLAUDE_FALLBACK_MODEL", ""),
        claude_max_budget_usd=float(env("CLAUDE_MAX_BUDGET_USD", "3.00")),
        claude_timeout_seconds=int(env("CLAUDE_TIMEOUT_SECONDS", "5400")),
        gh_bin=env("GH_BIN", "gh"),
        gh_merge_method=env("GH_MERGE_METHOD", "squash"),
    )


def compute_backoff(config: Config, attempts: int) -> timedelta:
    delay = min(
        config.backoff_base_seconds * (config.backoff_factor ** max(attempts - 1, 0)),
        config.backoff_max_seconds,
    )
    jitter = delay * config.backoff_jitter_pct
    delay = delay + random.uniform(-jitter, jitter)
    return timedelta(seconds=max(delay, 0))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _sd_notify(message: str) -> None:
    """Notifica a systemd (READY=1, WATCHDOG=1...) sin depender de python-systemd."""
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    if addr[0] == "@":
        addr = "\0" + addr[1:]
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.connect(addr)
        sock.sendall(message.encode())
    except OSError:
        log.debug("no se pudo notificar a systemd (%s)", message)
    finally:
        sock.close()


def _watchdog_loop(interval_seconds: float) -> None:
    while True:
        _sd_notify("WATCHDOG=1")
        time.sleep(interval_seconds)


def _start_watchdog_thread() -> None:
    """Si la unit tiene WatchdogSec=, hace ping cada mitad de ese intervalo.

    Corre en un hilo aparte para que un ciclo largo (claude puede tardar hasta
    CLAUDE_TIMEOUT_SECONDS bloqueado en process_once) no dispare el watchdog: esto
    solo confirma que el intérprete de Python sigue vivo y planificando hilos, no que
    la tarea en curso haya terminado.
    """
    usec = os.environ.get("WATCHDOG_USEC")
    if not usec:
        return
    interval = max(int(usec) / 1_000_000 / 2, 1.0)
    threading.Thread(target=_watchdog_loop, args=(interval,), daemon=True).start()
    log.info("Watchdog systemd activo, ping cada %.0fs", interval)


def write_heartbeat(config: Config, status: str, ok: bool, error: str | None = None) -> None:
    path = config.heartbeat_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_cycle_at": _now().isoformat(),
        "ok": ok,
        "status": status,
        "error": error,
        "pid": os.getpid(),
    }
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)


def _save(config: Config, task: Task, message: str, extra_paths: list[Path] | None = None) -> None:
    task.touch()
    tasks_store.write_task(task)
    paths = [task.path, *(extra_paths or [])]
    gh_git.commit_and_push_bookkeeping(config.repo_path, paths, message, config.git_base_branch)


def _handle_in_review(config: Config, task: Task) -> str:
    status = gh_git.view_pr(config.repo_path, task.pr_number, config)
    if status.state == "MERGED":
        task.status = STATUS_DONE
        task.merged_at = status.merged_at
        old_path = tasks_store.move_to_done(task)
        _save(
            config, task,
            f"chore(tasks): mark task {task.id:03d} as done and move to tasks/done/",
            extra_paths=[old_path],
        )
        msg = f"tarea {task.id:03d}: PR #{task.pr_number} mergeado, marcada como done y movida a tasks/done/"
        log.info(msg)
    elif status.state == "CLOSED":
        task.status = STATUS_FAILED
        task.last_error = "PR cerrado sin fusionar"
        _save(config, task, f"chore(tasks): mark task {task.id:03d} as failed (PR cerrado)")
        msg = f"tarea {task.id:03d}: PR #{task.pr_number} cerrado sin fusionar, marcada como failed"
        log.warning(msg)
    else:
        msg = f"tarea {task.id:03d}: PR #{task.pr_number} todavía abierto, esperando merge manual"
        log.info(msg)
    return msg


def _run_task_attempt(config: Config, task: Task) -> str:
    branch = task.branch or tasks_store.branch_name_for(task)
    task.status = "in_progress"
    task.branch = branch
    task.started_at = task.started_at or tasks_store.now_iso()
    _save(config, task, f"chore(tasks): start processing task {task.id:03d}")

    worktree_dir = config.worktrees_dir / branch
    gh_git.ensure_clean_worktree(config.repo_path, worktree_dir, branch, config.git_base_branch)

    log.info("Tarea %03d: invocando claude en %s", task.id, worktree_dir)
    result = claude_runner.invoke_claude(task, worktree_dir, config)

    if result.ok and result.made_commits:
        doc_path = worktree_dir / "doc" / tasks_store.doc_filename_for(task)
        if not doc_path.exists():
            log.warning(
                "Tarea %03d: claude no creó %s (contexto acumulado sin actualizar para esta tarea)",
                task.id, doc_path.relative_to(worktree_dir),
            )

        gh_git.push_branch(worktree_dir, branch)
        pr = gh_git.create_pr(worktree_dir, branch, task, config)
        gh_git.remove_worktree(config.repo_path, worktree_dir)
        task.status = STATUS_IN_REVIEW
        task.pr_number = pr.number
        task.pr_url = pr.url
        task.submitted_at = tasks_store.now_iso()
        log.info("Tarea %03d: PR creado %s", task.id, pr.url)

        # Importante: comitear y pushear este bookkeeping ANTES de fusionar. Si se
        # fusionara primero, origin/<base_branch> avanzaría (por el propio merge) y el
        # push de este bookkeeping se rechazaría por "fetch first" contra el repo_path
        # local (sincronizado al principio del ciclo, antes del merge). Ese push
        # fallido perdía silenciosamente el pr_number/status=in_review: en el
        # siguiente ciclo la tarea parecía "in_progress recuperada tras un crash" y se
        # reprocesaba entera desde cero — con force=true esto producía un PR y un
        # merge duplicados en cada ciclo, indefinidamente (es lo que le pasó a la
        # tarea 001: 21 merges duplicados antes de detectar y arreglar este bug).
        _save(config, task, f"chore(tasks): open PR for task {task.id:03d}")

        if task.force:
            try:
                gh_git.merge_pr(config.repo_path, pr.number, config)
                log.info("Tarea %03d: force=true, PR #%s fusionado sin revisión humana", task.id, pr.number)
            except gh_git.GitError:
                log.exception(
                    "Tarea %03d: force=true pero el auto-merge del PR #%s falló; "
                    "queda en in_review esperando merge manual",
                    task.id, pr.number,
                )
        return f"tarea {task.id:03d}: PR creado {pr.url}"

    elif result.ok and not result.made_commits:
        gh_git.remove_worktree(config.repo_path, worktree_dir)
        task.status = STATUS_FAILED
        task.last_error = "claude finalizó sin crear ningún commit"
        _save(config, task, f"chore(tasks): mark task {task.id:03d} as failed (sin commits)")
        msg = f"tarea {task.id:03d}: claude no hizo ningún commit, marcada como failed"
        log.warning(msg)
        return msg

    elif result.is_retryable:
        gh_git.remove_worktree(config.repo_path, worktree_dir)
        task.attempts += 1
        delay = compute_backoff(config, task.attempts)
        task.status = STATUS_BLOCKED
        task.next_retry_at = (_now() + delay).isoformat()
        task.last_error = result.error_snippet
        _save(config, task, f"chore(tasks): backoff retry for task {task.id:03d} (intento {task.attempts})")
        msg = (
            f"tarea {task.id:03d}: fallo reintentable (intento {task.attempts}), "
            f"próximo intento en {delay}: {result.error_snippet}"
        )
        log.warning(msg)
        return msg

    else:
        gh_git.remove_worktree(config.repo_path, worktree_dir)
        task.attempts += 1
        task.status = STATUS_FAILED
        task.last_error = result.error_snippet
        _save(config, task, f"chore(tasks): mark task {task.id:03d} as failed")
        msg = f"tarea {task.id:03d}: fallo duro, marcada como failed: {result.error_snippet}"
        log.error(msg)
        return msg


def process_once(config: Config) -> str:
    gh_git.sync_base_branch(config.repo_path, config.git_base_branch)
    tasks = tasks_store.load_tasks(config.tasks_dir)

    for task in tasks:
        if task.status == STATUS_DONE:
            continue

        if task.status == STATUS_FAILED:
            msg = (
                f"tarea {task.id:03d} en failed ({task.last_error}). "
                "Cola detenida, requiere intervención manual."
            )
            log.warning(msg)
            return msg

        if task.status == STATUS_IN_REVIEW:
            return _handle_in_review(config, task)

        if task.status == STATUS_BLOCKED:
            next_retry_at = _parse_iso(task.next_retry_at)
            if next_retry_at and _now() < next_retry_at:
                msg = f"tarea {task.id:03d}: en backoff, próximo intento en {next_retry_at - _now()}"
                log.info(msg)
                return msg

        # pending, blocked (backoff vencido), o in_progress recuperado tras un crash
        return _run_task_attempt(config, task)

    msg = "no hay tareas pendientes, cola vacía"
    log.info(msg)
    return msg


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = load_config()
    log.info(
        "madrono-agent arrancando. repo_path=%s poll_interval=%ss",
        config.repo_path, config.poll_interval_seconds,
    )
    _sd_notify("READY=1")
    _start_watchdog_thread()

    while True:
        try:
            status = process_once(config)
            write_heartbeat(config, status=status, ok=True)
        except Exception as exc:
            log.exception("Fallo inesperado en process_once(); se reintentará en el próximo ciclo")
            write_heartbeat(config, status="excepción en process_once", ok=False, error=str(exc))
        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    main()
