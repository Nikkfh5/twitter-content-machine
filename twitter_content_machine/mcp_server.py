from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .algorithm_review import write_algorithm_review, write_all_algorithm_layers
from .db import search_memory
from .drafting import create_draft, get_draft, refine_draft, review_draft, set_draft_status
from .identity_style import style_build, style_curate, style_review, write_identity_artifacts
from .project_context import detect_project, refresh_project_context
from .telegram_import import import_telegram
from .x_read import sync_posted


def tw_search_memory(query: str, project_id: str | None = None, limit: int = 10) -> list[dict[str, str]]:
    del project_id
    return search_memory(query, limit)


def tw_get_project_context(cwd: str | None = None) -> dict[str, str]:
    project = detect_project(Path(cwd) if cwd else None)
    context = refresh_project_context(project)
    return {"project_id": project.id, "context": context.summary}


def tw_refresh_project_context(cwd: str | None = None) -> dict[str, str]:
    project = detect_project(Path(cwd) if cwd else None)
    context = refresh_project_context(project, force=True)
    return {"project_id": project.id, "context_path": str(context.context_path)}


def tw_save_idea(text: str, url: str | None = None, tags: str | None = None, cwd: str | None = None) -> dict[str, str]:
    from .cli import save_idea

    idea_id = save_idea(text, Path(cwd) if cwd else None, url, tags or "")
    return {"idea_id": idea_id}


def tw_create_draft(
    text: str,
    type: str = "short",
    identity_style: str | None = None,
    identity_strength: float = 0.35,
    algo_aware: bool = False,
    url: str | None = None,
    cwd: str | None = None,
) -> dict[str, str]:
    draft = create_draft(
        text,
        type,
        Path(cwd) if cwd else None,
        url,
        False,
        identity_style,
        identity_strength if identity_style else 0.0,
    )
    if algo_aware:
        write_all_algorithm_layers(draft.id)
    return {"draft_id": draft.id, "folder": str(draft.folder), "final_text": draft.final_text}


def tw_get_draft(draft_id: str) -> dict[str, str]:
    return get_draft(draft_id)


def tw_list_drafts(status: str | None = None, project_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    from .cli import list_drafts

    return list_drafts(status=status, project_id=project_id, limit=limit)


def tw_refine_draft(draft_id: str, instruction: str) -> dict[str, str]:
    draft = refine_draft(draft_id, instruction)
    return {"draft_id": draft.id, "folder": str(draft.folder), "final_text": draft.final_text}


def tw_review_draft(draft_id: str) -> str:
    return review_draft(draft_id)


def tw_algo_review(draft_id: str) -> dict[str, str]:
    path = write_algorithm_review(draft_id)
    return {"path": str(path)}


def tw_style_review(draft_id: str, profile_name: str = "tg_crypto_clean") -> dict[str, str]:
    path = style_review(draft_id, profile_name)
    return {"path": str(path)}


def tw_import_telegram(path: str, profile_name: str = "tg_crypto_clean") -> dict[str, str | int]:
    result = import_telegram(path, profile_name)
    return {
        "profile_name": result.profile_name,
        "profile_dir": str(result.profile_dir),
        "imported": result.imported,
        "own_original": result.own_original,
        "forwarded_other": result.forwarded_other,
    }


def tw_style_build(profile_name: str) -> dict[str, str]:
    path = style_build(profile_name)
    return {"profile_dir": str(path)}


def tw_style_curate(profile_name: str) -> dict[str, str]:
    path = style_curate(profile_name)
    return {"path": str(path)}


def tw_mark_ready(draft_id: str) -> dict[str, str]:
    set_draft_status(draft_id, "ready")
    return {"draft_id": draft_id, "status": "ready"}


def tw_mark_posted(draft_id: str, url: str | None = None) -> dict[str, str]:
    set_draft_status(draft_id, "posted", url)
    return {"draft_id": draft_id, "status": "posted", "url": url or ""}


def tw_sync_posted_readonly() -> dict[str, str | int]:
    result = sync_posted()
    return {"imported": result.imported, "message": result.message}


TOOLS: dict[str, Callable[..., Any]] = {
    "tw_search_memory": tw_search_memory,
    "tw_get_project_context": tw_get_project_context,
    "tw_refresh_project_context": tw_refresh_project_context,
    "tw_save_idea": tw_save_idea,
    "tw_create_draft": tw_create_draft,
    "tw_get_draft": tw_get_draft,
    "tw_list_drafts": tw_list_drafts,
    "tw_refine_draft": tw_refine_draft,
    "tw_review_draft": tw_review_draft,
    "tw_algo_review": tw_algo_review,
    "tw_style_review": tw_style_review,
    "tw_import_telegram": tw_import_telegram,
    "tw_style_build": tw_style_build,
    "tw_style_curate": tw_style_curate,
    "tw_mark_ready": tw_mark_ready,
    "tw_mark_posted": tw_mark_posted,
    "tw_sync_posted_readonly": tw_sync_posted_readonly,
}


def tool_names() -> list[str]:
    return sorted(TOOLS)


def serve() -> int:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore
    except Exception:
        print("MCP package not installed. Install optional MCP dependencies, then run: tw mcp serve")
        print("Available local tool wrappers:")
        for name in tool_names():
            print(f"- {name}")
        return 2

    app = FastMCP("twitter-content-machine")
    for name, func in TOOLS.items():
        app.tool(name=name)(func)
    app.run()
    return 0
