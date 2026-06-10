from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import load_config
from .db import connect_db
from .drafting import create_draft
from .llm import run_llm
from .output_protocol import load_interface_summary
from .review import anti_gpt_pass
from .runs import (
    RunStep,
    WorkspaceRun,
    append_event,
    create_run,
    load_run,
    next_unfinished_step,
    pending_codex_step,
    read_events,
    save_run,
)
from .sessions import ContentSession, create_session, find_resumable_session, load_session, save_session
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
            return WorkspaceCommandResult(False, "Команды MVP начинаются с slash. Попробуй: /draft <текст>", self.session)
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
            return "Пустой workspace.\n\nКоманда: /draft <идея>"
        run = self._current_run()
        if run is None:
            return self.status().message
        loaded = load_interface_summary(run.path)
        if loaded.markdown:
            return loaded.markdown
        return self.status().message + "\n\n" + _timeline_text(run)

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
        (run.path / "AGENTS.md").write_text(_agents_contract(), encoding="utf-8")
        (run.path / "TASK.md").write_text(_task_contract(run, folder), encoding="utf-8")
        (run.path / "OUTPUT_SCHEMA.md").write_text(_output_schema_contract(), encoding="utf-8")
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
            _write_interface_summary(run, folder, final_text=run.final_text or "", problem=result.message)
            _write_artifacts(run, folder)
            append_event(run, "codex_finished", result.message, step_id="run_codex", severity="error")
            raise RuntimeError(result.message)
        final = _apply_llm_result(run, folder, result.parsed.data)
        _write_interface_summary(run, folder, final_text=final)
        _write_artifacts(run, folder)
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


def _apply_llm_result(run: WorkspaceRun, folder: Path, data: dict) -> str:
    variants = data.get("variants", [])
    variants_text = "# Variants\n\n" + "\n\n".join(
        f"## Variant {item.get('id', '')}: {item.get('name', '')}\n{item.get('text', '')}\n\nIntent: {item.get('intent', '')}\nWhy: {item.get('why_it_might_work', '')}\nRisks: {', '.join(item.get('risks', []))}"
        for item in variants
    )
    critique = data.get("critique", {})
    critique_text = "# Critique\n\n" + "\n".join(f"- {key}: {value}" for key, value in critique.items())
    selected_id = data.get("selected_variant_id", "A")
    selected_text = next((item.get("text", "") for item in variants if item.get("id") == selected_id), data.get("final_candidate", ""))
    final = anti_gpt_pass(str(data.get("final_candidate", selected_text)))
    (folder / "03_variants.md").write_text(variants_text.strip() + "\n", encoding="utf-8")
    (folder / "04_critique.md").write_text(critique_text.strip() + "\n", encoding="utf-8")
    (folder / "05_selected.md").write_text(f"# Selected\n\n{selected_text}\n", encoding="utf-8")
    (folder / "06_final_candidate.md").write_text(final + "\n", encoding="utf-8")
    if run.draft_id:
        with connect_db() as conn:
            conn.execute(
                "update drafts set final_text = ?, selected_variant = ? where id = ?",
                (final, selected_id, run.draft_id),
            )
    run.final_text = final
    save_run(run)
    return final


def _write_interface_summary(run: WorkspaceRun, folder: Path, final_text: str, problem: str = "") -> None:
    files = [
        {"label": "session", "path": str(run.path.parent.parent)},
        {"label": "run", "path": str(run.path)},
        {"label": "draft", "path": str(folder)},
        {"label": "final_candidate", "path": str(folder / "06_final_candidate.md")},
    ]
    problems = [problem] if problem else ["Проверь, не звучит ли текст слишком общо.", "Проверь, хватает ли конкретного примера."]
    fixes = ["Открыть draft folder и отредактировать final candidate вручную."] if problem else ["Если мысль размазана, ужать до одного наблюдения.", "Если нужен тред, разнести части по отдельным постам."]
    data = {
        "language": "ru",
        "summary": _short_summary(final_text or run.input_text),
        "audience": ["инженеры, которые пишут публичные build logs", "люди, которым интересны проверки, баги и рабочие заметки"],
        "not_for": ["аудитория, ожидающая готовый туториал или громкий вывод"],
        "problems": problems,
        "fixes": fixes,
        "decisions": [
            {
                "name": "format",
                "value": "adaptive",
                "reason": "Формат выбран existing draft pipeline; workspace хранит resume state отдельно.",
            },
            {
                "name": "safety",
                "value": "draft_only",
                "reason": "MVP не публикует и не вызывает X write APIs.",
            },
        ],
        "files": files,
        "next_commands": [
            {"command": "/path", "reason": "посмотреть session, run и draft папки"},
            {"command": "/runs", "reason": "проверить steps и resume state"},
        ],
    }
    (run.path / "interface_summary.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (run.path / "interface_summary.md").write_text(_summary_markdown(data), encoding="utf-8")


def _write_artifacts(run: WorkspaceRun, folder: Path) -> None:
    required = {
        "final_candidate": folder / "06_final_candidate.md",
        "interface_summary_md": run.path / "interface_summary.md",
        "interface_summary_json": run.path / "interface_summary.json",
    }
    created = [{"label": label, "path": str(path), "required": True} for label, path in required.items() if path.exists()]
    missing = [{"label": label, "path": str(path), "required": True} for label, path in required.items() if not path.exists()]
    (run.path / "artifacts.json").write_text(
        json.dumps({"created": created, "missing": missing}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _summary_markdown(data: dict) -> str:
    def bullet(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "- нет"

    return f"""# Interface Summary

## Кратко
{data["summary"]}

## Для кого
{bullet(data["audience"])}

## Кому не зайдет
{bullet(data["not_for"])}

## Проблемы
{bullet(data["problems"])}

## Как исправить
{bullet(data["fixes"])}

## Основные решения
{bullet([f'{item["name"]}: {item["value"]} — {item["reason"]}' for item in data["decisions"]])}

## Файлы
{bullet([f'{item["label"]}: {item["path"]}' for item in data["files"]])}

## Next Commands
{bullet([f'{item["command"]} — {item["reason"]}' for item in data["next_commands"]])}
"""


def _timeline_text(run: WorkspaceRun) -> str:
    events = read_events(run)
    if not events:
        return "Timeline пуст."
    return "\n".join(f"{event.get('ts', '')} {event.get('type', '')}: {event.get('message', '')}" for event in events[-12:])


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


def _short_summary(text: str) -> str:
    clean = " ".join(text.split())
    if not clean:
        return "Черновик подготовлен, но итоговый текст пустой."
    return clean[:240] + ("..." if len(clean) > 240 else "")


def _now() -> str:
    from .utils import iso_now

    return iso_now()


def _agents_contract() -> str:
    return """# Content Workspace Codex Contract

You are producing draft X/Twitter content for Nikita.

Hard rules:
- Draft only. Never publish.
- Never call X write APIs.
- Do not add browser automation that clicks Post.
- Do not read `.env`, tokens, keys, credentials, or private logs.
- Do not modify source project files.
- Do not inspect parent repositories unless explicitly included as safe context.
- Write content artifacts only in the draft folder or this run folder.
"""


def _task_contract(run: WorkspaceRun, folder: Path) -> str:
    return f"""# Task

Run id: {run.id}
Draft folder: {folder}

Use the existing draft context:
- `{folder / "13_context_bundle.md"}`
- `{folder / "14_llm_request.md"}`
- `{folder / "FORMAT_DECISION.md"}`

Generate or improve the final candidate. Keep draft-only safety.
"""


def _output_schema_contract() -> str:
    return """# Output Schema

Required workspace protocol:
- `interface_summary.md` in Russian
- `interface_summary.json`
- optional semantic appends to `events.jsonl`

The interface summary must cover: meaning, audience, who will ignore it,
problems, fixes, decisions, files, and next commands.
"""
