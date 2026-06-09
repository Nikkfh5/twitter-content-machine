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

def _cmd_article(args: argparse.Namespace) -> int:
    ensure_workspace()
    source_id = store_article(args.url)
    print(f"stored source: {source_id}")
    print("Run draft with: tw draft --article-note --url " + args.url)
    return 0

def _cmd_x_read(args: argparse.Namespace) -> int:
    ensure_workspace()
    result = x_read_import(args.username_or_url, args.limit)
    print(result.message)
    if result.imported:
        print(f"imported: {result.imported}")
    if result.imported == 0 and "complete" not in result.message.lower():
        return 1
    return 0

def _cmd_sync_posted(args: argparse.Namespace) -> int:
    result = sync_posted()
    print(result.message)
    if result.imported:
        print(f"imported: {result.imported}")
    return 0

def _cmd_search(args: argparse.Namespace, cwd: Path | None = None) -> int:
    ensure_workspace()
    if args.smart:
        result = run_smart_search(args.query, args.limit, cwd)
        if result is None:
            print("no matches")
            return 0
        print(result.output)
        print("")
        print(f"search log: {result.folder}")
        return 0
    rows = search_memory(args.query, args.limit)
    if not rows:
        print("no matches")
        return 0
    for row in rows:
        text = " ".join(row["text"].split())[:240]
        print(f"{row['type']}: {row['id']}  {text}")
    return 0

def _cmd_analyze_own(args: argparse.Namespace) -> int:
    ensure_workspace()
    if args.sync:
        result = sync_posted()
        print(result.message)
    print(analyze_own_posts())
    return 0

def _cmd_analyze_peer(args: argparse.Namespace) -> int:
    ensure_workspace()
    result = x_read_import(args.username_or_url, args.limit)
    print(result.message)
    print(analyze_peer_posts(args.username_or_url))
    return 0

