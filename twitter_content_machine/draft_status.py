from __future__ import annotations

from pathlib import Path

from .db import connect_db, resolve_draft_id, search_memory, upsert_fts
from .draft_fallbacks import _variant_thread
from .models import DraftResult
from .review import anti_gpt_pass, score_text
from .utils import iso_now, short_hash


def get_draft(draft_id: str) -> dict[str, str]:
    resolved = resolve_draft_id(draft_id)
    with connect_db() as conn:
        row = conn.execute("select * from drafts where id = ?", (resolved,)).fetchone()
    if not row:
        raise ValueError(f"Draft not found: {draft_id}")
    return dict(row)


def refine_draft(draft_id: str, instruction: str = "human") -> DraftResult:
    draft = get_draft(draft_id)
    folder = Path(draft["folder_path"])
    revisions = folder / "revisions"
    revisions.mkdir(exist_ok=True)
    existing = sorted(revisions.glob("*.md"))
    number = len(existing) + 1
    source = draft["final_text"] or (folder / "06_final_candidate.md").read_text(encoding="utf-8")
    if instruction in {"human", "critique"}:
        refined = anti_gpt_pass(source).replace("Current guess:", "Current guess:")
    elif instruction == "shorten":
        refined = " ".join(source.split()[:45])
    elif instruction == "thread":
        refined = _variant_thread(source.splitlines()[0][:180])
    elif instruction == "clarify":
        refined = source + "\n\nClarify before posting: what exact assumption changed?"
    else:
        refined = anti_gpt_pass(source)
    rev_path = revisions / f"{number:03d}.md"
    rev_path.write_text(refined + "\n", encoding="utf-8")
    (folder / "06_final_candidate.md").write_text(refined + "\n", encoding="utf-8")
    now = iso_now()
    resolved = draft["id"]
    with connect_db() as conn:
        conn.execute(
            "insert into draft_revisions(id, draft_id, created_at, revision_number, text, change_note) values(?, ?, ?, ?, ?, ?)",
            (f"{resolved}-r{number:03d}", resolved, now, number, refined, instruction),
        )
        conn.execute(
            "update drafts set updated_at = ?, final_text = ? where id = ?",
            (now, refined, resolved),
        )
        upsert_fts(conn, "drafts_fts", (resolved, draft["title"], refined, draft.get("tags") or ""))
    return DraftResult(resolved, folder, refined)


def review_draft(draft_id: str) -> str:
    draft = get_draft(draft_id)
    memory = search_memory(draft["final_text"] or "", limit=5)
    return score_text(draft["final_text"] or "", memory)


def set_draft_status(draft_id: str, status: str, url: str | None = None) -> None:
    draft = get_draft(draft_id)
    with connect_db() as conn:
        conn.execute("update drafts set status = ?, updated_at = ? where id = ?", (status, iso_now(), draft["id"]))
        if status == "posted":
            post_id = f"manual_{short_hash((url or '') + draft['id'], 10)}"
            conn.execute(
                "insert or ignore into posts(id, created_at, platform, platform_post_id, url, text, thread_id, project_id, source_draft_id, tags) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (post_id, iso_now(), "x", post_id, url or "", draft["final_text"] or "", "", draft["project_id"], draft["id"], ""),
            )
            upsert_fts(conn, "posts_fts", (post_id, draft["final_text"] or "", ""))
