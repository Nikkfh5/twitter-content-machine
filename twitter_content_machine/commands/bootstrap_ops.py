from __future__ import annotations

import argparse
from pathlib import Path

from ..bootstrap import (
    add_target_account,
    create_bootstrap_plan,
    create_digest,
    create_draft_from_digest,
    create_follow_seed_queue,
    create_graph_scan,
    graph_review_markdown,
    import_target_accounts,
    list_target_accounts,
    log_bootstrap_action,
    quote_candidates_text,
    refresh_today_operator_packet,
    refresh_today_operator_packet_live,
    rescore_target_accounts,
    today_markdown,
    weekly_review_markdown,
)
from ..x_read import x_read_setup_problem


def _cmd_bootstrap_plan(args: argparse.Namespace) -> int:
    result = create_bootstrap_plan(args.days)
    print(f"bootstrap plan: {result.id}")
    print(f"path: {result.folder}")
    print("daily: " + str(result.folder / "daily"))
    print("safety: manual-only; no auto-follow, no auto-like, no auto-post")
    return 0


def _cmd_today(args: argparse.Namespace) -> int:
    if getattr(args, "refresh", False):
        if getattr(args, "live_x", False):
            setup_problem = x_read_setup_problem()
            if setup_problem:
                print(setup_problem)
                return 1
            print(refresh_today_operator_packet_live())
            return 0
        print(refresh_today_operator_packet())
        return 0
    print(today_markdown())
    return 0


def _cmd_log_action(args: argparse.Namespace) -> int:
    status = "done" if args.done else "skipped"
    ok = log_bootstrap_action(args.action_id, status, args.note or "")
    if not ok:
        print(f"action not found: {args.action_id}")
        return 1
    print(f"{args.action_id}: {status}")
    return 0


def _cmd_follow_seed(args: argparse.Namespace) -> int:
    path = create_follow_seed_queue(args.cluster, args.limit)
    print(f"manual follow queue: {path}")
    print("Open accounts manually. This command does not follow anyone.")
    return 0


def _cmd_graph_scan(args: argparse.Namespace) -> int:
    setup_problem = x_read_setup_problem()
    if setup_problem:
        print(setup_problem)
        return 1
    result = create_graph_scan(
        cluster=args.cluster,
        limit_accounts=args.limit,
        limit_posts=args.posts,
        include_seed_following=not args.no_seed_following,
    )
    print(f"graph scan: {result.id}")
    print(f"path: {result.folder}")
    print(f"accounts: {result.account_count}")
    print(f"posts: {result.post_count}")
    if result.warnings:
        print("x provider warnings:")
        for item in result.warnings[:5]:
            print(f"- {item}")
        if result.account_count == 0 and result.post_count == 0:
            print("No live X data returned. Use curated/manual seeds or check X API plan/limits.")
            return 1
    if result.queue_path:
        print(f"manual follow queue: {result.queue_path}")
    print("safety: read-only scan; no X write actions")
    return 0


def _cmd_target_accounts(args: argparse.Namespace) -> int:
    if args.target_accounts_command == "add":
        account_id = add_target_account(args.handle, args.cluster, args.note or "")
        print(f"target account: {account_id} {args.handle}")
        return 0
    if args.target_accounts_command == "import":
        count = import_target_accounts(Path(args.path), args.cluster)
        print(f"imported target accounts: {count}")
        return 0
    if args.target_accounts_command == "list":
        rows = list_target_accounts(args.cluster)
        if not rows:
            print("no target accounts")
            return 0
        for row in rows:
            print(
                f"@{row['handle']}  {row['cluster']}  "
                f"rel={row['relevance_score']:.2f} fit={row['social_fit_score']:.2f} "
                f"noise={row['noise_score']:.2f}  {row['notes']}"
            )
        return 0
    if args.target_accounts_command == "score":
        count = rescore_target_accounts(args.cluster)
        print(f"scored target accounts: {count}")
        return 0
    print("target-accounts command required")
    return 1


def _cmd_x_digest(args: argparse.Namespace) -> int:
    language = "ru" if args.ru else "en" if args.en else None
    result = create_digest(args.cluster, args.limit, language)
    print(f"digest: {result.id}")
    print(f"path: {result.folder}")
    print(f"raw items: {result.raw_count}")
    if result.raw_count == 0:
        print("No cached/read-only source posts found. Import with x-read or target-accounts import first.")
    return 0


def _cmd_draft_from_digest(args: argparse.Namespace, cwd: Path | None = None) -> int:
    draft_type = "thread" if args.thread else "short"
    draft = create_draft_from_digest(args.target, draft_type, cwd, no_llm=args.no_llm)
    print(f"draft: {draft.id}")
    print(f"path: {draft.folder}")
    print("")
    print(draft.final_text)
    return 0


def _cmd_quote_candidates(args: argparse.Namespace) -> int:
    path, text = quote_candidates_text(args.target)
    if path:
        print(f"quote candidates: {path}")
        print("")
    print(text)
    return 0


def _cmd_graph_review(args: argparse.Namespace) -> int:
    print(graph_review_markdown())
    return 0


def _cmd_weekly_review(args: argparse.Namespace) -> int:
    print(weekly_review_markdown())
    return 0
