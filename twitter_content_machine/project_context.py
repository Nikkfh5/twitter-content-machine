from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from .config import load_config
from .db import connect_db
from .models import Project, ProjectContext
from .review import redact_secrets
from .utils import first_nonempty_line, format_list, get_now, iso_now, safe_read_text, short_hash, should_ignore_path, slugify
from .workspace import ensure_workspace


def _run_git(root: Path, args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _git_root(cwd: Path) -> Path | None:
    out = _run_git(cwd, ["rev-parse", "--show-toplevel"])
    return Path(out).resolve() if out else None


def detect_project(cwd: Path | str | None = None) -> Project:
    current = Path(cwd or os.getcwd()).resolve()
    root = _git_root(current) or current
    name = root.name or "project"
    project_id = f"{slugify(name, max_words=4)}-{short_hash(str(root).lower(), 8)}"
    return Project(id=project_id, name=name, root_path=root)


def _tree(root: Path, max_entries: int = 160) -> list[str]:
    entries: list[str] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if should_ignore_path(rel):
            continue
        if len(entries) >= max_entries:
            entries.append("[truncated]")
            break
        suffix = "/" if path.is_dir() else ""
        entries.append(f"{rel.as_posix()}{suffix}")
    return entries


def _read_context_files(root: Path) -> dict[str, str]:
    candidates = [
        "README.md",
        "AGENTS.md",
        "PROJECT_CONTEXT.md",
        ".twitter-context.md",
        ".public-notes.md",
    ]
    result: dict[str, str] = {}
    for rel in candidates:
        path = root / rel
        if path.exists() and not should_ignore_path(Path(rel)):
            result[rel] = redact_secrets(safe_read_text(path, 30_000))
    docs = root / "docs"
    if docs.exists() and docs.is_dir():
        for path in sorted(docs.rglob("*.md"))[:12]:
            rel = path.relative_to(root)
            if not should_ignore_path(rel):
                result[rel.as_posix()] = redact_secrets(safe_read_text(path, 12_000))
    return result


def _git_state(project: Project) -> tuple[str, str, str]:
    branch = _run_git(project.root_path, ["branch", "--show-current"]) or "(not a git repo)"
    status = _run_git(project.root_path, ["status", "--short"]) or "clean or unavailable"
    commits = _run_git(project.root_path, ["log", "--oneline", "-n", "8"]) or "unavailable"
    return branch, status, commits


def _recent_files(root: Path) -> list[str]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and not should_ignore_path(path.relative_to(root)):
            files.append(path)
    files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return [p.relative_to(root).as_posix() for p in files[:20]]


def _filesystem_state(root: Path) -> str:
    parts: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not should_ignore_path(path.relative_to(root)):
            try:
                parts.append(f"{path.relative_to(root).as_posix()}:{int(path.stat().st_mtime)}")
            except OSError:
                continue
        if len(parts) >= 80:
            break
    return "\n".join(parts)


def _cache_is_fresh(cache_text: str, state_hash: str, minutes: int) -> bool:
    if f"git_state: {state_hash}" not in cache_text:
        return False
    updated = ""
    for line in cache_text.splitlines():
        if line.startswith("updated_at: "):
            updated = line.split(": ", 1)[1].strip()
            break
    if not updated:
        return False
    try:
        updated_at = datetime.fromisoformat(updated)
    except ValueError:
        return False
    return get_now() - updated_at < timedelta(minutes=minutes)


def refresh_project_context(project: Project, force: bool = False) -> ProjectContext:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    project_dir = workspace.root / "projects" / project.id
    project_dir.mkdir(parents=True, exist_ok=True)
    cache_meta = project_dir / "cache_meta.yaml"

    branch, status, commits = _git_state(project)
    state_hash = short_hash(branch + status + commits + _filesystem_state(project.root_path), 12)
    if cache_meta.exists() and not force:
        previous = cache_meta.read_text(encoding="utf-8", errors="replace")
        if _cache_is_fresh(previous, state_hash, config.context_cache_minutes):
            context_path = project_dir / "context.md"
            if context_path.exists():
                summary = context_path.read_text(encoding="utf-8", errors="replace")
                return ProjectContext(
                    project=project,
                    summary=summary,
                    context_path=context_path,
                    recent_changes_path=project_dir / "recent_changes.md",
                    public_angle_path=project_dir / "public_angle.md",
                )

    files = _read_context_files(project.root_path)
    tree = _tree(project.root_path)
    recent = _recent_files(project.root_path)
    title = project.name
    for text in files.values():
        first = first_nonempty_line(text)
        if first:
            title = first
            break

    summary_parts = [
        f"# Project Context: {project.name}",
        "",
        f"- project_id: {project.id}",
        f"- root: {project.root_path}",
        f"- inferred_public_title: {title}",
        "",
        "## Files Read",
        format_list(list(files.keys())),
        "",
        "## Safe Summary",
        "This is an automatically collected public-context summary. It intentionally avoids secrets, credentials, hidden env files, large data, and binary files.",
    ]
    for rel, text in files.items():
        summary_parts.extend(["", f"### {rel}", text[:4000].strip()])
    summary_parts.extend(["", "## File Tree", format_list(tree)])
    summary = "\n".join(summary_parts).strip() + "\n"

    recent_text = f"""# Recent Changes: {project.name}

- branch: {branch}
- git_state: {state_hash}

## Git Status
```text
{status}
```

## Recent Commits
```text
{commits}
```

## Recently Modified Files
{format_list(recent)}
"""
    public_angle = f"""# Public Angle: {project.name}

Write only from safe, public notebook perspective:
- what changed in understanding
- what broke
- what was checked
- what remains uncertain

Do not expose private internals, secrets, credentials, company details, or trading advice.
"""
    context_path = project_dir / "context.md"
    recent_path = project_dir / "recent_changes.md"
    angle_path = project_dir / "public_angle.md"
    context_path.write_text(summary, encoding="utf-8")
    recent_path.write_text(recent_text, encoding="utf-8")
    angle_path.write_text(public_angle, encoding="utf-8")
    cache_meta.write_text(
        f"updated_at: {iso_now()}\ngit_state: {state_hash}\ncache_minutes: {config.context_cache_minutes}\n",
        encoding="utf-8",
    )
    with connect_db() as conn:
        now = iso_now()
        conn.execute(
            """
            insert into projects(id, name, root_path, created_at, updated_at, summary, public_angle)
            values(?, ?, ?, ?, ?, ?, ?)
            on conflict(id) do update set
              name=excluded.name,
              root_path=excluded.root_path,
              updated_at=excluded.updated_at,
              summary=excluded.summary,
              public_angle=excluded.public_angle
            """,
            (project.id, project.name, str(project.root_path), now, now, summary, public_angle),
        )
    return ProjectContext(project, summary, context_path, recent_path, angle_path)
