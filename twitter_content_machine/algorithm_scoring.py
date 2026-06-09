from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .algorithm_terms import (
    CRYPTO_SHILL_TERMS,
    ENGAGEMENT_BAIT,
    FINANCE_RISK_TERMS,
    MEDIA_TERMS,
    OVERCLAIM_TERMS,
    POSITIVE_ACTIONS,
    STOPWORDS,
    TOPIC_CLUSTERS,
)
from .db import connect_db
from .drafting import get_draft


@dataclass(frozen=True)
class DraftView:
    id: str
    folder: Path
    draft_type: str
    final_text: str
    project_id: str


@dataclass(frozen=True)
class ReviewFacts:
    clusters: list[str]
    repeated: bool
    repeated_reason: str
    finance_risk: bool
    crypto_risk: bool
    engagement_bait: bool
    overclaim_risk: bool
    generic_risk: bool
    thread_stretch_risk: bool
    media_needed: bool
    media_type: str
    primary_action: str
    secondary_action: str
    scores: dict[str, int]
    decision: str


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9+#]+", text.lower())
    return {word for word in words if len(word) > 2 and word not in STOPWORDS}


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    for term in terms:
        normalized = term.lower().strip()
        if not normalized:
            continue
        pattern = r"(?<![a-z0-9+#])" + re.escape(normalized) + r"(?![a-z0-9+#])"
        if re.search(pattern, lowered):
            return True
    return False


def _draft_view(draft_id: str) -> DraftView:
    draft = get_draft(draft_id)
    folder = Path(draft["folder_path"])
    final_path = folder / "06_final_candidate.md"
    if final_path.exists():
        final_text = final_path.read_text(encoding="utf-8", errors="replace")
    else:
        final_text = draft["final_text"] or ""
    return DraftView(
        id=draft["id"],
        folder=folder,
        draft_type=draft["type"] or "short",
        final_text=final_text.strip(),
        project_id=draft["project_id"] or "",
    )


def _topic_clusters(text: str) -> list[str]:
    lowered = text.lower()
    clusters: list[str] = []
    for name, terms in TOPIC_CLUSTERS.items():
        if any(term in lowered for term in terms):
            clusters.append(name)
    return clusters


def _similar_memory(text: str, draft_id: str) -> tuple[bool, str]:
    current = _tokens(text)
    if not current:
        return False, "not enough text to compare"
    rows: list[tuple[str, str, str]] = []
    with connect_db() as conn:
        rows.extend(
            (f"{row['status']} draft", row["id"], row["final_text"] or "")
            for row in conn.execute(
                "select id, status, final_text from drafts where id != ?", (draft_id,)
            ).fetchall()
            if row["status"] in {"ready", "posted"}
        )
        rows.extend(
            ("post", row["id"], row["text"] or "")
            for row in conn.execute("select id, text from posts").fetchall()
        )
    best_kind = ""
    best_id = ""
    best_overlap = 0.0
    for kind, item_id, old_text in rows:
        old = _tokens(old_text)
        if not old:
            continue
        overlap = len(current & old) / max(1, min(len(current), len(old)))
        if overlap > best_overlap:
            best_kind = kind
            best_id = item_id
            best_overlap = overlap
    if best_overlap >= 0.55:
        return True, f"similar memory exists: {best_kind} {best_id} overlap {best_overlap:.2f}"
    return False, "no close local memory match"


def _thread_stretch_risk(text: str, draft_type: str) -> bool:
    if draft_type != "thread":
        return False
    parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(parts) < 4:
        return False
    normalized_parts = [_tokens(part) for part in parts]
    if not normalized_parts:
        return False
    all_tokens = set().union(*normalized_parts)
    average_unique = sum(len(part) for part in normalized_parts) / len(normalized_parts)
    repeated_phrases = len({re.sub(r"^\d+/\s*", "", part.lower()) for part in parts}) <= 2
    return repeated_phrases or len(all_tokens) <= max(6, int(average_unique * 1.5))


def _primary_action(text: str, draft_type: str, clusters: list[str], media_needed: bool) -> tuple[str, str]:
    lowered = text.lower()
    if media_needed:
        return "photo_expand", "dwell"
    if draft_type == "question" or "?" in text:
        return "reply", "dwell"
    if any(term in lowered for term in ["list", "failure modes", "1.", "2.", "3."]):
        return "repost/share", "profile_click"
    if any(term in lowered for term in ["building", "public notebook", "current stack", "follow"]):
        return "profile_click", "follow_author"
    if clusters:
        return "dwell", "reply"
    return "dwell", "profile_click"


def _score_facts(view: DraftView) -> ReviewFacts:
    text = view.final_text
    lowered = text.lower()
    clusters = _topic_clusters(text)
    repeated, repeated_reason = _similar_memory(text, view.id)
    finance_risk = _contains_any(lowered, FINANCE_RISK_TERMS)
    crypto_risk = _contains_any(lowered, CRYPTO_SHILL_TERMS)
    engagement_bait = _contains_any(lowered, ENGAGEMENT_BAIT)
    overclaim_risk = _contains_any(lowered, OVERCLAIM_TERMS)
    generic_risk = len(_tokens(text)) < 8 or "great point" in lowered
    thread_stretch_risk = _thread_stretch_risk(text, view.draft_type)
    media_needed = _contains_any(lowered, MEDIA_TERMS)
    if "chart" in lowered or "plot" in lowered or "graph" in lowered:
        media_type = "chart"
    elif "diagram" in lowered or "pipeline" in lowered:
        media_type = "diagram"
    elif "table" in lowered or "matrix" in lowered:
        media_type = "table"
    elif "terminal" in lowered or "cli" in lowered or "output" in lowered:
        media_type = "terminal screenshot"
    else:
        media_type = "none"
    primary, secondary = _primary_action(text, view.draft_type, clusters, media_needed)

    safety_penalty = sum([finance_risk, crypto_risk, engagement_bait, overclaim_risk])
    candidate_retrieval_fit = 5 if clusters else 2
    concrete_value = (
        5
        if any(
            term in lowered
            for term in [
                "because",
                "broke",
                "fees",
                "fills",
                "validation",
                "protocol",
                "metric",
                "benchmark",
            ]
        )
        else 3
    )
    positive_action_potential = 5 if primary in POSITIVE_ACTIONS and not generic_risk else 3
    negative_feedback_safety = max(0, 5 - (2 * safety_penalty) - (1 if repeated else 0))
    style_authenticity = 5
    if engagement_bait or overclaim_risk:
        style_authenticity -= 2
    if generic_risk:
        style_authenticity -= 1
    if finance_risk or crypto_risk:
        style_authenticity -= 2
    style_authenticity = max(0, style_authenticity)
    media_fit = 5 if media_needed else 3
    if view.draft_type == "thread" and thread_stretch_risk:
        positive_action_potential = min(positive_action_potential, 2)
        concrete_value = min(concrete_value, 2)
    scores = {
        "candidate_retrieval_fit": candidate_retrieval_fit,
        "concrete_value": concrete_value,
        "positive_action_potential": positive_action_potential,
        "negative_feedback_safety": negative_feedback_safety,
        "style_authenticity": style_authenticity,
        "media_fit": media_fit,
    }
    total = sum(scores.values())
    if finance_risk or crypto_risk or negative_feedback_safety <= 1:
        decision = "reject"
    elif thread_stretch_risk or total < 22 or repeated:
        decision = "revise"
    else:
        decision = "publish candidate"
    return ReviewFacts(
        clusters=clusters,
        repeated=repeated,
        repeated_reason=repeated_reason,
        finance_risk=finance_risk,
        crypto_risk=crypto_risk,
        engagement_bait=engagement_bait,
        overclaim_risk=overclaim_risk,
        generic_risk=generic_risk,
        thread_stretch_risk=thread_stretch_risk,
        media_needed=media_needed,
        media_type=media_type,
        primary_action=primary,
        secondary_action=secondary,
        scores=scores,
        decision=decision,
    )


def _risk_level(flag: bool) -> str:
    return "high" if flag else "low"


def _score_block(scores: dict[str, int]) -> str:
    total = sum(scores.values())
    lines = [f"{key}: {value}" for key, value in scores.items()]
    lines.append(f"total: {total}")
    return "\n".join(lines)
