from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from .algorithm_review import artifact_paths, write_algorithm_review, write_all_algorithm_layers, write_distribution_plan, write_media_plan
from .article import store_article
from .config import load_config
from .db import connect_db, resolve_draft_id, search_memory, upsert_fts
from .drafting import create_draft, refine_draft, review_draft, set_draft_status
from .identity_style import auto_select_examples, style_build, style_curate, style_refresh, style_review, write_style_stats
from .llm import codex_available, mode_description
from .project_context import detect_project, refresh_project_context
from .telegram_import import import_telegram
from .utils import iso_now, short_hash
from .workspace import ensure_workspace
from .x_analysis import analyze_own_posts, analyze_peer_posts
from .x_read import sync_posted, x_read as x_read_import


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
            f"select id, created_at, type, status, project_id, title, folder_path from drafts{where} order by created_at desc limit ?",
            (*params, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def _draft_type_from_args(args: argparse.Namespace) -> str:
    for name in ["thread", "article_note", "build_log", "question", "short"]:
        if getattr(args, name, False):
            return name.replace("_", "-")
    return "short"


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


def _cmd_draft(args: argparse.Namespace, cwd: Path | None) -> int:
    text = " ".join(args.text).strip()
    if not text and args.url:
        text = f"notes from {args.url}"
    if not text:
        print("draft text required")
        return 1
    draft = create_draft(
        text,
        _draft_type_from_args(args),
        cwd,
        args.url,
        args.copy,
        args.identity_style,
        args.identity_strength if args.identity_style else 0.0,
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


def _cmd_refine(args: argparse.Namespace) -> int:
    instruction = args.pass_name or "human"
    draft = refine_draft(args.draft_id, instruction)
    print(f"revision saved: {draft.folder / 'revisions'}")
    print(draft.final_text)
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    print(review_draft(args.draft_id))
    return 0


def _cmd_algo_review(args: argparse.Namespace) -> int:
    print(write_algorithm_review(args.draft_id))
    return 0


def _cmd_media_plan(args: argparse.Namespace) -> int:
    print(write_media_plan(args.draft_id))
    return 0


def _cmd_distribution_plan(args: argparse.Namespace) -> int:
    print(write_distribution_plan(args.draft_id))
    return 0


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


def _cmd_style_stats(args: argparse.Namespace) -> int:
    print(write_style_stats(args.profile))
    return 0


def _cmd_style_curate(args: argparse.Namespace) -> int:
    print(style_curate(args.profile, args.limit))
    return 0


def _cmd_style_review(args: argparse.Namespace) -> int:
    print(style_review(args.draft_id, args.profile, args.identity_strength))
    return 0


def _cmd_queue(args: argparse.Namespace) -> int:
    rows = list_drafts(args.status, args.project_id, args.limit)
    if not rows:
        print("no drafts")
        return 0
    for row in rows:
        print(f"{row['created_at']}  {row['status']:<8} {row['type']:<12} {row['id']}  {row['title']}")
    return 0


def _cmd_open(args: argparse.Namespace) -> int:
    draft_id = resolve_draft_id(args.draft_id)
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
    set_draft_status(args.draft_id, status, getattr(args, "url", None))
    print(f"{args.draft_id}: {status}")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    ensure_workspace()
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
        from .mcp_server import serve

        return serve()
    print("usage: tw mcp serve")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tw", description="Local draft-only X/Twitter content machine")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init").set_defaults(func=_cmd_init)
    sub.add_parser("ensure").set_defaults(func=_cmd_ensure)

    idea = sub.add_parser("idea")
    idea.add_argument("text")
    idea.add_argument("--url")
    idea.add_argument("--tags")
    idea.set_defaults(func=_cmd_idea)

    sub.add_parser("capture").set_defaults(func=_cmd_capture)

    draft = sub.add_parser("draft")
    kind = draft.add_mutually_exclusive_group()
    kind.add_argument("--short", action="store_true")
    kind.add_argument("--thread", action="store_true")
    kind.add_argument("--article-note", action="store_true", dest="article_note")
    kind.add_argument("--build-log", action="store_true", dest="build_log")
    kind.add_argument("--question", action="store_true")
    draft.add_argument("--url")
    draft.add_argument("--copy", action="store_true")
    draft.add_argument("--algo-aware", action="store_true")
    draft.add_argument("--identity-style")
    draft.add_argument("--identity-strength", type=float, default=0.35)
    draft.add_argument("--llm", choices=["auto", "manual", "codex", "openai-api"])
    draft.add_argument("--model")
    draft.add_argument("--reasoning-effort", choices=["low", "medium", "high", "xhigh"])
    draft.add_argument("--speed")
    draft.add_argument("--require-llm", action="store_true")
    draft.add_argument("--no-llm", action="store_true")
    draft.add_argument("--context-only", action="store_true")
    draft.add_argument("--print-prompt-path", action="store_true")
    draft.add_argument("text", nargs="*")
    draft.set_defaults(func=_cmd_draft)

    article = sub.add_parser("article")
    article.add_argument("url")
    article.set_defaults(func=_cmd_article)

    x_read = sub.add_parser("x-read")
    x_read.add_argument("username_or_url")
    x_read.add_argument("--limit", type=int, default=100)
    x_read.set_defaults(func=_cmd_x_read)

    sub.add_parser("sync-posted").set_defaults(func=_cmd_sync_posted)

    refine = sub.add_parser("refine")
    refine.add_argument("draft_id")
    refine.add_argument("--pass", dest="pass_name", choices=["critique", "compress", "human", "thread", "shorten", "clarify", "identity"])
    refine.set_defaults(func=_cmd_refine)

    review = sub.add_parser("review")
    review.add_argument("draft_id")
    review.set_defaults(func=_cmd_review)

    algo_review = sub.add_parser("algo-review")
    algo_review.add_argument("draft_id")
    algo_review.set_defaults(func=_cmd_algo_review)

    media_plan = sub.add_parser("media-plan")
    media_plan.add_argument("draft_id")
    media_plan.set_defaults(func=_cmd_media_plan)

    distribution_plan = sub.add_parser("distribution-plan")
    distribution_plan.add_argument("draft_id")
    distribution_plan.set_defaults(func=_cmd_distribution_plan)

    tg_import = sub.add_parser("tg-import")
    tg_import.add_argument("path")
    tg_import.add_argument("--profile", default="tg_crypto_clean")
    tg_import.add_argument("--own-name", default="Nik Nik")
    tg_import.set_defaults(func=_cmd_tg_import)

    style_build_cmd = sub.add_parser("style-build")
    style_build_cmd.add_argument("profile")
    style_build_cmd.add_argument("--auto", action="store_true")
    style_build_cmd.set_defaults(func=_cmd_style_build)

    style_refresh_cmd = sub.add_parser("style-refresh")
    style_refresh_cmd.add_argument("profile")
    style_refresh_cmd.set_defaults(func=_cmd_style_refresh)

    style_stats_cmd = sub.add_parser("style-stats")
    style_stats_cmd.add_argument("profile")
    style_stats_cmd.set_defaults(func=_cmd_style_stats)

    style_curate_cmd = sub.add_parser("style-curate")
    style_curate_cmd.add_argument("profile")
    style_curate_cmd.add_argument("--limit", type=int, default=50)
    style_curate_cmd.set_defaults(func=_cmd_style_curate)

    style_review_cmd = sub.add_parser("style-review")
    style_review_cmd.add_argument("draft_id")
    style_review_cmd.add_argument("--profile", default="tg_crypto_clean")
    style_review_cmd.add_argument("--identity-strength", type=float, default=0.35)
    style_review_cmd.set_defaults(func=_cmd_style_review)

    queue = sub.add_parser("queue")
    queue.add_argument("--status")
    queue.add_argument("--project-id")
    queue.add_argument("--limit", type=int, default=50)
    queue.set_defaults(func=_cmd_queue)

    open_cmd = sub.add_parser("open")
    open_cmd.add_argument("draft_id")
    open_cmd.add_argument("--print-path", action="store_true")
    open_cmd.set_defaults(func=_cmd_open)

    mark_ready = sub.add_parser("mark-ready")
    mark_ready.add_argument("draft_id")
    mark_ready.set_defaults(func=lambda args: _cmd_mark(args, "ready"))

    reject = sub.add_parser("reject")
    reject.add_argument("draft_id")
    reject.set_defaults(func=lambda args: _cmd_mark(args, "rejected"))

    mark_posted = sub.add_parser("mark-posted")
    mark_posted.add_argument("draft_id")
    mark_posted.add_argument("--url")
    mark_posted.set_defaults(func=lambda args: _cmd_mark(args, "posted"))

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(func=_cmd_search)

    sub.add_parser("doctor").set_defaults(func=_cmd_doctor)

    analyze_own = sub.add_parser("analyze-own")
    analyze_own.add_argument("--sync", action="store_true")
    analyze_own.set_defaults(func=_cmd_analyze_own)

    analyze_peer = sub.add_parser("analyze-peer")
    analyze_peer.add_argument("username_or_url")
    analyze_peer.add_argument("--limit", type=int, default=100)
    analyze_peer.set_defaults(func=_cmd_analyze_peer)

    refresh = sub.add_parser("refresh-context")
    refresh.add_argument("--force", action="store_true")
    refresh.set_defaults(func=_cmd_refresh_context)

    mcp = sub.add_parser("mcp")
    mcp.add_argument("mcp_command", choices=["serve"])
    mcp.set_defaults(func=_cmd_mcp)

    return parser


def run_cli(argv: list[str] | None = None, cwd: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = args.func
    try:
        if args.command in {"idea", "capture", "draft", "refresh-context"}:
            return int(func(args, cwd))
        return int(func(args))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
