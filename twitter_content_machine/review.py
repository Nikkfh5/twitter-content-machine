from __future__ import annotations

import re


FORBIDDEN_PHRASES = [
    "in today's world",
    "important to note",
    "it is worth mentioning",
    "this highlights",
    "this underscores",
    "game changer",
    "unlock",
    "deep dive",
    "leverage",
    "cutting-edge",
    "revolutionary",
    "here are 5 lessons",
    "everyone should",
    "the future of",
    "i am excited to announce",
]

SECRET_PATTERNS = [
    re.compile(r"(?i)(x_bearer_token|api[_-]?key|secret|token|password)\s*=\s*['\"]?[^'\"\s]+"),
    re.compile(r"(?i)(bearer)\s+[a-z0-9._\-]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def contains_forbidden_phrase(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in FORBIDDEN_PHRASES)


def anti_gpt_pass(text: str) -> str:
    result = text
    replacements = {
        "It is important to note that ": "",
        "important to note that ": "",
        "This highlights ": "",
        "this highlights ": "",
        "This underscores ": "",
        "this underscores ": "",
        "In today's world, ": "",
        "in today's world, ": "",
        "game changer": "useful change",
        "deep dive": "notes",
        "unlock": "make possible",
    }
    for old, new in replacements.items():
        result = result.replace(old, new)
    lines = [line.rstrip() for line in result.splitlines()]
    return redact_secrets("\n".join(lines).strip())


def critique_text(text: str, old_memory: list[dict[str, str]] | None = None) -> str:
    lowered = text.lower()
    issues: list[str] = []
    if len(text.strip()) < 30:
        issues.append("Real point weak: too short to carry an observation.")
    if contains_forbidden_phrase(text):
        issues.append("GPT-like phrasing found. Remove stock phrases.")
    if any(term in lowered for term in ["buy ", "sell ", "signal", "guaranteed return"]):
        issues.append("Financial-advice risk. Remove trading-signal wording.")
    if "[REDACTED_SECRET]" in redact_secrets(text):
        issues.append("Confidentiality risk. Secret-like text was redacted.")
    if old_memory:
        issues.append("Check repetition: similar memory exists; make the new angle concrete.")
    if not issues:
        issues.append("Core point exists. Keep it concrete and avoid over-polishing.")
    return "\n".join(f"- {issue}" for issue in issues)


def score_text(text: str, old_memory: list[dict[str, str]] | None = None) -> str:
    gpt_like = 4 if contains_forbidden_phrase(text) else 1
    advice = 4 if re.search(r"(?i)\b(buy|sell|long|short)\b", text) else 0
    secret = 5 if "[REDACTED_SECRET]" in redact_secrets(text) else 0
    repetition = 3 if old_memory else 1
    real_point = 4 if len(text.split()) >= 8 else 2
    return f"""Review
- real point: {real_point}/5
- too GPT-like: {gpt_like}/5
- overclaim risk: 2/5
- cringe/influencer risk: {gpt_like}/5
- confidentiality risk: {secret}/5
- repetition vs old posts: {repetition}/5
- recommendation: {'revise before using' if max(gpt_like, advice, secret) >= 4 else 'usable as a draft, manually inspect before posting'}
"""
