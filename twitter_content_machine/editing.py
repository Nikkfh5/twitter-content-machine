from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import load_config
from .db import connect_db, upsert_fts
from .drafting import get_draft
from .llm import build_codex_invocation_plan, resolve_codex_command
from .state import resolve_active_draft_id, set_current_draft
from .utils import iso_now
from .workspace import ensure_workspace


@dataclass(frozen=True)
class EditResult:
    draft_id: str
    folder: Path
    final_text: str
    revision_path: Path


def edit_draft_with_codex(draft_id: str | None, instruction: str) -> EditResult:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    resolved_id = resolve_active_draft_id(draft_id)
    draft = get_draft(resolved_id)
    folder = Path(draft["folder_path"])
    current = (draft.get("final_text") or "").strip() or _read_optional(folder / "06_final_candidate.md")
    request = _build_edit_request(folder, current, instruction)
    (folder / "17_edit_request.md").write_text(request, encoding="utf-8")

    if not resolve_codex_command(config.llm_codex_command):
        raise RuntimeError(f"{config.llm_codex_command} not found")
    plan = build_codex_invocation_plan(request, folder, config)
    if hasattr(plan.capabilities, "exec_available") and not plan.capabilities.exec_available:
        raise RuntimeError(f"{config.llm_codex_command} exec is not available")

    completed = subprocess.run(
        plan.command,
        cwd=plan.cwd,
        env=plan.env,
        text=True,
        capture_output=True,
        timeout=config.llm_codex_timeout_seconds,
        check=False,
    )
    raw = completed.stdout + ("\n\nSTDERR:\n" + completed.stderr if completed.stderr else "")
    (folder / "18_edit_raw_output.md").write_text(raw, encoding="utf-8")
    final_text, parse_report = _parse_edit_output(raw)
    if completed.returncode != 0:
        parse_report += f"\n- codex_returncode: {completed.returncode}\n"
    if completed.returncode != 0 or not final_text:
        (folder / "19_edit_parse_report.md").write_text(parse_report, encoding="utf-8")
        raise RuntimeError("Codex edit failed")

    revisions = folder / "revisions"
    revisions.mkdir(exist_ok=True)
    number = len(sorted(revisions.glob("*.md"))) + 1
    revision_path = revisions / f"{number:03d}-codex-edit.md"
    revision_path.write_text(final_text + "\n", encoding="utf-8")
    (folder / "06_final_candidate.md").write_text(final_text + "\n", encoding="utf-8")
    now = iso_now()
    with connect_db() as conn:
        conn.execute(
            "insert into draft_revisions(id, draft_id, created_at, revision_number, text, change_note) values(?, ?, ?, ?, ?, ?)",
            (f"{resolved_id}-e{number:03d}", resolved_id, now, number, final_text, instruction),
        )
        conn.execute(
            "update drafts set updated_at = ?, final_text = ? where id = ?",
            (now, final_text, resolved_id),
        )
        upsert_fts(conn, "drafts_fts", (resolved_id, draft["title"], final_text, draft.get("tags") or ""))
    set_current_draft(resolved_id)
    (folder / "19_edit_parse_report.md").write_text(parse_report, encoding="utf-8")
    return EditResult(resolved_id, folder, final_text, revision_path)


def _build_edit_request(folder: Path, current: str, instruction: str) -> str:
    context_parts = []
    for name in ["07_algorithm_review.md", "10_identity_style_review.md", "12_risk_flags.md"]:
        text = _read_optional(folder / name).strip()
        if text:
            context_parts.append(f"## {name}\n{text[:5000]}")
    context = "\n\n".join(context_parts) if context_parts else "No extra review context found."
    return f"""You are editing one draft-only X/Twitter candidate for Nikita.

Never publish. Never call X write APIs. Do not inspect parent repositories.
Use only the context included in this prompt and files in this draft folder.

Current final candidate:
{current}

User edit instruction:
{instruction}

Relevant review context:
{context}

Return only JSON:
{{"final_candidate": "edited text"}}
"""


def _parse_edit_output(raw: str) -> tuple[str, str]:
    data = _extract_json(raw)
    if not data:
        return "", "# Edit Parse Report\n\n- ok: false\n- error: No JSON object found\n"
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        return "", f"# Edit Parse Report\n\n- ok: false\n- error: Invalid JSON: {exc}\n"
    final = str(payload.get("final_candidate", "")).strip()
    if not final:
        return "", "# Edit Parse Report\n\n- ok: false\n- error: Missing final_candidate\n"
    return final, "# Edit Parse Report\n\n- ok: true\n"


def _extract_json(text: str) -> str | None:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _read_optional(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")
