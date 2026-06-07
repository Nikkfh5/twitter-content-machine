from __future__ import annotations

import re


URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
ADDRESS_RE = re.compile(r"\b(?:0x[a-fA-F0-9]{32,}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-zA-HJ-NP-Z0-9]{20,})\b")
LONG_ID_RE = re.compile(r"\b[a-zA-Z0-9_-]{40,}\b")
HANDLE_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{2,32}")


def sanitize_public_text(text: str) -> str:
    result = URL_RE.sub("[URL]", text)
    result = ADDRESS_RE.sub("[ADDRESS]", result)
    result = LONG_ID_RE.sub("[ID_OR_ADDRESS]", result)
    result = HANDLE_RE.sub("@HANDLE", result)
    return result.strip()


def risk_flags(text: str, source_role: str) -> list[str]:
    lowered = text.lower()
    flags: list[str] = []
    if source_role == "forwarded_other":
        flags.append("not_own_text_default_exclude")
    if "[ADDRESS]" in text or "[ID_OR_ADDRESS]" in text:
        flags.append("address_or_long_id")
    if any(term in lowered for term in ["alpha", "100x", "easy money", "airdrop", "token", "buy now"]):
        flags.append("crypto_trading_or_shill_risk")
    if any(term in lowered for term in ["buy", "sell", "long", "short", "not financial advice"]):
        flags.append("financial_advice_risk")
    return flags

