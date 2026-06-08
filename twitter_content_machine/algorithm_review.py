from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import connect_db
from .drafting import get_draft


POSITIVE_ACTIONS = [
    "reply",
    "repost/share",
    "dwell",
    "photo_expand",
    "video_view",
    "profile_click",
    "follow_author",
    "click",
]

TOPIC_CLUSTERS = {
    "quant / markets / microstructure": [
        "market",
        "markets",
        "microstructure",
        "backtest",
        "backtesting",
        "fills",
        "fill",
        "fees",
        "latency",
        "execution",
        "hft",
        "orderbook",
        "lob",
        "capacity",
    ],
    "C++ / systems / ML infra": [
        "c++",
        "cpp",
        "systems",
        "infra",
        "latency",
        "compiler",
        "cache",
        "pipeline",
        "ml",
        "model",
        "validation",
        "feature",
    ],
    "build logs / experiments": [
        "build",
        "broke",
        "tried",
        "expected",
        "got",
        "next",
        "experiment",
        "metric",
        "benchmark",
        "protocol",
        "cpd",
    ],
    "learning notes": [
        "misunderstood",
        "learned",
        "realized",
        "changed",
        "wrong",
        "assumption",
        "assumptions",
        "lesson",
        "note",
    ],
}

FINANCE_RISK_TERMS = [
    "buy",
    "sell",
    "long",
    "short",
    "signal",
    "guaranteed return",
    "not financial advice",
]

CRYPTO_SHILL_TERMS = ["alpha", "100x", "easy money", "moon", "gem", "ape"]

ENGAGEMENT_BAIT = ["thoughts?", "agree?", "what do you think?", "like and retweet"]

OVERCLAIM_TERMS = [
    "game changer",
    "revolutionary",
    "changes everything",
    "everyone should",
    "the future of",
    "unlock",
]

MEDIA_TERMS = [
    "chart",
    "plot",
    "graph",
    "diagram",
    "table",
    "screenshot",
    "terminal",
    "cli",
    "output",
    "trace",
    "matrix",
    "diff",
]

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "that",
    "this",
    "it",
    "is",
    "was",
    "i",
    "my",
    "after",
    "before",
    "now",
    "current",
    "guess",
    "small",
    "note",
}


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
            ("idea", row["id"], row["raw_text"] or "")
            for row in conn.execute("select id, raw_text from ideas").fetchall()
        )
        rows.extend(
            ("draft", row["id"], row["final_text"] or "")
            for row in conn.execute("select id, final_text from drafts where id != ?", (draft_id,)).fetchall()
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
    concrete_value = 5 if any(term in lowered for term in ["because", "broke", "fees", "fills", "validation", "protocol", "metric", "benchmark"]) else 3
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


def write_algorithm_review(draft_id: str) -> Path:
    view = _draft_view(draft_id)
    facts = _score_facts(view)
    target_audience = (
        "CS / ML / C++ / quant readers who engage with markets, systems, ML infra, and build logs"
        if facts.clusters
        else "unclear; make the topic cluster more explicit"
    )
    needed_edits: list[str] = []
    if not facts.clusters:
        needed_edits.append("add a clearer markets / systems / ML infra / build-log anchor")
    if facts.repeated:
        needed_edits.append("make the new angle concrete; similar memory exists")
    if facts.finance_risk:
        needed_edits.append("remove financial-advice risk wording")
    if facts.crypto_risk:
        needed_edits.append("remove crypto-shill risk wording")
    if facts.thread_stretch_risk:
        needed_edits.append("compress thread into one post or add independent value to each part")
    if not needed_edits:
        needed_edits.append("manual final read before posting")
    text = f"""# Algorithm Review

## 1. Candidate retrieval fit
- target audience: {target_audience}
- topic cluster: {", ".join(facts.clusters) if facts.clusters else "unclear"}
- semantic clarity: {"clear" if facts.clusters else "weak"}
- account consistency: {"high" if facts.clusters else "medium"}
- topic drift risk: {"low" if facts.clusters else "medium"}

## 2. Primary predicted action
- primary: {facts.primary_action}
- why: this action best matches the post's format, specificity, and likely viewer intent

## 3. Secondary predicted action
- secondary: {facts.secondary_action}

## 4. Negative feedback risk
- not_interested risk: {_risk_level(facts.generic_risk or facts.repeated)}
- mute/block risk: {_risk_level(facts.engagement_bait or facts.crypto_risk)}
- report risk: {_risk_level(facts.finance_risk or facts.crypto_risk)}
- financial-advice risk: {_risk_level(facts.finance_risk)}
- crypto-shill risk: {_risk_level(facts.crypto_risk)}
- overclaim risk: {_risk_level(facts.overclaim_risk)}
- generic content risk: {_risk_level(facts.generic_risk)}
- repeated idea risk: {_risk_level(facts.repeated)}
- repeated idea reason: {facts.repeated_reason}
- thread stretch risk: {_risk_level(facts.thread_stretch_risk)}

## 5. Format fit
- recommended format: {view.draft_type}
- why: use this format only if it carries one clear idea or independent thread parts

## 6. Media fit
- recommended media: {facts.media_type}
- why: media should add information, not decoration

## 7. Revision instructions
{chr(10).join(f"- {item}" for item in needed_edits)}

## 8. Decision
decision: {facts.decision}

## 9. Machine-readable scores
```yaml
{_score_block(facts.scores)}
```
"""
    path = view.folder / "07_algorithm_review.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_media_plan(draft_id: str) -> Path:
    view = _draft_view(draft_id)
    facts = _score_facts(view)
    if facts.media_needed:
        use_media = "yes"
        action = "photo_expand / dwell / share"
        best_media = facts.media_type
        reason = "the draft references a concrete visual artifact that can add information"
    else:
        use_media = "no"
        action = "none"
        best_media = "none"
        reason = "decorative media rejected; text already carries the idea"
    text = f"""# Media Plan

Does this post need media?
- {use_media}

Use media?
- {use_media}

Expected media action:
- {action}

Best media:
- {best_media}

Reason:
- {reason}

Do not use media if:
- it only decorates the post
- it makes the post look like a generic carousel
- it repeats text already in the post
"""
    path = view.folder / "08_media_plan.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_distribution_plan(draft_id: str) -> Path:
    view = _draft_view(draft_id)
    facts = _score_facts(view)
    if view.draft_type == "thread" and not facts.thread_stretch_risk:
        post_type = "thread"
    elif view.draft_type == "question":
        post_type = "standalone or reply"
    elif facts.primary_action == "reply":
        post_type = "reply"
    else:
        post_type = "standalone"
    audience = ", ".join(facts.clusters) if facts.clusters else "tighten topic cluster before posting"
    text = f"""# Distribution Plan

Post type:
- {post_type}

Best initial audience:
- {audience}

Potential accounts/conversations to reply under:
- quant/dev/infra/ML conversations where this adds a concrete example

Follow-up reply:
- add source, code detail, chart, or limitation only if someone asks

Do not:
- spam the same idea
- post many variants in a row
- quote random viral posts without adding value
- turn the draft into engagement bait
"""
    path = view.folder / "09_distribution_plan.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_all_algorithm_layers(draft_id: str) -> dict[str, Path]:
    return {
        "algorithm_review": write_algorithm_review(draft_id),
        "media_plan": write_media_plan(draft_id),
        "distribution_plan": write_distribution_plan(draft_id),
    }


def artifact_paths(paths: dict[str, Path] | Path) -> str:
    if isinstance(paths, Path):
        return str(paths)
    return "\n".join(f"{name}: {path}" for name, path in paths.items())
