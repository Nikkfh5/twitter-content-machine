from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import load_config
from .drafting import create_draft
from .llm import run_llm
from .output_protocol import load_interface_summary
from .runs import (
    RunStep,
    WorkspaceRun,
    append_event,
    create_run,
    load_run,
    next_unfinished_step,
    pending_codex_step,
    save_run,
)
from .sessions import ContentSession, create_session, find_resumable_session, load_session, save_session
from .workspace_protocol import (
    agents_contract,
    apply_llm_result,
    output_schema_contract,
    task_contract,
    write_artifacts,
    write_interface_summary,
)
from .workspace_view import (
    render_empty_workspace_screen,
    render_session_without_run_screen,
    render_workspace_screen,
)
from .workspace import ensure_workspace


@dataclass(frozen=True)
class WorkspaceCommandResult:
    ok: bool
    message: str
    session: ContentSession | None = None
    run: WorkspaceRun | None = None
    exit_requested: bool = False


class ContentWorkspaceService:
    def __init__(self, cwd: Path | None = None, root: Path | None = None) -> None:
        self.workspace = ensure_workspace(root)
        self.cwd = cwd
        self.session = find_resumable_session(self.workspace.root)

    def handle(self, command: str) -> WorkspaceCommandResult:
        command = command.strip()
        if not command:
            return self.status()
        if not command.startswith("/"):
            if self.session is None:
                return self.draft(command)
            return WorkspaceCommandResult(False, "Commands for an active draft still need slash syntax. Try: /continue or /help", self.session)
        parts = shlex.split(command)
        name = parts[0].lower()
        args = parts[1:]
        if name == "/draft":
            return self.draft(" ".join(args).strip())
        if name == "/continue":
            return self.continue_run(run_codex="--run" in args)
        if name == "/status":
            return self.status()
        if name == "/runs":
            return self.runs()
        if name == "/path":
            return self.path()
        if name == "/help":
            return WorkspaceCommandResult(True, _help_text(), self.session)
        if name == "/exit":
            return WorkspaceCommandResult(True, "Выход.", self.session, exit_requested=True)
        return WorkspaceCommandResult(False, f"Неизвестная команда: {name}. Попробуй /help", self.session)

    def draft(self, text: str) -> WorkspaceCommandResult:
        if not text:
            return WorkspaceCommandResult(False, "Нужен текст: /draft <идея>", self.session)
        if self.session is None:
            self.session = create_session(self.workspace.root)
        run = create_run(self.session, "draft_generation", text, cwd=self.cwd)
        append_event(run, "session_created", f"Session {self.session.id} active")
        self.session.internal_status = "needs_user"
        save_session(self.session)
        return WorkspaceCommandResult(
            True,
            "Сессия создана. Run подготовлен. Дальше: /continue",
            self.session,
            run,
        )

    def continue_run(self, run_codex: bool = False) -> WorkspaceCommandResult:
        current = self._current_run()
        if current is None:
            return WorkspaceCommandResult(False, "Нет активного run. Начни: /draft <идея>", self.session)
        run = current
        assert self.session is not None
        self.session.internal_status = "running"
        save_session(self.session)
        while True:
            step = next_unfinished_step(run, allow_codex=run_codex)
            if step is None:
                codex_step = pending_codex_step(run)
                if codex_step is not None:
                    self.session.internal_status = "needs_user"
                    save_session(self.session)
                    append_event(run, "needs_user", "Codex step requires explicit confirmation", step_id=codex_step.id)
                    return WorkspaceCommandResult(
                        True,
                        "Next Codex run готов. Запуск: /continue --run",
                        self.session,
                        run,
                    )
                self.session.internal_status = "needs_user"
                save_session(self.session)
                return WorkspaceCommandResult(True, "Незавершенных step нет.", self.session, run)
            try:
                self._run_step(run, step)
            except Exception as exc:
                step.status = "failed"
                step.finished_at = _now()
                run.status = "failed"
                save_run(run)
                self.session.internal_status = "failed"
                save_session(self.session)
                append_event(run, "failed", str(exc), step_id=step.id, severity="error")
                return WorkspaceCommandResult(False, f"Step failed: {step.id}: {exc}", self.session, run)
            if step.kind == "codex" and run_codex:
                run_codex = False

    def status(self) -> WorkspaceCommandResult:
        if self.session is None:
            return WorkspaceCommandResult(True, "Пустой workspace. Начни: /draft <идея>", None)
        run = self._current_run()
        draft = self.session.draft_id or "none"
        run_id = run.id if run else "none"
        return WorkspaceCommandResult(
            True,
            f"Session: {self.session.status}/{self.session.internal_status}\nDraft: {draft}\nRun: {run_id}",
            self.session,
            run,
        )

    def runs(self) -> WorkspaceCommandResult:
        if self.session is None:
            return WorkspaceCommandResult(True, "Runs пока нет.", None)
        lines = [f"Session: {self.session.id}", ""]
        for run_id in self.session.runs:
            run_path = self.session.path / "runs" / run_id
            if not run_path.exists():
                continue
            run = load_run(run_path)
            lines.append(f"- {run.id}: {run.type} / {run.status}")
            for step in run.steps:
                lines.append(f"  {step.id}: {step.status}")
        return WorkspaceCommandResult(True, "\n".join(lines), self.session, self._current_run())

    def path(self) -> WorkspaceCommandResult:
        if self.session is None:
            return WorkspaceCommandResult(True, str(self.workspace.root / "sessions"), None)
        run = self._current_run()
        lines = [f"session: {self.session.path}"]
        if run:
            lines.append(f"run: {run.path}")
        if self.session.draft_id:
            lines.append(f"draft_id: {self.session.draft_id}")
        return WorkspaceCommandResult(True, "\n".join(lines), self.session, run)

    def render_summary(self) -> str:
        if self.session is None:
            return render_empty_workspace_screen(self.workspace.root)
        run = self._current_run()
        if run is None:
            return render_session_without_run_screen(self.session)
        loaded = load_interface_summary(run.path)
        return render_workspace_screen(self.session, run, loaded)

    def _current_run(self) -> WorkspaceRun | None:
        if self.session is None:
            return None
        self.session = load_session(self.session.path)
        if not self.session.current_run_id:
            return None
        run_path = self.session.path / "runs" / self.session.current_run_id
        if not run_path.exists():
            return None
        return load_run(run_path)

    def _run_step(self, run: WorkspaceRun, step: RunStep) -> None:
        step.status = "running"
        step.started_at = _now()
        run.status = "running"
        save_run(run)
        append_event(run, "step_started", f"{step.id} started", step_id=step.id)
        handlers: dict[str, Callable[[WorkspaceRun], None]] = {
            "create_draft": self._step_create_draft,
            "write_context": self._step_write_context,
            "write_format_decision": self._step_write_format_decision,
            "prepare_codex_contract": self._step_prepare_codex_contract,
            "run_codex": self._step_run_codex,
            "load_output_protocol": self._step_load_output_protocol,
            "mark_needs_user": self._step_mark_needs_user,
        }
        handlers[step.id](run)
        step.status = "done"
        step.finished_at = _now()
        run.status = "needs_user" if step.id == "mark_needs_user" else "running"
        save_run(run)
        append_event(run, "step_finished", f"{step.id} finished", step_id=step.id)

    def _step_create_draft(self, run: WorkspaceRun) -> None:
        if run.draft_id and run.draft_folder and Path(run.draft_folder).exists():
            return
        result = create_draft(
            text=run.input_text,
            draft_type="adaptive",
            cwd=Path(run.cwd) if run.cwd else self.cwd,
            no_llm=True,
        )
        run.draft_id = result.id
        run.draft_folder = str(result.folder)
        run.final_text = result.final_text
        assert self.session is not None
        self.session.draft_id = result.id
        save_session(self.session)
        save_run(run)

    def _step_write_context(self, run: WorkspaceRun) -> None:
        folder = _draft_folder(run)
        missing = [name for name in ["13_context_bundle.md", "13_context_bundle.json", "14_llm_request.md"] if not (folder / name).exists()]
        if missing:
            raise RuntimeError(f"missing context artifacts: {', '.join(missing)}")

    def _step_write_format_decision(self, run: WorkspaceRun) -> None:
        folder = _draft_folder(run)
        if not (folder / "FORMAT_DECISION.md").exists():
            raise RuntimeError("FORMAT_DECISION.md missing")

    def _step_prepare_codex_contract(self, run: WorkspaceRun) -> None:
        folder = _draft_folder(run)
        (run.path / "AGENTS.md").write_text(agents_contract(), encoding="utf-8")
        (run.path / "TASK.md").write_text(task_contract(run, folder), encoding="utf-8")
        (run.path / "OUTPUT_SCHEMA.md").write_text(output_schema_contract(), encoding="utf-8")
        (run.path / "DRAFT_FOLDER.txt").write_text(str(folder) + "\n", encoding="utf-8")

    def _step_run_codex(self, run: WorkspaceRun) -> None:
        folder = _draft_folder(run)
        config = load_config(self.workspace.root)
        append_event(run, "codex_started", "Codex generation started", step_id="run_codex")
        result = run_llm(
            "codex",
            folder / "14_llm_request.md",
            folder,
            config,
            require_llm=False,
            progress_callback=lambda message: append_event(run, "codex_progress", message, step_id="run_codex"),
        )
        if result.attempted:
            (folder / "15_llm_raw_output.md").write_text(result.raw_output, encoding="utf-8")
        if not result.ok:
            write_interface_summary(run, folder, final_text=run.final_text or "", problem=result.message)
            write_artifacts(run, folder)
            append_event(run, "codex_finished", result.message, step_id="run_codex", severity="error")
            raise RuntimeError(result.message)
        final = apply_llm_result(run, folder, result.parsed.data)
        write_interface_summary(run, folder, final_text=final)
        write_artifacts(run, folder)
        append_event(run, "codex_finished", "Codex generation finished", step_id="run_codex")

    def _step_load_output_protocol(self, run: WorkspaceRun) -> None:
        loaded = load_interface_summary(run.path)
        for warning in loaded.warnings:
            append_event(run, "summary_loaded", warning, step_id="load_output_protocol", severity="warning")
        if not loaded.markdown and loaded.data is None:
            raise RuntimeError("interface summary missing")
        append_event(run, "summary_loaded", "Interface summary loaded", step_id="load_output_protocol")

    def _step_mark_needs_user(self, run: WorkspaceRun) -> None:
        assert self.session is not None
        self.session.status = "active"
        self.session.internal_status = "needs_user"
        save_session(self.session)
        append_event(run, "needs_user", "Ready for next user command", step_id="mark_needs_user")


def _help_text() -> str:
    return """Команды MVP:
/draft <text>
/continue
/continue --run
/status
/runs
/path
/help
/exit"""


def _draft_folder(run: WorkspaceRun) -> Path:
    if not run.draft_folder:
        raise RuntimeError("draft folder is not ready")
    folder = Path(run.draft_folder)
    if not folder.exists():
        raise RuntimeError(f"draft folder missing: {folder}")
    return folder


def _now() -> str:
    from .utils import iso_now

    return iso_now()
