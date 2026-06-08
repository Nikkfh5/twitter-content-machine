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
    leading = _decode_json_object(text.lstrip())
    if leading is not None:
        return leading

    fenced_candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.IGNORECASE | re.DOTALL)
    first_valid: str | None = None
    for candidate in fenced_candidates:
        decoded = _decode_json_object(candidate.strip())
        if decoded is None:
            continue
        if first_valid is None:
            first_valid = decoded
        if _has_required_keys(decoded):
            return decoded
    if first_valid is not None:
        return first_valid

    first_decoded: str | None = None
    for match in re.finditer(r"\{", text):
        decoded = _decode_json_object(text[match.start() :].lstrip())
        if decoded is None:
            continue
        if first_decoded is None:
            first_decoded = decoded
        if _has_required_keys(decoded):
            return decoded
    return first_decoded


def _decode_json_object(text: str) -> str | None:
    try:
        data, _end = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return json.dumps(data, ensure_ascii=False)


def _has_required_keys(raw: str) -> bool:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and REQUIRED_KEYS <= set(data)


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
