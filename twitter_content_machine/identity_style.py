from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .db import connect_db, resolve_draft_id
from .review import contains_forbidden_phrase
from .utils import iso_now
from .workspace import ensure_workspace


SUPPORT_FILES = [
    "identity_style_card.md",
    "phrasebank.md",
    "hooks.md",
    "rhythm.md",
    "anti_patterns.md",
    "adaptation_rules.md",
    "self_writing_cheatsheet.md",
]


@dataclass(frozen=True)
class IdentityContext:
    profile_name: str
    strength: float
    style_card: str
    anti_patterns: str
    examples: list[dict[str, str]]
    warnings: list[str]


def profile_dir(profile_name: str) -> Path:
    workspace = ensure_workspace()
    path = workspace.root / "identity_styles" / profile_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read(path: Path, limit: int = 8000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def _get_draft(draft_id: str) -> dict[str, str]:
    resolved = resolve_draft_id(draft_id)
    with connect_db() as conn:
        row = conn.execute("select * from drafts where id = ?", (resolved,)).fetchone()
    if not row:
        raise ValueError(f"Draft not found: {draft_id}")
    return dict(row)


def _eligible_examples(profile_name: str, limit: int = 5) -> list[dict[str, str]]:
    with connect_db() as conn:
        curated = conn.execute(
            """
            select e.telegram_message_id, e.label, m.text_clean, m.source_role
            from identity_style_examples e
            join telegram_messages m
              on m.profile_name = e.profile_name
             and m.telegram_message_id = e.telegram_message_id
            where e.profile_name = ?
              and e.label = 'gold'
              and m.source_role in ('own_original', 'own_forwarded_self')
            limit ?
            """,
            (profile_name, limit),
        ).fetchall()
        rows = curated or conn.execute(
            """
            select telegram_message_id, 'auto' as label, text_clean, source_role
            from telegram_messages
            where profile_name = ?
              and source_role in ('own_original', 'own_forwarded_self')
              and length between 40 and 600
              and risk_flags not like '%crypto_trading_or_shill_risk%'
              and risk_flags not like '%financial_advice_risk%'
            order by reactions desc, length desc
            limit ?
            """,
            (profile_name, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def load_identity_context(profile_name: str, strength: float = 0.35) -> IdentityContext:
    path = profile_dir(profile_name)
    warnings: list[str] = []
    if strength > 0.6:
        warnings.append("identity_strength above 0.6 risks old-channel imitation")
    if strength > 0.35:
        warnings.append("manual review required for stronger identity influence")
    examples = _eligible_examples(profile_name)
    if not examples:
        warnings.append("no eligible own/gold examples found; using style card only")
    return IdentityContext(
        profile_name=profile_name,
        strength=strength,
        style_card=_read(path / "identity_style_card.md"),
        anti_patterns=_read(path / "anti_patterns.md"),
        examples=examples,
        warnings=warnings,
    )


def identity_brief_context(profile_name: str, strength: float) -> str:
    ctx = load_identity_context(profile_name, strength)
    example_lines = [
        f"- {item['telegram_message_id']} ({item['source_role']}): {item['text_clean'][:220]}"
        for item in ctx.examples
    ]
    return f"""Identity/style profile: {profile_name}
Identity strength: {strength}

Rules:
- preserve directness, rhythm, roughness, skepticism, and concrete mechanics
- do not copy old examples verbatim
- do not imitate forwarded_other content
- remove crypto shilling, airdrop instructions, price calls, guru tone

Style card:
{ctx.style_card[:2500]}

Anti-patterns:
{ctx.anti_patterns[:1600]}

Eligible examples:
{chr(10).join(example_lines) if example_lines else "- none"}

Warnings:
{chr(10).join(f"- {warning}" for warning in ctx.warnings) if ctx.warnings else "- none"}
"""


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
