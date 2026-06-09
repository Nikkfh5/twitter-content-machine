from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .cli_commands import (
    DEFAULT_IDENTITY_PROFILE,
    _cmd_algo,
    _cmd_algo_review,
    _cmd_analyze_own,
    _cmd_analyze_peer,
    _cmd_article,
    _cmd_capture,
    _cmd_codex,
    _cmd_distribution_plan,
    _cmd_doctor,
    _cmd_draft,
    _cmd_drafts,
    _cmd_edit,
    _cmd_ensure,
    _cmd_idea,
    _cmd_init,
    _cmd_mark,
    _cmd_mcp,
    _cmd_media_plan,
    _cmd_open,
    _cmd_path,
    _cmd_queue,
    _cmd_refine,
    _cmd_refresh_context,
    _cmd_review,
    _cmd_search,
    _cmd_show,
    _cmd_style_build,
    _cmd_style_curate,
    _cmd_style_gold_import,
    _cmd_style_learn,
    _cmd_style_refresh,
    _cmd_style_review,
    _cmd_style_stats,
    _cmd_sync_posted,
    _cmd_tg_import,
    _cmd_use,
    _cmd_x_read,
    list_drafts,
    save_idea,
)

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
    draft.set_defaults(algo_aware=True)
    draft.add_argument("--algo-aware", dest="algo_aware", action="store_true")
    draft.add_argument("--no-algo-aware", dest="algo_aware", action="store_false")
    draft.add_argument("--identity-style")
    draft.add_argument("--identity-strength", type=float, default=0.35)
    draft.add_argument("--llm", choices=["auto", "codex"])
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
    refine.add_argument("draft_id", nargs="?")
    refine.add_argument("--pass", dest="pass_name", choices=["critique", "compress", "human", "thread", "shorten", "clarify", "identity"])
    refine.set_defaults(func=_cmd_refine)

    review = sub.add_parser("review")
    review.add_argument("draft_id", nargs="?")
    review.set_defaults(func=_cmd_review)

    algo_review = sub.add_parser("algo-review")
    algo_review.add_argument("draft_id", nargs="?")
    algo_review.set_defaults(func=_cmd_algo_review)

    media_plan = sub.add_parser("media-plan")
    media_plan.add_argument("draft_id", nargs="?")
    media_plan.set_defaults(func=_cmd_media_plan)

    distribution_plan = sub.add_parser("distribution-plan")
    distribution_plan.add_argument("draft_id", nargs="?")
    distribution_plan.set_defaults(func=_cmd_distribution_plan)

    tg_import = sub.add_parser("tg-import")
    tg_import.add_argument("path")
    tg_import.add_argument("--profile", default="tg_crypto_clean")
    tg_import.add_argument("--own-name", default="Nik Nik")
    tg_import.set_defaults(func=_cmd_tg_import)

    style_build_cmd = sub.add_parser("style-build")
    style_build_cmd.add_argument("profile", nargs="?", default=DEFAULT_IDENTITY_PROFILE)
    style_build_cmd.add_argument("--auto", action="store_true")
    style_build_cmd.set_defaults(func=_cmd_style_build)

    style_refresh_cmd = sub.add_parser("style-refresh")
    style_refresh_cmd.add_argument("profile", nargs="?", default=DEFAULT_IDENTITY_PROFILE)
    style_refresh_cmd.set_defaults(func=_cmd_style_refresh)

    style_learn_cmd = sub.add_parser("style-learn")
    style_learn_cmd.set_defaults(profile=DEFAULT_IDENTITY_PROFILE, func=_cmd_style_learn)

    style_stats_cmd = sub.add_parser("style-stats")
    style_stats_cmd.add_argument("profile", nargs="?", default=DEFAULT_IDENTITY_PROFILE)
    style_stats_cmd.set_defaults(func=_cmd_style_stats)

    style_curate_cmd = sub.add_parser("style-curate")
    style_curate_cmd.add_argument("profile", nargs="?", default=DEFAULT_IDENTITY_PROFILE)
    style_curate_cmd.add_argument("--limit", type=int, default=50)
    style_curate_cmd.set_defaults(func=_cmd_style_curate)

    style_review_cmd = sub.add_parser("style-review")
    style_review_cmd.add_argument("draft_id", nargs="?")
    style_review_cmd.add_argument("--profile", default="tg_crypto_clean")
    style_review_cmd.add_argument("--identity-strength", type=float, default=0.35)
    style_review_cmd.set_defaults(func=_cmd_style_review)

    style_gold_import = sub.add_parser("style-gold-import")
    style_gold_import.add_argument("path")
    style_gold_import.set_defaults(func=_cmd_style_gold_import)

    queue = sub.add_parser("queue")
    queue.add_argument("--status")
    queue.add_argument("--project-id")
    queue.add_argument("--limit", type=int, default=50)
    queue.set_defaults(func=_cmd_queue)

    drafts_cmd = sub.add_parser("drafts")
    drafts_cmd.add_argument("--status")
    drafts_cmd.add_argument("--project-id")
    drafts_cmd.add_argument("--limit", type=int, default=20)
    drafts_cmd.set_defaults(func=_cmd_drafts)

    use_cmd = sub.add_parser("use")
    use_cmd.add_argument("target")
    use_cmd.set_defaults(func=_cmd_use)

    show_cmd = sub.add_parser("show")
    show_cmd.add_argument("draft_id", nargs="?")
    show_cmd.set_defaults(func=_cmd_show)

    path_cmd = sub.add_parser("path")
    path_cmd.add_argument("draft_id", nargs="?")
    path_cmd.set_defaults(func=_cmd_path)

    algo_cmd = sub.add_parser("algo")
    algo_cmd.add_argument("draft_id", nargs="?")
    algo_cmd.set_defaults(func=_cmd_algo)

    edit_cmd = sub.add_parser("edit")
    edit_cmd.add_argument("instruction", nargs="*")
    edit_cmd.add_argument("--draft-id")
    edit_cmd.set_defaults(func=_cmd_edit)

    codex_cmd = sub.add_parser("codex")
    codex_cmd.add_argument("draft_id", nargs="?")
    codex_cmd.add_argument("--file")
    codex_mode = codex_cmd.add_mutually_exclusive_group()
    codex_mode.add_argument("--thread", action="store_true")
    codex_mode.add_argument("--final-post", action="store_true")
    codex_cmd.add_argument("--prepare", action="store_true")
    codex_cmd.add_argument("--run", action="store_true")
    codex_cmd.add_argument("--print-command", action="store_true")
    codex_cmd.add_argument("--instruction", nargs="*")
    codex_cmd.set_defaults(func=_cmd_codex)

    open_cmd = sub.add_parser("open")
    open_cmd.add_argument("draft_id", nargs="?")
    open_cmd.add_argument("--print-path", action="store_true")
    open_cmd.set_defaults(func=_cmd_open)

    mark_ready = sub.add_parser("mark-ready")
    mark_ready.add_argument("draft_id", nargs="?")
    mark_ready.set_defaults(func=lambda args: _cmd_mark(args, "ready"))

    ready = sub.add_parser("ready")
    ready.add_argument("draft_id", nargs="?")
    ready.set_defaults(func=lambda args: _cmd_mark(args, "ready"))

    reject = sub.add_parser("reject")
    reject.add_argument("draft_id", nargs="?")
    reject.set_defaults(func=lambda args: _cmd_mark(args, "rejected"))

    mark_posted = sub.add_parser("mark-posted")
    mark_posted.add_argument("draft_id", nargs="?")
    mark_posted.add_argument("--url")
    mark_posted.set_defaults(func=lambda args: _cmd_mark(args, "posted"))

    posted = sub.add_parser("posted")
    posted.add_argument("draft_id", nargs="?")
    posted.add_argument("--url")
    posted.set_defaults(func=lambda args: _cmd_mark(args, "posted"))

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--smart", action="store_true")
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
        if args.command in {"idea", "capture", "draft", "refresh-context", "search", "codex"}:
            return int(func(args, cwd))
        return int(func(args))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
