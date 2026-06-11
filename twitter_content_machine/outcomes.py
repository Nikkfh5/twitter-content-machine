from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .db import connect_db
from .utils import iso_now, short_hash


@dataclass(frozen=True)
class OutcomeRecord:
    id: str
    draft_id: str
    handle: str
    action: str
    why_important: str
    audience_cluster: str
    relationship: str
    quality_note: str
    follow_up_needed: bool
    artifact_path: Path


def record_outcome(
    draft_id: str,
    handle: str,
    action: str,
    why_important: str,
    audience_cluster: str = "",
    relationship: str = "",
    quality_note: str = "",
    follow_up_needed: bool = False,
) -> OutcomeRecord:
    handle = _normalize_handle(handle)
    now = iso_now()
    outcome_id = "outcome_" + short_hash("|".join([draft_id, handle, action, why_important, now]), 12)
    folder = _draft_folder(draft_id)
    with connect_db() as conn:
        conn.execute(
            """
            insert into high_value_interactions(
              id, created_at, draft_id, post_id, handle, action, why_important,
              audience_cluster, relationship, quality_note, follow_up_needed
            ) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome_id,
                now,
                draft_id,
                "",
                handle,
                action,
                why_important,
                audience_cluster,
                relationship,
                quality_note,
                1 if follow_up_needed else 0,
            ),
        )
        conn.execute(
            """
            insert into accounts(handle, display_name, cluster, why_important, first_seen, last_interaction, notes)
            values(?, ?, ?, ?, ?, ?, ?)
            on conflict(handle) do update set
              cluster = coalesce(nullif(excluded.cluster, ''), accounts.cluster),
              why_important = coalesce(nullif(excluded.why_important, ''), accounts.why_important),
              last_interaction = excluded.last_interaction,
              notes = coalesce(nullif(excluded.notes, ''), accounts.notes)
            """,
            (handle, "", audience_cluster, why_important, now, now, quality_note),
        )
    artifact = write_outcome_artifact(draft_id)
    return OutcomeRecord(
        id=outcome_id,
        draft_id=draft_id,
        handle=handle,
        action=action,
        why_important=why_important,
        audience_cluster=audience_cluster,
        relationship=relationship,
        quality_note=quality_note,
        follow_up_needed=follow_up_needed,
        artifact_path=artifact,
    )


def list_outcomes(draft_id: str | None = None, limit: int = 50) -> list[dict[str, object]]:
    clauses = []
    params: list[object] = []
    if draft_id:
        clauses.append("draft_id = ?")
        params.append(draft_id)
    where = " where " + " and ".join(clauses) if clauses else ""
    with connect_db() as conn:
        rows = conn.execute(
            f"""
            select id, created_at, draft_id, handle, action, why_important,
              audience_cluster, relationship, quality_note, follow_up_needed
            from high_value_interactions{where}
            order by created_at desc, rowid desc
            limit ?
            """,
            (*params, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def write_outcome_artifact(draft_id: str) -> Path:
    folder = _draft_folder(draft_id)
    rows = list_outcomes(draft_id, limit=200)
    lines = ["# High-Value Interactions", ""]
    if not rows:
        lines.append("- none")
    for row in rows:
        lines.extend(
            [
                f"## {row['created_at']} {row['handle']}",
                "",
                f"- id: {row['id']}",
                f"- draft_id: {row['draft_id']}",
                f"- action: {row['action']}",
                f"- why_important: {row['why_important']}",
                f"- audience_cluster: {row['audience_cluster'] or ''}",
                f"- relationship: {row['relationship'] or ''}",
                f"- quality_note: {row['quality_note'] or ''}",
                f"- follow_up_needed: {'true' if row['follow_up_needed'] else 'false'}",
                "",
            ]
        )
    path = folder / "20_high_value_interactions.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def format_outcome_rows(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "no outcomes"
    lines = []
    for row in rows:
        lines.append(
            f"{row['created_at']}  {row['draft_id']}  {row['handle']}  {row['action']}  {row['why_important']}"
        )
    return "\n".join(lines)


def _draft_folder(draft_id: str) -> Path:
    with connect_db() as conn:
        row = conn.execute("select folder_path from drafts where id = ?", (draft_id,)).fetchone()
    if not row:
        raise ValueError(f"draft not found: {draft_id}")
    return Path(row["folder_path"])


def _normalize_handle(handle: str) -> str:
    stripped = handle.strip()
    if not stripped:
        raise ValueError("handle required")
    return stripped if stripped.startswith("@") else "@" + stripped
