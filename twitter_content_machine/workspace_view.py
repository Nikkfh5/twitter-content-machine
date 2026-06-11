from __future__ import annotations

from pathlib import Path

from .output_protocol import LoadedInterfaceSummary
from .runs import WorkspaceRun, next_unfinished_step, pending_codex_step, read_events
from .sessions import ContentSession


STEP_LABELS = {
    "create_draft": "create draft files",
    "write_context": "collect context",
    "write_format_decision": "choose format",
    "prepare_codex_contract": "prepare Codex contract",
    "run_codex": "run Codex",
    "load_output_protocol": "load summary",
    "mark_needs_user": "wait for user",
}


def render_empty_workspace_screen(root: Path) -> str:
    return "\n".join(
        [
            "Content Workspace",
            "",
            "Status: empty",
            "Next action: /draft <idea>",
            "",
            "Draft preview",
            "No active draft yet.",
            "",
            "Write the raw idea first. It can be rough, mixed-language, or just a note.",
            "Command: /draft <idea>",
            "The workspace will create a resumable session and stop before any long Codex run.",
            "",
            f"Workspace: {root}",
        ]
    )


def render_session_without_run_screen(session: ContentSession) -> str:
    return "\n".join(
        [
            "Content Workspace",
            "",
            f"Status: {session.status}/{session.internal_status}",
            "Next action: /draft <idea>",
            "",
            "Draft preview",
            "No run in this session yet.",
            "",
            f"Session: {session.path}",
        ]
    )


def render_workspace_screen(
    session: ContentSession,
    run: WorkspaceRun,
    loaded: LoadedInterfaceSummary,
) -> str:
    return "\n".join(
        [
            "Content Workspace",
            "",
            f"Status: {session.status}/{session.internal_status}",
            f"Draft: {run.draft_id or 'not created yet'}",
            f"Run: {run.type} / {run.status}",
            f"Next action: {_next_action(run)}",
            "",
            "Draft preview",
            _draft_preview(run),
            "",
            "Summary",
            _summary_text(run, loaded),
            "",
            "Problems",
            _bullet_block(_problem_lines(run, loaded)),
            "",
            "Decisions",
            _bullet_block(_decision_lines(loaded)),
            "",
            "Progress",
            "\n".join(_progress_lines(run)),
            "",
            "Files",
            _bullet_block(_file_lines(run, loaded)),
            "",
            "Recent activity",
            _bullet_block(_activity_lines(run)),
        ]
    ).rstrip()


def _next_action(run: WorkspaceRun) -> str:
    codex_step = pending_codex_step(run)
    if codex_step is not None:
        return "/continue --run - run Codex and create final candidate"
    step = next_unfinished_step(run, allow_codex=True)
    if step is not None:
        return f"/continue - finish {STEP_LABELS.get(step.id, step.id)}"
    if run.status == "failed":
        return "/path - inspect failed run artifacts"
    return "/path - inspect draft and session files"


def _draft_preview(run: WorkspaceRun) -> str:
    folder = Path(run.draft_folder) if run.draft_folder else None
    if folder:
        candidate = folder / "06_final_candidate.md"
        if candidate.exists():
            return _limit_lines(candidate.read_text(encoding="utf-8", errors="replace").strip(), 8)
    if run.final_text:
        return _limit_lines(run.final_text.strip(), 8)
    return _limit_lines(run.input_text.strip(), 8)


def _summary_text(run: WorkspaceRun, loaded: LoadedInterfaceSummary) -> str:
    if loaded.data is not None:
        return loaded.data.summary
    if loaded.markdown:
        return _limit_lines(_markdown_without_headings(loaded.markdown), 5)
    if run.draft_id:
        return "Draft context is ready. Codex summary is not loaded yet."
    return "Raw idea captured. Local generation has not started yet."


def _problem_lines(run: WorkspaceRun, loaded: LoadedInterfaceSummary) -> list[str]:
    if loaded.data is not None and loaded.data.problems:
        return loaded.data.problems[:4]
    if loaded.warnings and _codex_finished(run):
        return loaded.warnings[:3]
    step = next_unfinished_step(run, allow_codex=True)
    if step is not None and step.id != "run_codex":
        return ["No Codex critique yet.", "Run /continue to prepare context before the model step."]
    return ["No Codex critique yet.", "Run /continue --run when ready for the model step."]


def _decision_lines(loaded: LoadedInterfaceSummary) -> list[str]:
    if loaded.data is not None and loaded.data.decisions:
        return [
            f"{item.name}: {item.value} - {item.reason}".strip()
            for item in loaded.data.decisions[:4]
        ]
    return ["Local steps prepared context, format decision, and Codex contract."]


def _codex_finished(run: WorkspaceRun) -> bool:
    return any(step.id == "run_codex" and step.status in {"done", "failed"} for step in run.steps)


def _file_lines(run: WorkspaceRun, loaded: LoadedInterfaceSummary) -> list[str]:
    if loaded.data is not None and loaded.data.files:
        return [f"{item.label}: {item.path}" for item in loaded.data.files[:5]]
    lines = [f"run: {run.path}"]
    if run.draft_folder:
        lines.append(f"draft: {run.draft_folder}")
    return lines


def _activity_lines(run: WorkspaceRun) -> list[str]:
    events = read_events(run)[-5:]
    if not events:
        return ["No activity yet."]
    return [_human_event(event) for event in events]


def _human_event(event: dict) -> str:
    event_type = str(event.get("type", ""))
    step_id = event.get("step_id")
    label = STEP_LABELS.get(str(step_id), str(step_id or "workspace"))
    if event_type == "step_started":
        text = f"Started {label}"
    elif event_type == "step_finished":
        text = f"Finished {label}"
    elif event_type == "needs_user":
        text = "Waiting for your next command"
    elif event_type == "codex_started":
        text = "Codex run started"
    elif event_type == "codex_finished":
        text = "Codex run finished"
    elif event_type == "failed":
        text = f"Failed: {event.get('message', '')}"
    elif event_type == "summary_loaded":
        text = "Loaded interface summary"
    elif event_type == "run_created":
        text = "Created draft run"
    elif event_type == "session_created":
        text = "Opened workspace session"
    else:
        text = str(event.get("message", event_type))
    ts = str(event.get("ts", ""))
    short_ts = ts[11:19] if len(ts) >= 19 else ts
    return f"{short_ts} {text}".strip()


def _progress_lines(run: WorkspaceRun) -> list[str]:
    marks = {
        "done": "[x]",
        "running": "[>]",
        "failed": "[!]",
        "skipped": "[-]",
        "pending": "[ ]",
    }
    return [
        f"{marks.get(step.status, '[ ]')} {STEP_LABELS.get(step.id, step.id)}"
        for step in run.steps
    ]


def _bullet_block(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items if item) or "- none"


def _limit_lines(text: str, limit: int) -> str:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "empty"
    clipped = lines[:limit]
    if len(lines) > limit:
        clipped.append("...")
    return "\n".join(clipped)


def _markdown_without_headings(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return "\n".join(lines)
