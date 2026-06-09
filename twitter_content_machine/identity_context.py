from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .db import connect_db, resolve_draft_id
from .workspace import ensure_workspace


DEFAULT_IDENTITY_PROFILE = "tg_crypto_clean"

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
        processed = conn.execute(
            """
            select source_id as telegram_message_id,
                   label,
                   text as text_clean,
                   source_kind as source_role
            from processed_style_examples
            where profile_name = ?
              and label = 'processed_post_gold'
            order by created_at desc, rowid desc
            limit ?
            """,
            (profile_name, max(1, min(3, limit))),
        ).fetchall()
        curated = conn.execute(
            """
            select e.telegram_message_id, e.label, m.text_clean, m.source_role
            from identity_style_examples e
            join telegram_messages m
              on m.profile_name = e.profile_name
             and m.telegram_message_id = e.telegram_message_id
            where e.profile_name = ?
              and e.label in ('gold', 'auto_gold')
              and m.source_role in ('own_original', 'own_forwarded_self')
            limit ?
            """,
            (profile_name, limit),
        ).fetchall()
        rows = list(processed) + list(curated)
        if len(rows) < limit:
            fallback = conn.execute(
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
                (profile_name, limit - len(rows)),
            ).fetchall()
            rows.extend(fallback)
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        key = (item.get("text_clean") or "")[:160]
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:limit]


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
