from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from ..algorithm_review import artifact_paths, write_algorithm_review, write_all_algorithm_layers, write_distribution_plan, write_media_plan
from ..article import store_article
from ..config import load_config
from ..codex_session import prepare_codex_session, run_codex_session
from ..db import connect_db, resolve_draft_id, search_memory, upsert_fts
from ..drafting import create_draft, refine_draft, review_draft, set_draft_status
from ..editing import edit_draft_with_codex
from ..identity_style import (
    DEFAULT_IDENTITY_PROFILE,
    auto_select_examples,
    style_build,
    style_curate,
    style_learn,
    style_refresh,
    style_review,
    write_style_stats,
)
from ..llm import codex_available, mode_description
from ..project_context import detect_project, refresh_project_context
from ..smart_search import run_smart_search
from ..state import draft_id_from_list_number, get_current_draft_id, resolve_active_draft_id, set_current_draft
from ..style_gold import import_style_content_gold
from ..telegram_import import import_telegram
from ..utils import iso_now, short_hash
from ..workspace import ensure_workspace
from ..x_analysis import analyze_own_posts, analyze_peer_posts
from ..x_read import sync_posted, x_read as x_read_import

def save_idea(text: str, cwd: Path | None = None, url: str | None = None, tags: str = "") -> str:
    workspace = ensure_workspace()
    project = detect_project(cwd)
    refresh_project_context(project)
    idea_id = f"idea_{short_hash(project.id + text + iso_now(), 12)}"
    now = iso_now()
    with connect_db() as conn:
        conn.execute(
            "insert into ideas(id, created_at, project_id, raw_text, source_url, tags, status) values(?, ?, ?, ?, ?, ?, ?)",
            (idea_id, now, project.id, text, url or "", tags, "captured"),
        )
        upsert_fts(conn, "ideas_fts", (idea_id, text, tags))
    ideas_path = workspace.root / "inbox" / "ideas.md"
    with ideas_path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {now} {idea_id}\n\n{text}\n\n")
        if url:
            fh.write(f"Source: {url}\n")
        if tags:
            fh.write(f"Tags: {tags}\n")
    return idea_id

def list_drafts(status: str | None = None, project_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    ensure_workspace()
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)
    where = " where " + " and ".join(clauses) if clauses else ""
    with connect_db() as conn:
        rows = conn.execute(
            f"select id, created_at, type, status, project_id, title, folder_path from drafts{where} order by created_at desc, rowid desc limit ?",
            (*params, limit),
        ).fetchall()
    return [dict(row) for row in rows]

def _cmd_init(args: argparse.Namespace) -> int:
    workspace = ensure_workspace()
    print(f"workspace: {workspace.root}")
    return 0

def _cmd_ensure(args: argparse.Namespace) -> int:
    workspace = ensure_workspace()
    print(f"ok: {workspace.root}")
    return 0

def _cmd_idea(args: argparse.Namespace, cwd: Path | None) -> int:
    idea_id = save_idea(args.text, cwd, args.url, args.tags or "")
    print(f"stored idea: {idea_id}")
    return 0

def _cmd_capture(args: argparse.Namespace, cwd: Path | None) -> int:
    text = input("idea> ").strip()
    url = input("url optional> ").strip() or None
    tags = input("tags optional> ").strip()
    if not text:
        print("empty idea; nothing stored")
        return 1
    idea_id = save_idea(text, cwd, url, tags)
    print(f"stored idea: {idea_id}")
    return 0

def _print_draft_rows(rows: list[dict[str, Any]], numbered: bool = False) -> None:
    current = get_current_draft_id()
    for index, row in enumerate(rows, start=1):
        active = "*" if row["id"] == current else " "
        prefix = f"{active} {index:<2} " if numbered else f"{active} "
        print(f"{prefix}{row['created_at']}  {row['status']:<8} {row['type']:<12} {row['id']}  {row['title']}")

def _cmd_queue(args: argparse.Namespace) -> int:
    rows = list_drafts(args.status, args.project_id, args.limit)
    if not rows:
        print("no drafts")
        return 0
    _print_draft_rows(rows)
    return 0

def _cmd_drafts(args: argparse.Namespace) -> int:
    rows = list_drafts(args.status, args.project_id, args.limit)
    if not rows:
        print("no drafts")
        return 0
    _print_draft_rows(rows, numbered=True)
    return 0

def _cmd_use(args: argparse.Namespace) -> int:
    rows = list_drafts(limit=100)
    draft_id = draft_id_from_list_number(args.target, rows) or resolve_active_draft_id(args.target)
    with connect_db() as conn:
        row = conn.execute("select id, folder_path from drafts where id = ?", (draft_id,)).fetchone()
    if not row:
        print(f"draft not found: {args.target}")
        return 1
    set_current_draft(draft_id)
    print(f"current draft: {draft_id}")
    print(row["folder_path"])
    return 0

def _cmd_show(args: argparse.Namespace) -> int:
    draft_id = resolve_active_draft_id(getattr(args, "draft_id", None))
    with connect_db() as conn:
        row = conn.execute("select final_text from drafts where id = ?", (draft_id,)).fetchone()
    if not row:
        print(f"draft not found: {draft_id}")
        return 1
    print(row["final_text"] or "")
    return 0

def _cmd_path(args: argparse.Namespace) -> int:
    draft_id = resolve_active_draft_id(getattr(args, "draft_id", None))
    with connect_db() as conn:
        row = conn.execute("select folder_path from drafts where id = ?", (draft_id,)).fetchone()
    if not row:
        print(f"draft not found: {draft_id}")
        return 1
    print(row["folder_path"])
    return 0

def _cmd_open(args: argparse.Namespace) -> int:
    draft_id = resolve_active_draft_id(getattr(args, "draft_id", None))
    with connect_db() as conn:
        row = conn.execute("select folder_path from drafts where id = ?", (draft_id,)).fetchone()
    if not row:
        print(f"draft not found: {args.draft_id}")
        return 1
    folder = Path(row["folder_path"])
    if args.print_path:
        print(folder)
        return 0
    if os.name == "nt":
        os.startfile(folder)  # type: ignore[attr-defined]
    else:
        import subprocess

        subprocess.run(["xdg-open", str(folder)], check=False)
    print(folder)
    return 0

def _cmd_mark(args: argparse.Namespace, status: str) -> int:
    draft_id = resolve_active_draft_id(getattr(args, "draft_id", None))
    set_draft_status(draft_id, status, getattr(args, "url", None))
    set_current_draft(draft_id)
    print(f"{draft_id}: {status}")
    return 0

def _cmd_doctor(args: argparse.Namespace) -> int:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    print(f"workspace: {workspace.root}")
    print(f"db: {workspace.db_path}")
    print(f"llm: {config.llm_mode} ({mode_description(config.llm_mode)})")
    print(f"llm model: {config.llm_model}")
    print(f"llm reasoning_effort: {config.llm_reasoning_effort}")
    print(f"llm speed: {config.llm_speed}")
    print(f"codex CLI: {'available' if codex_available() else 'not detected'}")
    print(f"x provider: {config.x_provider}")
    print(f"x readonly: {config.x_readonly}")
    with connect_db() as conn:
        profile_count = conn.execute("select count(*) from identity_style_profiles").fetchone()[0]
        tg_count = conn.execute("select count(*) from telegram_messages").fetchone()[0]
    print(f"identity profiles: {profile_count}")
    print(f"telegram messages: {tg_count}")
    if config.x_provider == "none":
        print("warning: read-only X sync disabled; tw sync-posted will exit cleanly")
    print("safety: draft-only; no publish command is exposed")
    return 0

def _cmd_refresh_context(args: argparse.Namespace, cwd: Path | None) -> int:
    project = detect_project(cwd)
    context = refresh_project_context(project, force=args.force)
    print(f"project: {project.id}")
    print(f"context: {context.context_path}")
    return 0

def _cmd_mcp(args: argparse.Namespace) -> int:
    if args.mcp_command == "serve":
        from ..mcp_server import serve

        return serve()
    print("usage: tw mcp serve")
    return 1

