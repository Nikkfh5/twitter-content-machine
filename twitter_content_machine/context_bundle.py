from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Config
from .db import search_memory
from .models import Project, ProjectContext
from .utils import iso_now
from .workspace import read_profile


@dataclass(frozen=True)
class BundlePaths:
    markdown: Path
    json: Path
    request: Path


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[TRUNCATED: original {len(text)} chars, included {limit} chars]\n"


def _manifest(kind: str, item_id: str, path_or_url: str, included: str, reason: str, risk_level: str = "low") -> dict[str, Any]:
    return {
        "kind": kind,
        "id": item_id,
        "path/url": path_or_url,
        "included_chars": len(included),
        "reason": reason,
        "risk_level": risk_level,
    }


def build_context_bundle(
    draft_id: str,
    draft_folder: Path,
    raw_input: str,
    draft_type: str,
    cwd: Path | None,
    project: Project,
    project_context: ProjectContext,
    config: Config,
    source_url: str | None = None,
    identity_context: str = "",
) -> BundlePaths:
    profile = read_profile(config.root)
    source_manifest: list[dict[str, Any]] = []
    account = {
        key: _clip(profile.get(key, ""), 4000)
        for key in [
            "persona",
            "style",
            "safety",
            "forbidden_phrases",
            "x_algorithm_principles",
            "x_fit_rubric",
        ]
    }
    for key, value in account.items():
        source_manifest.append(_manifest("profile", key, str(config.root / "profile" / f"{key}.md"), value, "account positioning"))
    project_summary = _clip(project_context.summary, config.llm_max_project_context_chars)
    recent = _clip(project_context.recent_changes_path.read_text(encoding="utf-8", errors="replace"), 8000) if project_context.recent_changes_path.exists() else ""
    public_angle = _clip(project_context.public_angle_path.read_text(encoding="utf-8", errors="replace"), 4000) if project_context.public_angle_path.exists() else ""
    source_manifest.append(_manifest("project_context", project.id, str(project_context.context_path), project_summary, "detected project summary"))
    memory = search_memory(raw_input, config.llm_max_memory_items, project_id=project.id, include_global=True)
    bundle = {
        "task": {
            "raw_input": raw_input,
            "draft_type": draft_type,
            "language": config.default_language,
            "source_url": source_url or "",
            "cwd": str((cwd or Path.cwd()).resolve()),
            "project_id": project.id,
            "draft_id": draft_id,
            "created_at": iso_now(),
        },
        "account_positioning": account,
        "project_context": {
            "context": project_summary,
            "recent_changes": recent,
            "public_angle": public_angle,
        },
        "related_memory": memory,
        "identity_style": identity_context,
        "source_context": {"source_url": source_url or ""},
        "drafting_requirements": {
            "schema": "Return strict JSON matching 14_llm_request.md",
            "safety": "Draft only. No publishing. No financial advice. No crypto shilling.",
        },
        "algorithm_review_inputs": {
            "positive_actions": ["reply", "repost/share", "dwell", "photo_expand", "profile_click", "follow_author"],
            "negative_actions": ["not_interested", "block_author", "mute_author", "report"],
        },
        "source_manifest": source_manifest,
    }
    markdown = _bundle_markdown(bundle)
    request = _llm_request(bundle)
    md_path = draft_folder / "13_context_bundle.md"
    json_path = draft_folder / "13_context_bundle.json"
    request_path = draft_folder / "14_llm_request.md"
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    request_path.write_text(request, encoding="utf-8")
    return BundlePaths(md_path, json_path, request_path)


def _bundle_markdown(bundle: dict[str, Any]) -> str:
    parts = [
        "# Context Bundle",
        "",
        "## Task",
        json.dumps(bundle["task"], indent=2, ensure_ascii=False),
        "",
        "## Account Positioning",
    ]
    for key, value in bundle["account_positioning"].items():
        parts.extend([f"### {key}", value])
    parts.extend(
        [
            "## Project Context",
            bundle["project_context"]["context"],
            "## Recent Changes",
            bundle["project_context"]["recent_changes"],
            "## Public Angle",
            bundle["project_context"]["public_angle"],
            "## Related Memory",
            json.dumps(bundle["related_memory"], indent=2, ensure_ascii=False),
            "## Identity Style",
            str(bundle["identity_style"]),
            "## Drafting Requirements",
            json.dumps(bundle["drafting_requirements"], indent=2, ensure_ascii=False),
            "## Source Manifest",
            json.dumps(bundle["source_manifest"], indent=2, ensure_ascii=False),
        ]
    )
    return "\n\n".join(parts)


def _compact_memory(memory: list[dict[str, Any]], limit: int = 3) -> str:
    if not memory:
        return "- none"
    lines = []
    for item in memory[:limit]:
        text = " ".join(str(item.get("text", "")).split())
        lines.append(f"- {item.get('kind', item.get('type', 'memory'))} {item.get('id', '')}: {_clip(text, 280)}")
    return "\n".join(lines)


def _llm_request(bundle: dict[str, Any]) -> str:
    task = bundle["task"]
    account = bundle["account_positioning"]
    project = bundle["project_context"]
    identity = str(bundle.get("identity_style") or "")
    return f"""# LLM Draft Request

Generate X/Twitter draft text from this compact request.

Full inspectable context is available in this draft folder:
- 13_context_bundle.md
- 13_context_bundle.json

Use the compact context below first. Read full bundle files only if the compact context is insufficient.

Return strict JSON only. Do not wrap it in markdown. Use this schema:

```json
{{
  "variants": [
    {{"id": "A", "name": "direct_raw", "text": "...", "intent": "dwell", "why_it_might_work": "...", "risks": []}},
    {{"id": "B", "name": "clear_structured", "text": "...", "intent": "reply", "why_it_might_work": "...", "risks": []}},
    {{"id": "C", "name": "sharper", "text": "...", "intent": "repost_share", "why_it_might_work": "...", "risks": []}}
  ],
  "critique": {{
    "real_point": "...",
    "too_generic": false,
    "overclaim_risk": "low",
    "financial_advice_risk": "low",
    "confidentiality_risk": "low",
    "repetition_risk": "low",
    "identity_style_risk": "low",
    "algorithm_fit": "..."
  }},
  "selected_variant_id": "A",
  "final_candidate": "...",
  "media_suggestion": {{"use_media": false, "type": "none", "reason": "..."}},
  "manual_notes": []
}}
```

Draft only. Never publish. Never call X write APIs.
Do not run shell commands unless you must inspect the local context files above.
Do not modify files.

## Task

```json
{json.dumps(task, indent=2, ensure_ascii=False)}
```

## Account Rules

Persona:
{_clip(account.get("persona", ""), 900)}

Style:
{_clip(account.get("style", ""), 900)}

Safety:
{_clip(account.get("safety", ""), 700)}

Forbidden phrases:
{_clip(account.get("forbidden_phrases", ""), 600)}

Algorithm principles:
{_clip(account.get("x_algorithm_principles", ""), 1000)}

## Project Public Angle

{_clip(project.get("public_angle", ""), 900)}

## Related Memory

{_compact_memory(bundle.get("related_memory", []))}

## Identity Style

{_clip(identity, 2200)}

## Output Requirements

- Variant A should be direct/raw.
- Variant B should be clearer/structured.
- Variant C should be sharper, but not fake-contrarian.
- Final candidate should be usable as a first post about the project.
- Keep uncertainty if the project is just starting.
- Avoid financial advice, trading signals, crypto shilling, and generic launch hype.
- Prefer concrete benchmark language over broad promises.

"""
