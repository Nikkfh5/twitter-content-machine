from __future__ import annotations

from .utils import format_list, get_now, short_hash, slugify


DRAFT_FILES = [
    "00_raw_input.md",
    "01_context_used.md",
    "02_brief.md",
    "03_variants.md",
    "04_critique.md",
    "05_selected.md",
    "06_final_candidate.md",
    "prompt_to_codex.md",
    "meta.yaml",
]


def draft_id_for_text(text: str) -> str:
    now = get_now()
    slug = slugify(text)
    return f"{now:%Y%m%d-%H%M%S}-{slug}-{short_hash(text + now.isoformat(), 6)}"


def build_brief(text: str, draft_type: str, project_summary: str, memory: list[dict[str, str]]) -> str:
    return f"""# Writing Brief

Type: {draft_type}

Raw idea:
{text}

Public angle:
- personal notebook / build-in-public
- direct, specific, not expert cosplay
- preserve uncertainty when true
- no financial advice, no trading signal

Context summary:
{project_summary[:2500]}

Related old memory:
{format_list([f"{m['type']} {m['id']}: {m['text'][:180]}" for m in memory])}
"""


def build_prompt(text: str, draft_type: str, brief: str, profile: dict[str, str], identity_context: str = "") -> str:
    return f"""# Prompt To Codex

You are helping draft X/Twitter content. Draft only. Never publish or call any write/post API.

Raw input:
{text}

Draft type:
{draft_type}

Profile/style:
{profile.get('persona', '')}

{profile.get('style', '')}

Forbidden phrases:
{profile.get('forbidden_phrases', '')}

Safety:
{profile.get('safety', '')}

Identity/style context:
{identity_context}

Brief and context:
{brief}

Output required:
1. Variant A: direct/raw
2. Variant B: clearer/structured
3. Variant C: sharper/more opinionated but not fake-contrarian
4. Critique
5. Selected candidate
6. Final candidate
"""
