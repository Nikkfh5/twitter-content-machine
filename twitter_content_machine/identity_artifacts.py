from __future__ import annotations

from pathlib import Path

from .db import connect_db
from .identity_context import _get_draft, load_identity_context, profile_dir
from .review import contains_forbidden_phrase
from .utils import iso_now


def style_build(profile_name: str) -> Path:
    path = profile_dir(profile_name)
    with connect_db() as conn:
        rows = conn.execute(
            """
            select text_clean, source_role, risk_flags
            from telegram_messages
            where profile_name = ?
              and source_role in ('own_original', 'own_forwarded_self')
              and length > 0
            order by date
            """,
            (profile_name,),
        ).fetchall()
    texts = [row["text_clean"] for row in rows]
    avg_len = int(sum(len(text) for text in texts) / max(1, len(texts)))
    if not (path / "identity_style_card.md").exists():
        (path / "identity_style_card.md").write_text(
            f"""# Identity Style Card

Profile: {profile_name}

- direct
- rough but alive
- observation-first
- skeptical toward hype
- thinks in bets, risks, and assumptions
- comfortable with uncertainty
- average cleaned message length: {avg_len}

Use this as adaptation input, not imitation.
""",
            encoding="utf-8",
        )
    generated = {
        "phrasebank.md": "# Phrasebank\n\n- current guess\n- the annoying part is\n- I used to think\n- this broke because\n",
        "hooks.md": "# Hooks\n\n- Small note from building:\n- I used to think X. Now Y.\n- This broke in a boring place:\n",
        "rhythm.md": f"# Rhythm\n\n- eligible own messages: {len(texts)}\n- average length: {avg_len}\n- prefer short paragraphs and concrete mechanics\n",
        "anti_patterns.md": "# Anti Patterns\n\n- token shilling\n- airdrop instructions\n- urgent FOMO\n- direct price calls\n- forwarded posts as own style\n",
        "adaptation_rules.md": "# Adaptation Rules\n\nKeep directness and risk-thinking. Remove crypto action tone, shilling, and guru certainty.\n",
        "self_writing_cheatsheet.md": "# Self Writing Cheatsheet\n\n1. Name what broke.\n2. Name the assumption.\n3. Keep uncertainty if true.\n4. Remove advice tone.\n",
    }
    for name, content in generated.items():
        target = path / name
        if not target.exists() or target.stat().st_size == 0:
            target.write_text(content, encoding="utf-8")
    with connect_db() as conn:
        conn.execute(
            """
            insert into identity_style_profiles(profile_name, created_at, updated_at, summary, default_strength, status)
            values(?, ?, ?, ?, ?, ?)
            on conflict(profile_name) do update set
              updated_at=excluded.updated_at,
              summary=excluded.summary,
              default_strength=excluded.default_strength,
              status=excluded.status
            """,
            (
                profile_name,
                iso_now(),
                iso_now(),
                f"Identity/style profile built from {len(texts)} eligible own messages.",
                0.35,
                "built",
            ),
        )
    return path


def write_style_stats(profile_name: str) -> Path:
    path = profile_dir(profile_name)
    with connect_db() as conn:
        rows = conn.execute(
            "select source_role, count(*) as n from telegram_messages where profile_name = ? group by source_role",
            (profile_name,),
        ).fetchall()
        labels = conn.execute(
            "select label, count(*) as n from identity_style_examples where profile_name = ? group by label",
            (profile_name,),
        ).fetchall()
        processed_labels = conn.execute(
            "select label, count(*) as n from processed_style_examples where profile_name = ? group by label",
            (profile_name,),
        ).fetchall()
    text = "# Style Stats\n\n## Source Roles\n" + "\n".join(f"- {row['source_role']}: {row['n']}" for row in rows)
    text += "\n\n## Labels\n" + ("\n".join(f"- {row['label']}: {row['n']}" for row in labels) or "- none")
    text += "\n\n## Processed Own Posts\n" + (
        "\n".join(f"- {row['label']}: {row['n']}" for row in processed_labels) or "- none"
    )
    target = path / "style_stats.md"
    target.write_text(text + "\n", encoding="utf-8")
    return target


def style_curate(profile_name: str, limit: int = 50) -> Path:
    path = profile_dir(profile_name)
    with connect_db() as conn:
        rows = conn.execute(
            """
            select telegram_message_id, source_role, text_clean
            from telegram_messages
            where profile_name = ?
              and source_role in ('own_original', 'own_forwarded_self')
              and length between 40 and 600
            order by reactions desc, length desc
            limit ?
            """,
            (profile_name, limit),
        ).fetchall()
    target = path / "curated" / "curation_queue.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Curation Queue",
        "",
        "Labels: gold, neutral, anti, reject, private, source_only.",
        "Private/reject never used. Forwarded_other excluded by default.",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"## {row['telegram_message_id']} [{row['source_role']}]",
                "",
                "label: neutral",
                "",
                row["text_clean"][:1000],
                "",
            ]
        )
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def style_review(draft_id: str, profile_name: str = "tg_crypto_clean", strength: float = 0.35) -> Path:
    draft = _get_draft(draft_id)
    folder = Path(draft["folder_path"])
    final = (folder / "06_final_candidate.md").read_text(encoding="utf-8", errors="replace")
    ctx = load_identity_context(profile_name, strength)
    lowered = final.lower()
    risks: list[str] = []
    if contains_forbidden_phrase(final):
        risks.append("too GPT-like")
    if any(term in lowered for term in ["alpha", "100x", "airdrop", "easy money"]):
        risks.append("too old-crypto-channel-like")
    if any(term in lowered for term in ["buy", "sell", "long", "short", "not financial advice"]):
        risks.append("financial advice risk")
    if len(final.split()) > 120:
        risks.append("too long / too polished")
    if not risks:
        risks.append("no major identity/style risk found")
    text = f"""# Identity Style Review

Profile:
- {profile_name}

Identity strength:
- {strength}

Does it sound like the user?
- partially; manual final check still required

Too GPT-like?
- {"yes" if contains_forbidden_phrase(final) else "no"}

Too old-crypto-channel-like?
- {"yes" if any(term in lowered for term in ["alpha", "100x", "airdrop", "easy money"]) else "no"}

Mismatch with current X positioning?
- {"yes" if any(term in lowered for term in ["airdrop", "token shilling"]) else "no"}

Warnings:
{chr(10).join(f"- {warning}" for warning in ctx.warnings) if ctx.warnings else "- none"}

Risk flags:
{chr(10).join(f"- {risk}" for risk in risks)}

Recommendation:
- revise if any high-risk crypto/advice marker appears; otherwise usable as draft input
"""
    path = folder / "10_identity_style_review.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_identity_artifacts(draft_id: str, profile_name: str, strength: float = 0.35) -> dict[str, Path]:
    draft = _get_draft(draft_id)
    folder = Path(draft["folder_path"])
    ctx = load_identity_context(profile_name, strength)
    review_path = style_review(draft_id, profile_name, strength)
    examples_lines = ["# Examples Used", "", f"Profile: {profile_name}", ""]
    for item in ctx.examples:
        examples_lines.extend(
            [
                f"## {item['telegram_message_id']} [{item['source_role']}]",
                "",
                item["text_clean"][:1000],
                "",
            ]
        )
    examples_path = folder / "11_examples_used.md"
    examples_path.write_text("\n".join(examples_lines), encoding="utf-8")
    final = (folder / "06_final_candidate.md").read_text(encoding="utf-8", errors="replace")
    risk_items = list(ctx.warnings)
    if any(term in final.lower() for term in ["alpha", "100x", "airdrop", "easy money"]):
        risk_items.append("old crypto / shill marker found")
    if any(term in final.lower() for term in ["buy", "sell", "long", "short"]):
        risk_items.append("financial advice marker found")
    risk_path = folder / "12_risk_flags.md"
    risk_path.write_text(
        "# Risk Flags\n\n"
        + (("\n".join(f"- {item}" for item in risk_items)) if risk_items else "- none")
        + "\n",
        encoding="utf-8",
    )
    return {
        "identity_style_review": review_path,
        "examples_used": examples_path,
        "risk_flags": risk_path,
    }
