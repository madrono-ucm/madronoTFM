"""Demonio 24/7: procesa las tareas de tasks/*.md una a una y en orden.

Bucle principal simple: en cada ciclo da un único paso de estado (process_once) y
duerme POLL_INTERVAL_SECONDS. Pensado para correr como servicio systemd
(Restart=always) sobre un clon dedicado del repo (ver tasks/scripts/config.example.env).
"""

from __future__ import annotations

import logging
import os
import random
import sys
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

    @property
    def tasks_dir(self) -> Path:
        return self.repo_path / "tasks"

    @property
    def worktrees_dir(self) -> Path:
        return self.repo_path / "tasks" / "scripts" / ".worktrees"


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


def _save(config: Config, task: Task, message: str) -> None:
    task.touch()
    tasks_store.write_task(task)
    gh_git.commit_and_push_bookkeeping(config.repo_path, task.path, message, config.git_base_branch)


def _handle_in_review(config: Config, task: Task) -> None:
    status = gh_git.view_pr(config.repo_path, task.pr_number, config)
    if status.state == "MERGED":
        task.status = STATUS_DONE
        task.merged_at = status.merged_at
        _save(config, task, f"chore(tasks): mark task {task.id:03d} as done (PR mergeado)")
        log.info("Tarea %03d: PR #%s mergeado, marcada como done", task.id, task.pr_number)
    elif status.state == "CLOSED":
        task.status = STATUS_FAILED
        task.last_error = "PR cerrado sin fusionar"
        _save(config, task, f"chore(tasks): mark task {task.id:03d} as failed (PR cerrado)")
        log.warning("Tarea %03d: PR #%s cerrado sin fusionar, marcada como failed", task.id, task.pr_number)
    else:
        log.info("Tarea %03d: PR #%s todavía abierto, esperando merge manual", task.id, task.pr_number)


def _run_task_attempt(config: Config, task: Task) -> None:
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
        gh_git.push_branch(worktree_dir, branch)
        pr = gh_git.create_pr(worktree_dir, branch, task, config)
        gh_git.remove_worktree(config.repo_path, worktree_dir)
        task.status = STATUS_IN_REVIEW
        task.pr_number = pr.number
        task.pr_url = pr.url
        task.submitted_at = tasks_store.now_iso()
        _save(config, task, f"chore(tasks): open PR for task {task.id:03d}")
        log.info("Tarea %03d: PR creado %s", task.id, pr.url)

    elif result.ok and not result.made_commits:
        gh_git.remove_worktree(config.repo_path, worktree_dir)
        task.status = STATUS_FAILED
        task.last_error = "claude finalizó sin crear ningún commit"
        _save(config, task, f"chore(tasks): mark task {task.id:03d} as failed (sin commits)")
        log.warning("Tarea %03d: claude no hizo ningún commit, marcada como failed", task.id)

    elif result.is_retryable:
        gh_git.remove_worktree(config.repo_path, worktree_dir)
        task.attempts += 1
        delay = compute_backoff(config, task.attempts)
        task.status = STATUS_BLOCKED
        task.next_retry_at = (_now() + delay).isoformat()
        task.last_error = result.error_snippet
        _save(config, task, f"chore(tasks): backoff retry for task {task.id:03d} (intento {task.attempts})")
        log.warning(
            "Tarea %03d: fallo reintentable (intento %d), próximo intento en %s: %s",
            task.id, task.attempts, delay, result.error_snippet,
        )

    else:
        gh_git.remove_worktree(config.repo_path, worktree_dir)
        task.attempts += 1
        task.status = STATUS_FAILED
        task.last_error = result.error_snippet
        _save(config, task, f"chore(tasks): mark task {task.id:03d} as failed")
        log.error("Tarea %03d: fallo duro, marcada como failed: %s", task.id, result.error_snippet)


def process_once(config: Config) -> None:
    gh_git.sync_base_branch(config.repo_path, config.git_base_branch)
    tasks = tasks_store.load_tasks(config.tasks_dir)

    for task in tasks:
        if task.status == STATUS_DONE:
            continue

        if task.status == STATUS_FAILED:
            log.warning(
                "Tarea %03d en FAILED (%s). Cola detenida, requiere intervención manual.",
                task.id, task.last_error,
            )
            return

        if task.status == STATUS_IN_REVIEW:
            _handle_in_review(config, task)
            return

        if task.status == STATUS_BLOCKED:
            next_retry_at = _parse_iso(task.next_retry_at)
            if next_retry_at and _now() < next_retry_at:
                log.info("Tarea %03d: en backoff, próximo intento en %s", task.id, next_retry_at - _now())
                return

        # pending, blocked (backoff vencido), o in_progress recuperado tras un crash
        _run_task_attempt(config, task)
        return

    log.info("No hay tareas pendientes. Cola vacía.")


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

    while True:
        try:
            process_once(config)
        except Exception:
            log.exception("Fallo inesperado en process_once(); se reintentará en el próximo ciclo")
        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    main()
