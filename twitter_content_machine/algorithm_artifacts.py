from __future__ import annotations

from pathlib import Path

from .algorithm_scoring import _draft_view, _risk_level, _score_block, _score_facts


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
