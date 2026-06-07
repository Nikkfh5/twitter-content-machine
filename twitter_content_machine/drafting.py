from __future__ import annotations

from pathlib import Path

from .db import connect_db, resolve_draft_id, search_memory, upsert_fts
from .identity_style import identity_brief_context, write_identity_artifacts
from .models import DraftResult
from .project_context import detect_project, refresh_project_context
from .review import anti_gpt_pass, critique_text, redact_secrets, score_text
from .utils import format_list, get_now, iso_now, short_hash, slugify
from .workspace import ensure_workspace, read_profile
from .x_read import sync_posted


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


def _draft_id(text: str) -> str:
    now = get_now()
    slug = slugify(text)
    return f"{now:%Y%m%d-%H%M%S}-{slug}-{short_hash(text + now.isoformat(), 6)}"


def _brief(text: str, draft_type: str, project_summary: str, memory: list[dict[str, str]]) -> str:
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


def _variant_short(text: str, tone: str) -> str:
    if tone == "direct":
        return f"I used to hand-wave this: {text}. Current guess: the execution model matters more than the metric I was optimizing."
    if tone == "structured":
        return f"Small note: {text}.\n\nWhat changed for me: a backtest can look clean while the execution assumptions are doing most of the work."
    return f"The uncomfortable part of backtests is not the chart. It is noticing that {text}, and then deciding which assumptions are actually defensible."


def _variant_thread(text: str) -> str:
    return "\n\n".join(
        [
            f"1/ Small build note: {text}.",
            "2/ I used to look first at metrics. Now I first ask what execution assumptions make the result possible.",
            "3/ The annoying part is that a small unrealistic fill rule can dominate a clean-looking strategy report.",
            "4/ Current check: separate model quality from data/execution realism before trusting the output.",
            "5/ Not a conclusion yet. More like a debugging note for future backtests.",
        ]
    )


def generate_variants(text: str, draft_type: str, identity_style_active: bool = False) -> tuple[str, str, str]:
    if identity_style_active:
        return (
            f"Clean current-account version:\n\nSmall note from building: {text}.\n\nCurrent guess: the useful part is not the take itself, but which assumption broke.",
            f"Raw/personal version:\n\nI used to think this was simpler: {text}.\n\nNow it feels more annoying. The system breaks around assumptions, not around the pretty metric.",
            f"Compressed X-native version:\n\n{text}.\n\nThe annoying part is that the wrong assumption can look like insight until you test it.",
        )
    if draft_type == "thread":
        a = _variant_thread(text)
        b = _variant_thread(text).replace("Small build note", "Backtest note")
        c = _variant_thread(text).replace("The annoying part", "The fake precision starts")
        return a, b, c
    if draft_type == "article-note":
        base = f"Read this and took one useful question from it: {text}."
        return (
            f"{base}\n\nWhat I want to test: whether the idea survives contact with my own project assumptions.",
            f"{base}\n\nUseful part: it gives me a sharper way to check regimes instead of trusting one average backtest.",
            f"{base}\n\nI do not fully buy the conclusion yet. But the framing is useful enough to test.",
        )
    if draft_type == "build-log":
        return (
            f"Build log: {text}.\n\nWhat broke: the assumption was cleaner than the system. Next check: isolate the failure instead of polishing the explanation.",
            f"Tried: {text}.\n\nChanged my mind on one thing: the boring plumbing can decide whether the result means anything.",
            f"The useful part of today's project work: {text}. Not a big lesson, just a constraint I cannot ignore anymore.",
        )
    if draft_type == "question":
        return (
            f"Question for people who have dealt with this: {text}. Any good references that are practical, not just high-level?",
            f"Looking for resources on this: {text}. Especially interested in failure cases and implementation details.",
            f"Small question: {text}. What is the least hand-wavy thing worth reading/testing here?",
        )
    return (
        _variant_short(text, "direct"),
        _variant_short(text, "structured"),
        _variant_short(text, "sharp"),
    )


def _prompt(text: str, draft_type: str, brief: str, profile: dict[str, str], identity_context: str = "") -> str:
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


def create_draft(
    text: str,
    draft_type: str = "short",
    cwd: Path | str | None = None,
    url: str | None = None,
    copy: bool = False,
    identity_style_profile: str | None = None,
    identity_strength: float = 0.0,
) -> DraftResult:
    workspace = ensure_workspace()
    sync_posted()
    project = detect_project(Path(cwd) if cwd else None)
    context = refresh_project_context(project)
    safe_text = redact_secrets(text)
    memory = search_memory(safe_text, limit=5)
    draft_id = _draft_id(safe_text)
    now = get_now()
    folder = workspace.root / "drafts" / f"{now:%Y}" / f"{now:%m}" / draft_id
    folder.mkdir(parents=True, exist_ok=False)
    profile = read_profile(workspace.root)
    identity_context = (
        identity_brief_context(identity_style_profile, identity_strength)
        if identity_style_profile
        else ""
    )
    brief = _brief(safe_text, draft_type, context.summary + "\n\n" + identity_context, memory)
    a, b, c = generate_variants(safe_text, draft_type, identity_style_active=bool(identity_style_profile))
    variants = f"""# Variants

## Variant A: direct / raw
{anti_gpt_pass(a)}

## Variant B: clearer / structured
{anti_gpt_pass(b)}

## Variant C: sharper / more opinionated
{anti_gpt_pass(c)}
"""
    selected = anti_gpt_pass(a)
    critique = f"""# Critique

## Variant A
{critique_text(a, memory)}

## Variant B
{critique_text(b, memory)}

## Variant C
{critique_text(c, memory)}

## Remove
- stock phrasing
- overclaiming
- fake certainty
- anything that sounds like financial advice
- private implementation details
"""
    final = anti_gpt_pass(selected)
    files = {
        "00_raw_input.md": f"# Raw Input\n\n{safe_text}\n\nSource URL: {url or ''}\n",
        "01_context_used.md": context.summary,
        "02_brief.md": brief,
        "03_variants.md": variants,
        "04_critique.md": critique,
        "05_selected.md": f"# Selected\n\n{selected}\n",
        "06_final_candidate.md": f"{final}\n",
        "prompt_to_codex.md": _prompt(safe_text, draft_type, brief, profile, identity_context),
        "meta.yaml": f"""id: {draft_id}
created_at: {iso_now()}
updated_at: {iso_now()}
project_id: {project.id}
type: {draft_type}
status: draft
source_url: {url or ''}
folder_path: {folder}
autopublish: false
identity_style: {identity_style_profile or ''}
identity_strength: {identity_strength if identity_style_profile else ''}
""",
    }
    for name in DRAFT_FILES:
        (folder / name).write_text(files[name], encoding="utf-8")
    with connect_db() as conn:
        conn.execute(
            """
            insert into drafts(id, created_at, updated_at, project_id, type, status, title,
              folder_path, source_idea_id, selected_variant, final_text, tags)
            values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft_id,
                iso_now(),
                iso_now(),
                project.id,
                draft_type,
                "draft",
                slugify(safe_text),
                str(folder),
                None,
                "A",
                final,
                "",
            ),
        )
        upsert_fts(conn, "drafts_fts", (draft_id, slugify(safe_text), final, ""))
    if copy:
        try:
            import pyperclip  # type: ignore

            pyperclip.copy(final)
        except Exception:
            pass
    if identity_style_profile:
        write_identity_artifacts(draft_id, identity_style_profile, identity_strength)
    return DraftResult(draft_id, folder, final)


def get_draft(draft_id: str) -> dict[str, str]:
    resolved = resolve_draft_id(draft_id)
    with connect_db() as conn:
        row = conn.execute("select * from drafts where id = ?", (resolved,)).fetchone()
    if not row:
        raise ValueError(f"Draft not found: {draft_id}")
    return dict(row)


def refine_draft(draft_id: str, instruction: str = "human") -> DraftResult:
    draft = get_draft(draft_id)
    folder = Path(draft["folder_path"])
    revisions = folder / "revisions"
    revisions.mkdir(exist_ok=True)
    existing = sorted(revisions.glob("*.md"))
    number = len(existing) + 1
    source = draft["final_text"] or (folder / "06_final_candidate.md").read_text(encoding="utf-8")
    if instruction in {"human", "critique"}:
        refined = anti_gpt_pass(source).replace("Current guess:", "Current guess:")
    elif instruction == "shorten":
        refined = " ".join(source.split()[:45])
    elif instruction == "thread":
        refined = _variant_thread(source.splitlines()[0][:180])
    elif instruction == "clarify":
        refined = source + "\n\nClarify before posting: what exact assumption changed?"
    else:
        refined = anti_gpt_pass(source)
    rev_path = revisions / f"{number:03d}.md"
    rev_path.write_text(refined + "\n", encoding="utf-8")
    (folder / "06_final_candidate.md").write_text(refined + "\n", encoding="utf-8")
    now = iso_now()
    resolved = draft["id"]
    with connect_db() as conn:
        conn.execute(
            "insert into draft_revisions(id, draft_id, created_at, revision_number, text, change_note) values(?, ?, ?, ?, ?, ?)",
            (f"{resolved}-r{number:03d}", resolved, now, number, refined, instruction),
        )
        conn.execute(
            "update drafts set updated_at = ?, final_text = ? where id = ?",
            (now, refined, resolved),
        )
        upsert_fts(conn, "drafts_fts", (resolved, draft["title"], refined, draft.get("tags") or ""))
    return DraftResult(resolved, folder, refined)


def review_draft(draft_id: str) -> str:
    draft = get_draft(draft_id)
    memory = search_memory(draft["final_text"] or "", limit=5)
    return score_text(draft["final_text"] or "", memory)


def set_draft_status(draft_id: str, status: str, url: str | None = None) -> None:
    draft = get_draft(draft_id)
    with connect_db() as conn:
        conn.execute("update drafts set status = ?, updated_at = ? where id = ?", (status, iso_now(), draft["id"]))
        if status == "posted":
            post_id = f"manual_{short_hash((url or '') + draft['id'], 10)}"
            conn.execute(
                "insert or ignore into posts(id, created_at, platform, platform_post_id, url, text, thread_id, project_id, source_draft_id, tags) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (post_id, iso_now(), "x", post_id, url or "", draft["final_text"] or "", "", draft["project_id"], draft["id"], ""),
            )
            upsert_fts(conn, "posts_fts", (post_id, draft["final_text"] or "", ""))
