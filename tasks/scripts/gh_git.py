"""Integración con git (worktrees, ramas, push) y con `gh` (crear/consultar Pull Requests)."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

PR_URL_NUMBER_RE = re.compile(r"/pull/(\d+)\s*$")


class GitError(RuntimeError):
    pass


@dataclass
class PullRequestInfo:
    number: int
    url: str


@dataclass
class PullRequestStatus:
    state: str  # OPEN | MERGED | CLOSED
    merged_at: str | None
    url: str


def _run(cmd: list[str], cwd: Path | None = None, timeout: int | None = 120) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise GitError(f"{' '.join(cmd)} (cwd={cwd}) falló: {proc.stderr.strip()}")
    return proc.stdout.strip()


def sync_base_branch(repo_path: Path, base_branch: str) -> None:
    """Deja el clon dedicado (repo_path) sincronizado con origin/<base_branch>."""
    _run(["git", "fetch", "origin", base_branch], cwd=repo_path)
    _run(["git", "checkout", base_branch], cwd=repo_path)
    _run(["git", "reset", "--hard", f"origin/{base_branch}"], cwd=repo_path)


def commit_and_push_bookkeeping(
    repo_path: Path, task_path: Path, message: str, base_branch: str
) -> bool:
    """Comitea y pushea a base_branch los cambios de estado de una tarea (front-matter).

    Devuelve True si hubo algo que comitear, False si no había cambios (no-op idempotente).
    """
    _run(["git", "add", str(task_path)], cwd=repo_path)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_path)
    if diff.returncode == 0:
        return False  # nada en el índice, no hay nada que comitear
    _run(["git", "commit", "-m", message], cwd=repo_path)
    _run(["git", "push", "origin", base_branch], cwd=repo_path)
    return True


def _branch_exists_remote(repo_path: Path, branch: str) -> bool:
    out = _run(["git", "ls-remote", "--heads", "origin", branch], cwd=repo_path)
    return bool(out)


def _branch_exists_local(repo_path: Path, branch: str) -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", branch], cwd=repo_path, capture_output=True
    )
    return proc.returncode == 0


def ensure_clean_worktree(repo_path: Path, worktree_dir: Path, branch: str, base_branch: str) -> None:
    """Prepara un worktree aislado en worktree_dir sobre `branch`, limpiando restos de un crash previo."""
    if worktree_dir.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree_dir)], cwd=repo_path)
    _run(["git", "worktree", "prune"], cwd=repo_path)

    if _branch_exists_local(repo_path, branch):
        _run(["git", "worktree", "add", str(worktree_dir), branch], cwd=repo_path)
    elif _branch_exists_remote(repo_path, branch):
        _run(["git", "fetch", "origin", branch], cwd=repo_path)
        _run(["git", "worktree", "add", str(worktree_dir), branch], cwd=repo_path)
    else:
        _run(["git", "worktree", "add", str(worktree_dir), "-b", branch, base_branch], cwd=repo_path)


def remove_worktree(repo_path: Path, worktree_dir: Path) -> None:
    subprocess.run(["git", "worktree", "remove", "--force", str(worktree_dir)], cwd=repo_path)
    subprocess.run(["git", "worktree", "prune"], cwd=repo_path)


def push_branch(worktree_dir: Path, branch: str) -> None:
    _run(["git", "push", "-u", "origin", branch], cwd=worktree_dir, timeout=300)


def create_pr(worktree_dir: Path, branch: str, task, config) -> PullRequestInfo:
    title = f"[task {task.id:03d}] {task.title}"
    body = (
        f"Implementa `tasks/{task.path.name}` de forma automática.\n\n"
        + (
            "Generado por madrono-agent. `force: true` — este PR se fusionará "
            "automáticamente sin revisión humana."
            if task.force
            else "Generado por madrono-agent. Revisa el diff antes de fusionar."
        )
    )
    out = _run(
        [
            config.gh_bin, "pr", "create",
            "--repo", config.github_repo,
            "--base", config.git_base_branch,
            "--head", branch,
            "--title", title,
            "--body", body,
        ],
        cwd=worktree_dir,
        timeout=120,
    )
    url = out.splitlines()[-1].strip()
    match = PR_URL_NUMBER_RE.search(url)
    if not match:
        raise GitError(f"no se pudo extraer el número de PR de la salida de gh: {out!r}")
    return PullRequestInfo(number=int(match.group(1)), url=url)


def merge_pr(repo_path: Path, pr_number: int, config) -> None:
    """Fusiona un PR sin esperar revisión humana (solo para tareas con force: true)."""
    _run(
        [
            config.gh_bin, "pr", "merge", str(pr_number),
            "--repo", config.github_repo,
            f"--{config.gh_merge_method}",
            "--delete-branch",
        ],
        cwd=repo_path,
        timeout=120,
    )


def view_pr(repo_path: Path, pr_number: int, config) -> PullRequestStatus:
    out = _run(
        [
            config.gh_bin, "pr", "view", str(pr_number),
            "--repo", config.github_repo,
            "--json", "state,mergedAt,url",
        ],
        cwd=repo_path,
        timeout=60,
    )
    data = json.loads(out)
    return PullRequestStatus(state=data["state"], merged_at=data.get("mergedAt"), url=data["url"])
