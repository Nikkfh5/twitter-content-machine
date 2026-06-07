from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedLLMOutput:
    ok: bool
    data: dict[str, Any]
    error: str


REQUIRED_KEYS = {"variants", "critique", "selected_variant_id", "final_candidate", "media_suggestion", "manual_notes"}


def _extract_json(text: str) -> str | None:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def parse_llm_output(text: str) -> ParsedLLMOutput:
    raw = _extract_json(text)
    if raw is None:
        return ParsedLLMOutput(False, {}, "No JSON object found")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return ParsedLLMOutput(False, {}, f"Invalid JSON: {exc}")
    missing = REQUIRED_KEYS - set(data)
    if missing:
        return ParsedLLMOutput(False, data if isinstance(data, dict) else {}, f"Missing keys: {', '.join(sorted(missing))}")
    return ParsedLLMOutput(True, data, "")
