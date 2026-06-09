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

def _cmd_tg_import(args: argparse.Namespace) -> int:
    result = import_telegram(args.path, args.profile, args.own_name)
    print(f"profile: {result.profile_name}")
    print(f"path: {result.profile_dir}")
    print(f"imported: {result.imported}")
    print(f"own_original: {result.own_original}")
    print(f"forwarded_other: {result.forwarded_other}")
    return 0

def _cmd_style_build(args: argparse.Namespace) -> int:
    path = style_build(args.profile)
    print(path)
    if args.auto:
        print(auto_select_examples(args.profile))
    return 0

def _cmd_style_refresh(args: argparse.Namespace) -> int:
    print(style_refresh(args.profile))
    return 0

def _cmd_style_learn(args: argparse.Namespace) -> int:
    print(style_learn(args.profile))
    return 0

def _cmd_style_stats(args: argparse.Namespace) -> int:
    print(write_style_stats(args.profile))
    return 0

def _cmd_style_curate(args: argparse.Namespace) -> int:
    print(style_curate(args.profile, args.limit))
    return 0

def _cmd_style_review(args: argparse.Namespace) -> int:
    print(style_review(resolve_active_draft_id(getattr(args, "draft_id", None)), args.profile, args.identity_strength))
    return 0

def _cmd_style_gold_import(args: argparse.Namespace) -> int:
    result = import_style_content_gold(args.path)
    print(f"profile: {result.profile_dir}")
    for path in result.imported:
        print(f"imported: {path}")
    print(f"report: {result.report_path}")
    return 0

