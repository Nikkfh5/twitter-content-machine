from __future__ import annotations

import json
from pathlib import Path

from .db import connect_db
from .review import anti_gpt_pass
from .runs import WorkspaceRun, save_run


def apply_llm_result(run: WorkspaceRun, folder: Path, data: dict) -> str:
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


def write_interface_summary(run: WorkspaceRun, folder: Path, final_text: str, problem: str = "") -> None:
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


def write_artifacts(run: WorkspaceRun, folder: Path) -> None:
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


def agents_contract() -> str:
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


def task_contract(run: WorkspaceRun, folder: Path) -> str:
    return f"""# Task

Run id: {run.id}
Draft folder: {folder}

Use the existing draft context:
- `{folder / "13_context_bundle.md"}`
- `{folder / "14_llm_request.md"}`
- `{folder / "FORMAT_DECISION.md"}`

Generate or improve the final candidate. Keep draft-only safety.
"""


def output_schema_contract() -> str:
    return """# Output Schema

Required workspace protocol:
- `interface_summary.md` in Russian
- `interface_summary.json`
- optional semantic appends to `events.jsonl`

The interface summary must cover: meaning, audience, who will ignore it,
problems, fixes, decisions, files, and next commands.
"""


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


def _short_summary(text: str) -> str:
    clean = " ".join(text.split())
    if not clean:
        return "Черновик подготовлен, но итоговый текст пустой."
    return clean[:240] + ("..." if len(clean) > 240 else "")
