from __future__ import annotations

from pathlib import Path

from .db import connect_db, upsert_fts
from .identity_artifacts import style_build, write_style_stats
from .identity_context import DEFAULT_IDENTITY_PROFILE
from .review import contains_forbidden_phrase
from .utils import iso_now, short_hash


def _processed_style_risk_flags(text: str) -> list[str]:
    lowered = text.lower()
    flags: list[str] = []
    if contains_forbidden_phrase(text):
        flags.append("generic_or_gpt_like")
    if any(term in lowered for term in ["alpha", "100x", "airdrop", "easy money", "buy now"]):
        flags.append("crypto_shill_or_fomo")
    if any(term in lowered for term in ["not financial advice", "buy ", "sell ", "long ", "short "]):
        flags.append("financial_advice_marker")
    if len(text.strip()) < 20:
        flags.append("too_short")
    if text.count("[URL]") > 2 or lowered.count("#") > 4:
        flags.append("too_link_or_hashtag_heavy")
    return flags


def _safe_processed_style_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def style_learn(profile_name: str = DEFAULT_IDENTITY_PROFILE) -> Path:
    path = style_build(profile_name)
    now = iso_now()
    candidates: list[dict[str, str]] = []
    with connect_db() as conn:
        draft_rows = conn.execute(
            """
            select id, created_at, final_text, status
            from drafts
            where status in ('ready', 'posted')
              and final_text is not null
              and trim(final_text) != ''
            order by updated_at desc, created_at desc
            """
        ).fetchall()
        post_rows = conn.execute(
            """
            select id, created_at, text, source_draft_id
            from posts
            where text is not null
              and trim(text) != ''
            order by created_at desc, rowid desc
            """
        ).fetchall()

        for row in draft_rows:
            candidates.append(
                {
                    "source_kind": "approved_draft",
                    "source_id": row["id"],
                    "source_draft_id": row["id"],
                    "created_at": row["created_at"] or now,
                    "text": row["final_text"] or "",
                    "reason": f"draft status is {row['status']}",
                }
            )
        for row in post_rows:
            candidates.append(
                {
                    "source_kind": "posted_post",
                    "source_id": row["id"],
                    "source_draft_id": row["source_draft_id"] or "",
                    "created_at": row["created_at"] or now,
                    "text": row["text"] or "",
                    "reason": "own post stored in posts table",
                }
            )

        conn.execute("delete from processed_style_examples where profile_name = ?", (profile_name,))
        conn.execute("delete from processed_style_examples_fts where profile_name = ?", (profile_name,))

        learned: list[dict[str, str]] = []
        rejected: list[dict[str, str]] = []
        seen_hashes: set[str] = set()
        for candidate in candidates:
            text = _safe_processed_style_text(candidate["text"])
            text_hash = short_hash(text, 16)
            risk_flags = _processed_style_risk_flags(text)
            if text_hash in seen_hashes:
                continue
            seen_hashes.add(text_hash)
            if risk_flags:
                rejected.append({**candidate, "text": text, "risk_flags": ", ".join(risk_flags)})
                continue
            learned.append({**candidate, "text": text, "text_hash": text_hash, "risk_flags": ""})

        for item in learned:
            example_id = f"{profile_name}:processed:{item['text_hash']}"
            conn.execute(
                """
                insert into processed_style_examples(
                  id, profile_name, source_kind, source_id, source_draft_id, created_at,
                  text, text_hash, label, reason, risk_flags, imported_at
                ) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    example_id,
                    profile_name,
                    item["source_kind"],
                    item["source_id"],
                    item["source_draft_id"],
                    item["created_at"],
                    item["text"],
                    item["text_hash"],
                    "processed_post_gold",
                    item["reason"],
                    item["risk_flags"],
                    now,
                ),
            )
            upsert_fts(
                conn,
                "processed_style_examples_fts",
                (example_id, profile_name, item["text"], "processed_post_gold"),
            )

    examples_path = path / "post_gold_examples.md"
    examples_path.write_text(
        "# Post Gold Examples\n\n"
        + (
            "\n\n".join(
                f"## {item['source_kind']} {item['source_id']}\n\n{item['text']}"
                for item in learned
            )
            or "- none"
        )
        + "\n",
        encoding="utf-8",
    )
    report_path = path / "processed_posts_report.md"
    report_path.write_text(
        f"""# Processed Posts Report

- profile: {profile_name}
- mode: approved own texts
- accepted: {len(learned)}
- rejected_by_risk: {len(rejected)}
- rule: ready and posted are treated as approved own writing
- rule: rejected and plain draft texts are not imported
- rule: peer/source/X-read external material is not user style

## Accepted Sources
{chr(10).join(f"- {item['source_kind']} {item['source_id']}: {item['reason']}" for item in learned) if learned else "- none"}

## Rejected By Risk
{chr(10).join(f"- {item['source_kind']} {item['source_id']}: {item['risk_flags']}" for item in rejected) if rejected else "- none"}
""",
        encoding="utf-8",
    )
    write_style_stats(profile_name)
    return report_path
