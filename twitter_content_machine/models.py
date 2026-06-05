from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    root: Path
    db_path: Path


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    root_path: Path


@dataclass(frozen=True)
class ProjectContext:
    project: Project
    summary: str
    context_path: Path
    recent_changes_path: Path
    public_angle_path: Path


@dataclass(frozen=True)
class DraftResult:
    id: str
    folder: Path
    final_text: str


@dataclass(frozen=True)
class SyncResult:
    imported: int
    message: str
