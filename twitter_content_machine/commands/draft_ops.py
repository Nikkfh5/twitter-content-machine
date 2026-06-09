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

def _draft_type_from_args(args: argparse.Namespace) -> str:
    for name in ["thread", "article_note", "build_log", "question", "short"]:
        if getattr(args, name, False):
            return name.replace("_", "-")
    return "adaptive"

def _built_identity_profile_exists(profile_name: str) -> bool:
    ensure_workspace()
    with connect_db() as conn:
        row = conn.execute(
            "select status from identity_style_profiles where profile_name = ?",
            (profile_name,),
        ).fetchone()
    return bool(row and row["status"] == "built")

def _identity_style_from_args(args: argparse.Namespace) -> str | None:
    if args.identity_style:
        if args.identity_style.lower() in {"none", "off", "no", "false"}:
            return None
        return args.identity_style
    default_profile = DEFAULT_IDENTITY_PROFILE
    return default_profile if _built_identity_profile_exists(default_profile) else None

def _cmd_draft(args: argparse.Namespace, cwd: Path | None) -> int:
    text = " ".join(args.text).strip()
    if not text and args.url:
        text = f"notes from {args.url}"
    if not text:
        print("draft text required")
        return 1
    identity_style = _identity_style_from_args(args)
    draft = create_draft(
        text,
        _draft_type_from_args(args),
        cwd,
        args.url,
        args.copy,
        identity_style,
        args.identity_strength if identity_style else 0.0,
        args.llm,
        args.model,
        args.reasoning_effort,
        args.speed,
        args.require_llm,
        args.no_llm,
        args.context_only,
    )
    algo_paths = write_all_algorithm_layers(draft.id) if args.algo_aware else None
    print(f"draft: {draft.id}")
    print(f"path: {draft.folder}")
    if args.print_prompt_path:
        print(draft.folder / "14_llm_request.md")
    if algo_paths:
        print("algorithm-aware review:")
        print(artifact_paths(algo_paths))
    print("")
    print(draft.final_text)
    return 0

def _cmd_refine(args: argparse.Namespace) -> int:
    instruction = args.pass_name or "human"
    draft_id = resolve_active_draft_id(getattr(args, "draft_id", None))
    draft = refine_draft(draft_id, instruction)
    set_current_draft(draft.id)
    print(f"revision saved: {draft.folder / 'revisions'}")
    print(draft.final_text)
    return 0

def _cmd_review(args: argparse.Namespace) -> int:
    print(review_draft(resolve_active_draft_id(getattr(args, "draft_id", None))))
    return 0

def _cmd_algo_review(args: argparse.Namespace) -> int:
    print(write_algorithm_review(resolve_active_draft_id(getattr(args, "draft_id", None))))
    return 0

def _cmd_media_plan(args: argparse.Namespace) -> int:
    print(write_media_plan(resolve_active_draft_id(getattr(args, "draft_id", None))))
    return 0

def _cmd_distribution_plan(args: argparse.Namespace) -> int:
    print(write_distribution_plan(resolve_active_draft_id(getattr(args, "draft_id", None))))
    return 0

def _cmd_algo(args: argparse.Namespace) -> int:
    draft_id = resolve_active_draft_id(getattr(args, "draft_id", None))
    paths = write_all_algorithm_layers(draft_id)
    print(artifact_paths(paths))
    return 0

def _cmd_edit(args: argparse.Namespace) -> int:
    instruction = " ".join(args.instruction).strip()
    if not instruction:
        print("edit instruction required")
        return 1
    result = edit_draft_with_codex(getattr(args, "draft_id", None), instruction)
    print(f"revision: {result.revision_path}")
    print("")
    print(result.final_text)
    return 0

def _cmd_codex(args: argparse.Namespace, cwd: Path | None = None) -> int:
    output_mode = "thread" if args.thread else "final-post"
    instruction = " ".join(args.instruction or []).strip()
    session = prepare_codex_session(
        draft_id=args.draft_id,
        source_file=args.file,
        output_mode=output_mode,
        instruction=instruction,
        cwd=cwd,
    )
    print(f"session: {session.session_dir}")
    print(f"cd: {session.session_dir}")
    print("command: " + " ".join(str(part) for part in session.command))
    if args.print_command:
        return 0
    if args.run:
        ran = run_codex_session(session)
        print(f"codex exit: {ran.returncode}")
        return int(ran.returncode or 0)
    if args.prepare:
        return 0
    print("prepared. Run with: tw codex --run")
    return 0

