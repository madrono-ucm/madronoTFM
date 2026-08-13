"""Parseo y escritura de las tareas en tasks/*.md (front-matter YAML + cuerpo markdown)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

import yaml

STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_IN_REVIEW = "in_review"
STATUS_BLOCKED = "blocked"
STATUS_FAILED = "failed"
STATUS_DONE = "done"

IGNORED_FILENAMES = {"README.md", "_template.md"}
DONE_SUBDIR_NAME = "done"
TASK_FILENAME_RE = re.compile(r"^(\d+)-([a-z0-9-]+)\.md$")
FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

FRONT_MATTER_FIELDS = (
    "id",
    "slug",
    "title",
    "status",
    "force",
    "allow_infra_apply",
    "branch",
    "pr_number",
    "pr_url",
    "attempts",
    "next_retry_at",
    "last_error",
    "created_at",
    "updated_at",
    "started_at",
    "submitted_at",
    "merged_at",
)


class TaskParseError(RuntimeError):
    pass


class DuplicateTaskIdError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Task:
    id: int
    slug: str
    title: str
    status: str = STATUS_PENDING
    force: bool = False
    allow_infra_apply: bool = False
    branch: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    attempts: int = 0
    next_retry_at: str | None = None
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    submitted_at: str | None = None
    merged_at: str | None = None
    body: str = field(default="", compare=False)
    path: Path | None = field(default=None, compare=False)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def to_front_matter(self) -> dict:
        return {name: getattr(self, name) for name in FRONT_MATTER_FIELDS}


def _parse_task_file(path: Path) -> Task:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(text)
    if not match:
        raise TaskParseError(f"{path}: no se encontró front-matter YAML delimitado por '---'")

    raw_front_matter, body = match.groups()
    try:
        data = yaml.safe_load(raw_front_matter) or {}
    except yaml.YAMLError as exc:
        raise TaskParseError(f"{path}: front-matter YAML inválido: {exc}") from exc

    known_fields = {f.name for f in fields(Task)} - {"body", "path"}
    unknown = set(data) - known_fields
    if unknown:
        raise TaskParseError(f"{path}: campos desconocidos en front-matter: {sorted(unknown)}")

    return Task(body=body.strip("\n"), path=path, **data)


def _filename_for(task_id: int, slug: str) -> str:
    return f"{task_id:03d}-{slug}.md"


def load_tasks(tasks_dir: Path) -> list[Task]:
    """Carga y ordena todas las tareas de tasks_dir por su prefijo numérico ascendente."""
    tasks: list[Task] = []
    seen_ids: dict[int, Path] = {}

    for path in sorted(tasks_dir.glob("*.md")):
        if path.name in IGNORED_FILENAMES:
            continue
        m = TASK_FILENAME_RE.match(path.name)
        if not m:
            continue

        filename_id = int(m.group(1))
        task = _parse_task_file(path)
        if task.id != filename_id:
            raise TaskParseError(
                f"{path}: el 'id' del front-matter ({task.id}) no coincide con el "
                f"prefijo del nombre de archivo ({filename_id})"
            )
        if filename_id in seen_ids:
            raise DuplicateTaskIdError(
                f"id {filename_id} duplicado entre {seen_ids[filename_id]} y {path}"
            )
        seen_ids[filename_id] = path
        tasks.append(task)

    tasks.sort(key=lambda t: t.id)
    return tasks


def write_task(task: Task) -> None:
    """Reescribe el archivo de la tarea con su front-matter y cuerpo actuales."""
    if task.path is None:
        raise ValueError("write_task requiere que task.path esté fijado")

    front_matter = yaml.safe_dump(
        task.to_front_matter(), sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    content = f"---\n{front_matter}---\n\n{task.body}\n"
    task.path.write_text(content, encoding="utf-8")


def move_to_done(task: Task) -> Path:
    """Mueve el archivo de la tarea a tasks/done/ (status ya debe ser done).

    Devuelve la ruta anterior (para poder registrar su borrado al comitear) y deja
    task.path apuntando a la nueva ubicación.
    """
    if task.path is None:
        raise ValueError("move_to_done requiere que task.path esté fijado")

    old_path = task.path
    done_dir = old_path.parent / DONE_SUBDIR_NAME
    done_dir.mkdir(exist_ok=True)
    new_path = done_dir / old_path.name
    old_path.rename(new_path)
    task.path = new_path
    return old_path


def branch_name_for(task: Task) -> str:
    return f"task/{_filename_for(task.id, task.slug).removesuffix('.md')}"


def doc_filename_for(task: Task) -> str:
    """Nombre del resumen en doc/, con el mismo esquema NNN-slug.md que la propia tarea."""
    return _filename_for(task.id, task.slug)
