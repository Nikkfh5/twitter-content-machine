from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class FormatDecision:
    requested_format: str
    best_format: str
    decision_source: str
    content_density: str
    target_audience: str
    expected_primary_action: str
    length_range: str
    reasoning: str
    why_not_other_formats: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


EXPLICIT_FORMATS = {"short", "thread", "article-note", "build-log", "question"}


def decide_format(raw_input: str, requested_format: str, project_summary: str = "", source_url: str | None = None) -> FormatDecision:
    requested = requested_format or "adaptive"
    density = _content_density(raw_input)
    if requested in EXPLICIT_FORMATS:
        best = requested
        source = "explicit-user-format"
        reasoning = f"User explicitly selected {requested}."
    else:
        best, reasoning = _adaptive_format(raw_input, source_url)
        source = "adaptive-heuristic"
    return FormatDecision(
        requested_format=requested,
        best_format=best,
        decision_source=source,
        content_density=density,
        target_audience=_target_audience(raw_input + "\n" + project_summary),
        expected_primary_action=_expected_action(best),
        length_range=_length_range(best),
        reasoning=reasoning,
        why_not_other_formats=_why_not_other_formats(best),
    )


def write_format_decision(path: Path, decision: FormatDecision) -> Path:
    data = decision.to_dict()
    lines = [
        "# Format Decision",
        "",
        f"requested_format: {data['requested_format']}",
        f"best_format: {data['best_format']}",
        f"decision_source: {data['decision_source']}",
        f"content_density: {data['content_density']}",
        f"target_audience: {data['target_audience']}",
        f"expected_primary_action: {data['expected_primary_action']}",
        f"length_range: {data['length_range']}",
        "",
        "## Reasoning",
        str(data["reasoning"]),
        "",
        "## Why Not Other Formats",
    ]
    for name, reason in decision.why_not_other_formats.items():
        lines.append(f"- {name}: {reason}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def format_decision_brief(decision: FormatDecision | dict[str, object] | None) -> str:
    if decision is None:
        return "No format decision recorded."
    data = decision.to_dict() if isinstance(decision, FormatDecision) else decision
    why_not = data.get("why_not_other_formats", {})
    why_lines = []
    if isinstance(why_not, dict):
        why_lines = [f"- {key}: {value}" for key, value in why_not.items()]
    return "\n".join(
        [
            f"requested_format: {data.get('requested_format', '')}",
            f"best_format: {data.get('best_format', '')}",
            f"decision_source: {data.get('decision_source', '')}",
            f"content_density: {data.get('content_density', '')}",
            f"target_audience: {data.get('target_audience', '')}",
            f"expected_primary_action: {data.get('expected_primary_action', '')}",
            f"length_range: {data.get('length_range', '')}",
            f"reasoning: {data.get('reasoning', '')}",
            "why_not_other_formats:",
            *(why_lines or ["- none"]),
        ]
    )


def _content_density(text: str) -> str:
    bullets = len(re.findall(r"(?m)^\s*[-*]\s+", text))
    words = re.findall(r"\w+", text)
    if len(words) >= 120 or bullets >= 4:
        return "high"
    if len(words) >= 35 or bullets >= 2 or "\n" in text.strip():
        return "medium"
    return "low"


def _adaptive_format(text: str, source_url: str | None) -> tuple[str, str]:
    lowered = text.lower()
    if "?" in text or any(term in lowered for term in ["what should", "how would", "which option", "does anyone"]):
        return "question", "Input asks for bounded input or contains a direct question."
    if source_url or any(term in lowered for term in ["paper", "article", "read ", "reading", "source note"]):
        return "article-note", "Input reacts to a source, paper, or article."
    if any(term in lowered for term in ["build log", "built", "fixed", "broke", "debug", "implemented", "refactor", "validation bug", "what broke"]):
        return "build-log", "Input describes project work, a breakage, or an implementation check."
    bullets = len(re.findall(r"(?m)^\s*[-*]\s+", text))
    sentences = len(re.findall(r"[.!?](?:\s|$)", text))
    if bullets >= 4 or len(text) > 900 or sentences >= 8:
        return "thread", "Input has enough independent parts for a thread."
    if len(re.findall(r"\w+", text)) <= 12 and not any(term in lowered for term in ["project", "context", "build", "validation"]):
        return "short", "Input is a compact single observation."
    return "adaptive-single", "Input has substance, but not enough independent parts for a thread."


def _target_audience(text: str) -> str:
    lowered = text.lower()
    clusters = []
    if any(term in lowered for term in ["market", "quant", "backtest", "execution", "order book", "moex"]):
        clusters.append("markets / quant systems")
    if any(term in lowered for term in ["ml", "model", "validation", "benchmark", "feature"]):
        clusters.append("ML / validation")
    if any(term in lowered for term in ["cli", "tool", "codex", "infra", "build", "debug"]):
        clusters.append("builders / systems")
    return ", ".join(clusters) if clusters else "public notebook readers interested in technical work"


def _expected_action(best_format: str) -> str:
    if best_format == "question":
        return "reply"
    if best_format == "thread":
        return "dwell / repost"
    if best_format == "build-log":
        return "dwell / profile_click"
    if best_format == "article-note":
        return "reply / dwell"
    return "dwell"


def _length_range(best_format: str) -> str:
    ranges = {
        "short": "1-3 short paragraphs",
        "adaptive-single": "2-5 short paragraphs",
        "thread": "3-7 posts, each with independent value",
        "build-log": "3-5 short paragraphs",
        "article-note": "3-5 short paragraphs",
        "question": "brief setup plus one bounded question",
    }
    return ranges.get(best_format, "2-5 short paragraphs")


def _why_not_other_formats(best_format: str) -> dict[str, str]:
    formats = {
        "short": "too compressed unless the idea is genuinely small",
        "adaptive-single": "best when context is useful but thread parts are not independent",
        "thread": "only useful when each part adds independent value",
        "build-log": "best for what changed, what broke, and next check",
        "article-note": "best for source/paper/article reactions",
        "question": "best for bounded technical input",
    }
    return {name: ("selected" if name == best_format else reason) for name, reason in formats.items()}
