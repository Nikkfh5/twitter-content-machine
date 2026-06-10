from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .sessions import ContentSession, save_session
from .utils import iso_now


STEP_STATUSES = {"pending", "running", "done", "failed", "skipped"}


@dataclass
class RunStep:
    id: str
    kind: str = "local"
    status: str = "pending"
    requires_confirmation: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "requires_confirmation": self.requires_confirmation,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "artifacts": self.artifacts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunStep":
        status = str(data.get("status", "pending"))
        if status not in STEP_STATUSES:
            status = "pending"
        return cls(
            id=str(data["id"]),
            kind=str(data.get("kind", "local")),
            status=status,
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            artifacts=[str(item) for item in data.get("artifacts", [])],
        )


@dataclass
class WorkspaceRun:
    id: str
    session_id: str
    path: Path
    type: str
    input_text: str
    created_at: str
    updated_at: str
    status: str = "pending"
    cwd: str | None = None
    draft_id: str | None = None
    draft_folder: str | None = None
    final_text: str | None = None
    steps: list[RunStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "path": str(self.path),
            "type": self.type,
            "input_text": self.input_text,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "cwd": self.cwd,
            "draft_id": self.draft_id,
            "draft_folder": self.draft_folder,
            "final_text": self.final_text,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], path: Path | None = None) -> "WorkspaceRun":
        return cls(
            id=str(data["id"]),
            session_id=str(data["session_id"]),
            path=path or Path(str(data["path"])),
            type=str(data.get("type", "draft_generation")),
            input_text=str(data.get("input_text", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", data.get("created_at", ""))),
            status=str(data.get("status", "pending")),
            cwd=data.get("cwd"),
            draft_id=data.get("draft_id"),
            draft_folder=data.get("draft_folder"),
            final_text=data.get("final_text"),
            steps=[RunStep.from_dict(item) for item in data.get("steps", [])],
        )


def default_draft_steps() -> list[RunStep]:
    return [
        RunStep("create_draft"),
        RunStep("write_context"),
        RunStep("write_format_decision"),
        RunStep("prepare_codex_contract"),
        RunStep("run_codex", kind="codex", requires_confirmation=True),
        RunStep("load_output_protocol"),
        RunStep("mark_needs_user"),
    ]


def create_run(session: ContentSession, run_type: str, input_text: str, cwd: Path | None = None) -> WorkspaceRun:
    run_id = _unique_run_id(session.path / "runs")
    run_path = session.path / "runs" / run_id
    run_path.mkdir(parents=True, exist_ok=False)
    now = iso_now()
    run = WorkspaceRun(
        id=run_id,
        session_id=session.id,
        path=run_path,
        type=run_type,
        input_text=input_text,
        created_at=now,
        updated_at=now,
        cwd=str(cwd.resolve()) if cwd else None,
        steps=default_draft_steps(),
    )
    save_run(run)
    if run.id not in session.runs:
        session.runs.append(run.id)
    session.current_run_id = run.id
    save_session(session)
    append_event(run, "run_created", f"Run {run.type} created")
    return run


def load_run(path: Path) -> WorkspaceRun:
    data = json.loads((path / "run.json").read_text(encoding="utf-8"))
    return WorkspaceRun.from_dict(data, path=path)


def save_run(run: WorkspaceRun) -> None:
    run.updated_at = iso_now()
    run.path.mkdir(parents=True, exist_ok=True)
    (run.path / "run.json").write_text(
        json.dumps(run.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def append_event(
    run: WorkspaceRun,
    event_type: str,
    message: str,
    step_id: str | None = None,
    source: str = "tw",
    severity: str = "info",
) -> None:
    event = {
        "ts": iso_now(),
        "source": source,
        "type": event_type,
        "message": message,
        "step_id": step_id,
        "severity": severity,
    }
    with (run.path / "events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_events(run: WorkspaceRun | Path) -> list[dict[str, Any]]:
    path = run.path if isinstance(run, WorkspaceRun) else run
    events_path = path / "events.jsonl"
    if not events_path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append(
                {
                    "ts": "",
                    "source": "tw",
                    "type": "failed",
                    "message": f"Invalid event line: {line[:120]}",
                    "step_id": None,
                    "severity": "warning",
                }
            )
    return events


def next_unfinished_step(run: WorkspaceRun, allow_codex: bool = False) -> RunStep | None:
    for step in run.steps:
        if step.status in {"done", "skipped"}:
            continue
        if step.kind == "codex" and step.requires_confirmation and not allow_codex:
            return None
        return step
    return None


def pending_codex_step(run: WorkspaceRun) -> RunStep | None:
    for step in run.steps:
        if step.status in {"done", "skipped"}:
            continue
        if step.kind == "codex":
            return step
        return None
    return None


def _unique_run_id(runs_root: Path) -> str:
    runs_root.mkdir(parents=True, exist_ok=True)
    base = f"{iso_now().replace(':', '').replace('-', '')}-draft-generation"
    candidate = base
    counter = 2
    while (runs_root / candidate).exists():
        candidate = f"{base}-{counter:02d}"
        counter += 1
    return candidate
