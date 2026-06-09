from __future__ import annotations

from pathlib import Path

from .db import connect_db
from .identity_artifacts import style_build, write_style_stats
from .identity_context import profile_dir
from .utils import iso_now


UNCERTAINTY_MARKERS = ["РєР°Р¶РµС‚СЃСЏ", "РґСѓРјР°СЋ", "РІРѕР·РјРѕР¶РЅРѕ", "РїРѕРєР°", "РЅРµ СѓРІРµСЂРµРЅ", "current", "guess"]
REASONING_MARKERS = ["РїРѕС‚РѕРјСѓ С‡С‚Рѕ", "РїРѕ РёС‚РѕРіСѓ", "РІС‹РІРѕРґ", "РІ С‡РµРј СЃСѓС‚СЊ", "because", "broke"]


def _score_auto_example(text: str, reactions: int) -> int:
    lowered = text.lower()
    score = 0
    score += 2 if 60 <= len(text) <= 800 else -2
    score += 2 if any(marker in lowered for marker in UNCERTAINTY_MARKERS) else 0
    score += 2 if any(marker in lowered for marker in REASONING_MARKERS) else 0
    score += 1 if any(marker in lowered for marker in ["СЏ ", "Сѓ РјРµРЅСЏ", "СЃРµР№С‡Р°СЃ", "i "]) else 0
    score += min(reactions, 5)
    score -= lowered.count("[url]") * 2
    score -= 4 if any(term in lowered for term in ["airdrop", "alpha", "100x", "easy money"]) else 0
    return score


def auto_select_examples(profile_name: str, limit: int = 80) -> Path:
    path = profile_dir(profile_name)
    with connect_db() as conn:
        rows = conn.execute(
            """
            select telegram_message_id, source_role, text_clean, reactions, risk_flags, labels, length
            from telegram_messages
            where profile_name = ?
            """,
            (profile_name,),
        ).fetchall()
        conn.execute("delete from identity_style_examples where profile_name = ? and label like 'auto_%'", (profile_name,))
        gold = []
        rejected = []
        neutral = []
        for row in rows:
            text = row["text_clean"] or ""
            flags = row["risk_flags"] or ""
            labels = row["labels"] or ""
            lowered = text.lower()
            allowed_role = row["source_role"] in {"own_original", "own_forwarded_self"}
            risky = any(term in flags for term in ["crypto_trading_or_shill_risk", "financial_advice_risk", "address_or_long_id"])
            risky = risky or any(term in labels.lower() for term in ["private", "reject"])
            risky = risky or any(term in lowered for term in ["referral", "airdrop", "buy now", "100x", "easy money"])
            url_only = text.strip() in {"[URL]", ""} or (text.count("[URL]") >= 1 and len(text) < 80)
            noisy_links = text.count("[URL]") > 2 or lowered.count("#") > 3 or lowered.count("$") > 3
            if not allowed_role or risky or url_only or noisy_links:
                rejected.append(row)
                label = "auto_source_only" if row["source_role"] == "forwarded_other" else "auto_reject"
            else:
                score = _score_auto_example(text, int(row["reactions"] or 0))
                if score >= 4 and len(gold) < limit:
                    gold.append(row)
                    label = "auto_gold"
                else:
                    neutral.append(row)
                    label = "auto_neutral"
            conn.execute(
                "insert or replace into identity_style_examples(id, profile_name, telegram_message_id, label, note, created_at) values(?, ?, ?, ?, ?, ?)",
                (f"{profile_name}:{row['telegram_message_id']}:{label}", profile_name, row["telegram_message_id"], label, "automatic selection", iso_now()),
            )
    (path / "auto_gold_examples.md").write_text(
        "# Auto Gold Examples\n\n" + "\n\n".join(f"## {row['telegram_message_id']}\n\n{row['text_clean']}" for row in gold),
        encoding="utf-8",
    )
    (path / "auto_rejected_examples.md").write_text(
        "# Auto Rejected Examples\n\n" + "\n\n".join(f"## {row['telegram_message_id']} [{row['source_role']}]\n\n{row['text_clean'][:500]}" for row in rejected[:100]),
        encoding="utf-8",
    )
    report = path / "auto_selection_report.md"
    report.write_text(
        f"""# Auto Selection Report

- profile: {profile_name}
- auto_gold: {len(gold)}
- auto_neutral: {len(neutral)}
- auto_rejected_or_source_only: {len(rejected)}
- rule: forwarded_other never becomes auto_gold
""",
        encoding="utf-8",
    )
    write_style_stats(profile_name)
    return report


def style_refresh(profile_name: str) -> Path:
    style_build(profile_name)
    return auto_select_examples(profile_name)
