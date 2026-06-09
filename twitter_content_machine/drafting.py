from __future__ import annotations

import sys
from pathlib import Path

from .config import load_config
from .context_bundle import build_context_bundle
from .db import connect_db, search_memory, upsert_fts
from .draft_artifacts import DRAFT_FILES, build_brief, build_prompt, draft_id_for_text
from .draft_fallbacks import generate_variants
from .draft_status import get_draft, refine_draft, review_draft, set_draft_status
from .generation_workspace import prepare_generation_workspace
from .identity_style import identity_brief_context, write_identity_artifacts
from .llm import resolve_llm_mode, run_llm
from .models import DraftResult
from .project_context import detect_project, refresh_project_context
from .review import anti_gpt_pass, critique_text, redact_secrets
from .state import set_current_draft
from .utils import get_now, iso_now, slugify
from .workspace import ensure_workspace, read_profile
from .x_read import sync_posted


def create_draft(
    text: str,
    draft_type: str = "short",
    cwd: Path | str | None = None,
    url: str | None = None,
    copy: bool = False,
    identity_style_profile: str | None = None,
    identity_strength: float = 0.0,
    llm_mode: str | None = None,
    llm_model: str | None = None,
    reasoning_effort: str | None = None,
    speed: str | None = None,
    require_llm: bool = False,
    no_llm: bool = False,
    context_only: bool = False,
) -> DraftResult:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    if llm_model or reasoning_effort or speed:
        from dataclasses import replace

        config = replace(
            config,
            llm_model=llm_model or config.llm_model,
            llm_reasoning_effort=reasoning_effort or config.llm_reasoning_effort,
            llm_speed=speed or config.llm_speed,
        )
    sync_posted()
    project = detect_project(Path(cwd) if cwd else None)
    context = refresh_project_context(project)
    safe_text = redact_secrets(text)
    memory = search_memory(safe_text, limit=5)
    draft_id = draft_id_for_text(safe_text)
    now = get_now()
    folder = workspace.root / "drafts" / f"{now:%Y}" / f"{now:%m}" / draft_id
    folder.mkdir(parents=True, exist_ok=False)
    profile = read_profile(workspace.root)
    identity_context = (
        identity_brief_context(identity_style_profile, identity_strength)
        if identity_style_profile
        else ""
    )
    brief = build_brief(safe_text, draft_type, context.summary + "\n\n" + identity_context, memory)
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
        "prompt_to_codex.md": build_prompt(safe_text, draft_type, brief, profile, identity_context),
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
    set_current_draft(draft_id)
    if copy:
        try:
            import pyperclip  # type: ignore

            pyperclip.copy(final)
        except Exception:
            pass
    if identity_style_profile:
        write_identity_artifacts(draft_id, identity_style_profile, identity_strength)
    bundle_paths = build_context_bundle(
        draft_id=draft_id,
        draft_folder=folder,
        raw_input=safe_text,
        draft_type=draft_type,
        cwd=Path(cwd) if cwd else None,
        project=project,
        project_context=context,
        config=config,
        source_url=url,
        identity_context=identity_context,
    )
    prepare_generation_workspace(folder, config)
    selected_mode = resolve_llm_mode(llm_mode, config, no_llm=no_llm or context_only)
    if context_only:
        (folder / "16_llm_parse_report.md").write_text(
            "# LLM Parse Report\n\n- status: context_only\n- llm_attempted: false\n",
            encoding="utf-8",
        )
    else:
        must_have_llm = require_llm or selected_mode == "codex"
        result = run_llm(
            selected_mode,
            bundle_paths.request,
            folder,
            config,
            require_llm=False,
            progress_callback=_stderr_progress if selected_mode == "codex" else None,
        )
        if result.attempted:
            (folder / "15_llm_raw_output.md").write_text(result.raw_output, encoding="utf-8")
        if result.ok:
            data = result.parsed.data
            variants_text = "# Variants\n\n" + "\n\n".join(
                f"## Variant {item.get('id', '')}: {item.get('name', '')}\n{item.get('text', '')}\n\nIntent: {item.get('intent', '')}\nWhy: {item.get('why_it_might_work', '')}\nRisks: {', '.join(item.get('risks', []))}"
                for item in data["variants"]
            )
            critique_text_out = "# Critique\n\n" + "\n".join(f"- {key}: {value}" for key, value in data["critique"].items())
            selected_id = data["selected_variant_id"]
            selected_text = next((item["text"] for item in data["variants"] if item["id"] == selected_id), data["final_candidate"])
            final = anti_gpt_pass(str(data["final_candidate"]))
            (folder / "03_variants.md").write_text(variants_text + "\n", encoding="utf-8")
            (folder / "04_critique.md").write_text(critique_text_out + "\n", encoding="utf-8")
            (folder / "05_selected.md").write_text(f"# Selected\n\n{selected_text}\n", encoding="utf-8")
            (folder / "06_final_candidate.md").write_text(final + "\n", encoding="utf-8")
            with connect_db() as conn:
                conn.execute("update drafts set final_text = ?, selected_variant = ? where id = ?", (final, selected_id, draft_id))
        (folder / "16_llm_parse_report.md").write_text(
            f"""# LLM Parse Report

- mode: {selected_mode}
- attempted: {str(result.attempted).lower()}
- ok: {str(result.ok).lower()}
- message: {result.message}
- parse_error: {result.parsed.error}
""",
            encoding="utf-8",
        )
        if must_have_llm and not result.ok:
            raise RuntimeError(f"Codex generation failed: {result.message}")
    return DraftResult(draft_id, folder, final)


def _stderr_progress(message: str) -> None:
    print(f"tw: {message}", file=sys.stderr, flush=True)


__all__ = [
    "create_draft",
    "generate_variants",
    "get_draft",
    "refine_draft",
    "review_draft",
    "set_draft_status",
]
