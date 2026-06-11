from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Config, load_config
from .db import connect_db, upsert_fts
from .utils import get_now, iso_now, short_hash
from .workspace import ensure_workspace, read_profile
from .x_read import get_provider


DEFAULT_BOOTSTRAP_CLUSTERS = ["quant", "systems", "ml_infra", "ai_agents", "builders"]


@dataclass(frozen=True)
class BootstrapPlanResult:
    id: str
    folder: Path
    days: int


@dataclass(frozen=True)
class DigestResult:
    id: str
    folder: Path
    raw_count: int


@dataclass(frozen=True)
class GraphScanResult:
    id: str
    folder: Path
    cluster: str
    account_count: int
    post_count: int
    queue_path: Path | None
    warnings: list[str] | None = None


@dataclass(frozen=True)
class QualityDecision:
    accepted: bool
    relevance: float
    noise: float
    reasons: list[str]


def normalize_handle(value: str) -> str:
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        parts = [part for part in value.split("/") if part]
        value = parts[-1] if parts else value
    return value.lstrip("@").strip().lower()


def display_handle(value: str) -> str:
    handle = normalize_handle(value)
    return f"@{handle}" if handle else ""


def create_bootstrap_plan(days: int | None = None) -> BootstrapPlanResult:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    days = _bounded_days(days or config.bootstrap_plan_days)
    now = get_now()
    plan_id = f"{now:%Y%m%d}-{days}day-bootstrap"
    folder = workspace.root / "graph" / "plans" / plan_id
    daily_dir = folder / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)

    account_state = _account_state_markdown()
    strategy = _graph_strategy_markdown(config)
    personal_strategy = _personal_strategy_markdown(config)
    actions_by_day = {
        day: [_scoped_action(plan_id, action) for action in _actions_for_day(day, days, config)]
        for day in range(1, days + 1)
    }
    plan_md = _plan_markdown(plan_id, days, config, actions_by_day)
    plan_json = {
        "id": plan_id,
        "created_at": iso_now(),
        "days": days,
        "stage": config.bootstrap_account_stage,
        "interaction_mode": config.bootstrap_interaction_mode,
        "daily_follow_budget": config.bootstrap_daily_follow_budget,
        "manual_social_budget_minutes": config.bootstrap_manual_social_budget_minutes,
        "clusters": config.bootstrap_default_clusters,
        "actions": actions_by_day,
    }

    (folder / "plan.md").write_text(plan_md, encoding="utf-8")
    (folder / "plan.json").write_text(
        json.dumps(plan_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (folder / "account_state.md").write_text(account_state, encoding="utf-8")
    (folder / "graph_strategy.md").write_text(strategy, encoding="utf-8")
    (folder / "personal_strategy.md").write_text(personal_strategy, encoding="utf-8")
    for day, actions in actions_by_day.items():
        (daily_dir / f"day_{day:02d}.md").write_text(
            _daily_markdown(day, days, actions, config),
            encoding="utf-8",
        )

    with connect_db() as conn:
        conn.execute("delete from bootstrap_actions where plan_id = ?", (plan_id,))
        conn.execute(
            """
            insert or replace into bootstrap_plans(
              id, created_at, days, stage, interaction_mode, folder_path, status
            )
            values(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                iso_now(),
                days,
                config.bootstrap_account_stage,
                config.bootstrap_interaction_mode,
                str(folder),
                "active",
            ),
        )
        for day, actions in actions_by_day.items():
            for action in actions:
                conn.execute(
                    """
                    insert into bootstrap_actions(
                      id, plan_id, day, action_type, title, details, status,
                      created_at, updated_at
                    )
                    values(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        action["id"],
                        plan_id,
                        day,
                        action["action_type"],
                        action["title"],
                        action["details"],
                        "planned",
                        iso_now(),
                        iso_now(),
                    ),
                )
    return BootstrapPlanResult(plan_id, folder, days)


def today_markdown() -> str:
    workspace = ensure_workspace()
    plan = _latest_active_plan()
    if not plan:
        return "No active bootstrap plan. Run: tw bootstrap-plan --days 14"
    day = _current_plan_day(plan)
    with connect_db() as conn:
        rows = conn.execute(
            """
            select id, action_type, title, details, status
            from bootstrap_actions
            where plan_id = ? and day = ?
            order by rowid
            """,
            (plan["id"], day),
        ).fetchall()
    daily_file = Path(plan["folder_path"]) / "daily" / f"day_{day:02d}.md"
    lines = [
        f"Today, day {day}/{plan['days']}:",
        "",
        "No mandatory replies. No feed-reading required.",
        f"Daily file: {daily_file}",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        status = "" if row["status"] == "planned" else f" [{row['status']}]"
        lines.append(f"{index}. {row['title']}{status}")
        lines.append(f"   id: {row['id']}")
        lines.append(f"   {row['details']}")
    lines.append("")
    lines.append("Manual execution only: no auto-follow, no auto-like, no auto-post.")
    return "\n".join(lines)


def refresh_today_operator_packet() -> str:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    plan = _latest_active_plan()
    if not plan:
        return "No active bootstrap plan. Run: tw bootstrap --days 14"
    day = _current_plan_day(plan)
    cluster = _cluster_for_day(day, config)
    target_rows = list_target_accounts(cluster)[: config.bootstrap_daily_follow_budget]
    handles = [row["handle"] for row in target_rows]
    source_rows = _cached_source_posts(handles, 25)
    items = [_source_row_to_digest_item(row, cluster) for row in source_rows]
    daily_dir = Path(plan["folder_path"]) / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    packet_path = daily_dir / f"day_{day:02d}_operator.md"
    text = _daily_operator_packet_markdown(
        day=day,
        days=int(plan["days"]),
        cluster=cluster,
        target_rows=target_rows,
        items=items,
        config=config,
        scan_result=None,
    )
    packet_path.write_text(text, encoding="utf-8")
    return f"{text}\n\nDaily operator packet: {packet_path}"


def refresh_today_operator_packet_live() -> str:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    plan = _latest_active_plan()
    if not plan:
        return "No active bootstrap plan. Run: tw bootstrap --days 14"
    day = _current_plan_day(plan)
    cluster = _cluster_for_day(day, config)
    scan_result = create_graph_scan(
        cluster=cluster,
        limit_accounts=config.bootstrap_daily_follow_budget * 2,
        limit_posts=50,
    )
    target_rows = list_target_accounts(cluster)[: config.bootstrap_daily_follow_budget]
    source_rows = _cached_source_posts([row["handle"] for row in target_rows], 25)
    items = [_source_row_to_digest_item(row, cluster) for row in source_rows]
    daily_dir = Path(plan["folder_path"]) / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    packet_path = daily_dir / f"day_{day:02d}_operator.md"
    text = _daily_operator_packet_markdown(
        day=day,
        days=int(plan["days"]),
        cluster=cluster,
        target_rows=target_rows,
        items=items,
        config=config,
        scan_result=scan_result,
    )
    packet_path.write_text(text, encoding="utf-8")
    return f"{text}\n\nDaily operator packet: {packet_path}"


def log_bootstrap_action(action_id: str, status: str, note: str = "") -> bool:
    ensure_workspace()
    if status not in {"done", "skipped"}:
        raise ValueError("status must be done or skipped")
    with connect_db() as conn:
        row = conn.execute(
            "select details from bootstrap_actions where id = ?",
            (action_id,),
        ).fetchone()
        if not row:
            return False
        details = row["details"] or ""
        if note:
            details = details.rstrip() + f"\n\nLog note: {note}"
        conn.execute(
            "update bootstrap_actions set status = ?, details = ?, updated_at = ? where id = ?",
            (status, details, iso_now(), action_id),
        )
    return True


def add_target_account(
    handle: str,
    cluster: str,
    note: str = "",
    source: str = "manual",
    display_name: str = "",
    description: str = "",
    language: str = "",
    user_id: str = "",
    followers_count: int | None = None,
    following_count: int | None = None,
    verified: bool | None = None,
) -> str:
    ensure_workspace()
    clean = normalize_handle(handle)
    if not clean:
        raise ValueError("handle required")
    cluster = normalize_cluster(cluster)
    account_id = f"acct_{short_hash(clean, 12)}"
    relevance, social_fit, noise = score_account_fields(cluster, note, description)
    with connect_db() as conn:
        conn.execute(
            """
            insert or replace into target_accounts(
              id, handle, display_name, user_id, cluster, source, url,
              followers_count, following_count, verified, description, language,
              relevance_score, social_fit_score, noise_score, status, notes,
              created_at, updated_at
            )
            values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                clean,
                display_name,
                user_id,
                cluster,
                source,
                f"https://x.com/{clean}",
                followers_count,
                following_count,
                1 if verified else 0 if verified is not None else None,
                description,
                language,
                relevance,
                social_fit,
                noise,
                "candidate",
                note,
                iso_now(),
                iso_now(),
            ),
        )
        upsert_fts(conn, "target_accounts_fts", (account_id, clean, display_name, description, note))
    return account_id


def create_graph_scan(
    cluster: str,
    limit_accounts: int = 30,
    limit_posts: int = 50,
    include_seed_following: bool = True,
) -> GraphScanResult:
    workspace = ensure_workspace()
    cluster = normalize_cluster(cluster)
    limit_accounts = max(1, min(100, limit_accounts))
    limit_posts = max(10, min(100, limit_posts))
    provider = get_provider()
    queries = _cluster_search_queries(cluster)
    now = get_now()
    scan_id = f"scan_{now:%Y%m%d_%H%M}_{cluster}"
    folder = workspace.root / "graph" / "scans" / f"{now:%Y%m%d-%H%M}-{cluster}"
    folder.mkdir(parents=True, exist_ok=True)

    user_candidates: list[dict[str, Any]] = []
    post_candidates: list[dict[str, Any]] = []
    for query in queries:
        user_candidates.extend(_tag_source(provider.search_users(query, limit_accounts), "user_search", query))
        post_candidates.extend(_tag_source(provider.search_recent_posts(query, limit_posts), "recent_post_search", query))
    if include_seed_following:
        for seed in list_target_accounts(cluster)[:3]:
            user_candidates.extend(
                _tag_source(provider.get_user_following(seed["handle"], 50), "seed_following", seed["handle"])
            )

    all_users = _dedupe_users(user_candidates)
    all_posts = _dedupe_posts(post_candidates)
    users, user_rejects = _filter_scan_users(cluster, all_users)
    posts, post_rejects = _filter_scan_posts(cluster, all_posts)
    post_author_candidates = _dedupe_users([author for post in posts if (author := _user_from_post(post))])
    post_authors, post_author_rejects = _filter_scan_users(cluster, post_author_candidates)
    combined_users = _dedupe_users([*users, *post_authors])
    rejects = [*user_rejects, *post_rejects, *post_author_rejects]

    _clear_scan_derived_targets(cluster)
    for user in combined_users:
        _store_scan_user(user, cluster)
    for post in posts:
        _store_scan_post(post, cluster)
    rescore_target_accounts(cluster)
    queue_path = create_follow_seed_queue(cluster, limit_accounts) if combined_users or posts else None
    provider_warnings = list(getattr(provider, "errors", []) or [])

    (folder / "raw_users.json").write_text(
        json.dumps(combined_users, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (folder / "raw_posts.json").write_text(
        json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (folder / "raw_rejects.json").write_text(
        json.dumps(rejects, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (folder / "search_queries.md").write_text(
        "# Search Queries\n\n" + "\n".join(f"- {query}" for query in queries) + "\n",
        encoding="utf-8",
    )
    (folder / "follow_suggestions.md").write_text(
        _scan_follow_suggestions_markdown(cluster, combined_users),
        encoding="utf-8",
    )
    (folder / "reply_candidates.md").write_text(
        _scan_reply_candidates_markdown(cluster, posts),
        encoding="utf-8",
    )
    (folder / "quote_candidates.md").write_text(
        _scan_quote_candidates_markdown(cluster, posts),
        encoding="utf-8",
    )
    (folder / "scan_report.md").write_text(
        _scan_report_markdown(cluster, queries, combined_users, posts, queue_path, rejects, provider_warnings),
        encoding="utf-8",
    )
    (folder / "rejects.md").write_text(
        _scan_rejects_markdown(rejects),
        encoding="utf-8",
    )
    if provider_warnings:
        (folder / "provider_warnings.md").write_text(
            "# X Provider Warnings\n\n" + "\n".join(f"- {item}" for item in provider_warnings) + "\n",
            encoding="utf-8",
        )
    return GraphScanResult(scan_id, folder, cluster, len(combined_users), len(posts), queue_path, provider_warnings)


def import_target_accounts(path: Path, cluster: str | None = None) -> int:
    ensure_workspace()
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".csv":
        return _import_target_accounts_csv(path, cluster)
    return _import_target_accounts_markdown(path, cluster)


def list_target_accounts(cluster: str | None = None) -> list[dict[str, Any]]:
    ensure_workspace()
    clauses: list[str] = []
    params: list[Any] = []
    if cluster:
        clauses.append("cluster = ?")
        params.append(normalize_cluster(cluster))
    where = " where " + " and ".join(clauses) if clauses else ""
    with connect_db() as conn:
        rows = conn.execute(
            f"""
            select id, handle, cluster, relevance_score, social_fit_score,
              noise_score, status, notes
            from target_accounts{where}
            order by cluster, relevance_score desc, social_fit_score desc, handle
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def rescore_target_accounts(cluster: str | None = None) -> int:
    ensure_workspace()
    clauses: list[str] = []
    params: list[Any] = []
    if cluster:
        clauses.append("cluster = ?")
        params.append(normalize_cluster(cluster))
    where = " where " + " and ".join(clauses) if clauses else ""
    with connect_db() as conn:
        rows = conn.execute(
            f"select id, cluster, notes, description from target_accounts{where}",
            params,
        ).fetchall()
        for row in rows:
            relevance, social_fit, noise = score_account_fields(
                row["cluster"], row["notes"] or "", row["description"] or ""
            )
            conn.execute(
                """
                update target_accounts
                set relevance_score = ?, social_fit_score = ?, noise_score = ?,
                  updated_at = ?
                where id = ?
                """,
                (relevance, social_fit, noise, iso_now(), row["id"]),
            )
    return len(rows)


def create_follow_seed_queue(cluster: str, limit: int = 30) -> Path:
    workspace = ensure_workspace()
    cluster = normalize_cluster(cluster)
    limit = max(1, min(100, limit))
    with connect_db() as conn:
        rows = conn.execute(
            """
            select id, handle, cluster, source, description, notes, relevance_score,
              social_fit_score, noise_score, status
            from target_accounts
            where cluster = ?
              and status not in ('blocked', 'skipped', 'rejected')
              and (
                (
                  (
                    coalesce(source, '') in ('manual', 'import', 'manual_csv', 'manual_markdown')
                    or coalesce(source, '') like 'import:%'
                  )
                  and relevance_score >= 0.45
                  and noise_score <= 0.45
                )
                or (
                  (
                    coalesce(source, '') not in ('manual', 'import', 'manual_csv', 'manual_markdown')
                    and coalesce(source, '') not like 'import:%'
                  )
                  and relevance_score >= 0.6
                  and noise_score <= 0.35
                )
              )
            order by relevance_score desc, social_fit_score desc, noise_score asc, handle
            limit ?
            """,
            (cluster, limit),
        ).fetchall()
        queued: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            queue_id = f"fq_{cluster}_{short_hash(row['handle'], 10)}"
            existing = conn.execute(
                "select status from follow_queue where id = ?",
                (queue_id,),
            ).fetchone()
            if existing and existing["status"] in {"followed_manually", "blocked"}:
                continue
            reason = _follow_queue_reason(dict(row), cluster)
            conn.execute(
                """
                insert or replace into follow_queue(
                  id, account_id, handle, cluster, reason, priority, status,
                  suggested_at, acted_at
                )
                values(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    queue_id,
                    row["id"],
                    row["handle"],
                    cluster,
                    reason,
                    index,
                    "queued",
                    iso_now(),
                    "",
                ),
            )
            queued.append({**dict(row), "queue_id": queue_id, "reason": reason, "priority": index})

    now = get_now()
    path = workspace.root / "graph" / "follow_queue" / f"{now:%Y%m%d-%H%M}-{cluster}-follow_queue.md"
    path.write_text(_follow_queue_markdown(cluster, queued), encoding="utf-8")
    return path


def create_digest(cluster: str, limit: int = 50, language: str | None = None) -> DigestResult:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    cluster = normalize_cluster(cluster)
    language = language or config.bootstrap_default_digest_language
    handles = [row["handle"] for row in list_target_accounts(cluster)]
    rows = _cached_source_posts(handles, limit)
    now = get_now()
    digest_id = f"digest_{now:%Y%m%d_%H%M}_{cluster}"
    folder = workspace.root / "graph" / "digests" / f"{now:%Y%m%d-%H%M}-{cluster}"
    folder.mkdir(parents=True, exist_ok=True)

    raw_items = [_source_row_to_digest_item(row, cluster) for row in rows]
    summary = _digest_summary_markdown(cluster, raw_items, language)
    opportunities = _standalone_ideas_markdown(cluster, raw_items)
    quote_candidates = _quote_candidates_markdown(cluster, raw_items)
    follow_suggestions = _follow_suggestions_markdown(cluster)

    (folder / "raw_items.json").write_text(
        json.dumps(raw_items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (folder / "digest.md").write_text(summary, encoding="utf-8")
    (folder / "quote_candidates.md").write_text(quote_candidates, encoding="utf-8")
    (folder / "standalone_ideas.md").write_text(opportunities, encoding="utf-8")
    (folder / "follow_suggestions.md").write_text(follow_suggestions, encoding="utf-8")

    with connect_db() as conn:
        conn.execute(
            """
            insert or replace into digests(
              id, created_at, cluster, source, language, raw_count, summary,
              opportunities, folder_path
            )
            values(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                digest_id,
                iso_now(),
                cluster,
                "cached_x_sources",
                language,
                len(raw_items),
                summary,
                opportunities,
                str(folder),
            ),
        )
        conn.execute("delete from digest_items where digest_id = ?", (digest_id,))
        for item in raw_items:
            conn.execute(
                """
                insert into digest_items(
                  id, digest_id, source_account_id, handle, post_id, url,
                  created_at, text, public_metrics, cluster, relevance_score,
                  actionability_score, suggested_action
                )
                values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    digest_id,
                    item["source_account_id"],
                    item["handle"],
                    item["post_id"],
                    item["url"],
                    item["created_at"],
                    item["text"],
                    item["public_metrics"],
                    cluster,
                    item["relevance_score"],
                    item["actionability_score"],
                    item["suggested_action"],
                ),
            )
            upsert_fts(conn, "digest_items_fts", (item["id"], item["text"], item["handle"], cluster))
    return DigestResult(digest_id, folder, len(raw_items))


def latest_digest_folder(target: str = "latest") -> Path | None:
    ensure_workspace()
    if target != "latest":
        path = Path(target).expanduser()
        return path if path.exists() else None
    with connect_db() as conn:
        row = conn.execute(
            "select folder_path from digests order by created_at desc, rowid desc limit 1"
        ).fetchone()
    return Path(row["folder_path"]) if row else None


def quote_candidates_text(target: str = "latest") -> tuple[Path | None, str]:
    folder = latest_digest_folder(target)
    if not folder:
        return None, "No digest found. Run: tw x-digest --cluster quant --ru"
    path = folder / "quote_candidates.md"
    if not path.exists():
        return path, "No quote candidates file found."
    return path, path.read_text(encoding="utf-8", errors="replace")


def create_draft_from_digest(
    target: str,
    draft_type: str,
    cwd: Path | None = None,
    no_llm: bool = False,
):
    folder = latest_digest_folder(target)
    if not folder:
        raise ValueError("No digest found. Run x-digest first.")
    ideas_path = folder / "standalone_ideas.md"
    digest_path = folder / "digest.md"
    text = (
        "Create a low-social standalone draft from this digest. "
        "Do not fake expertise, do not write engagement bait, and keep it draft-only.\n\n"
        f"{digest_path.read_text(encoding='utf-8', errors='replace')}\n\n"
        f"{ideas_path.read_text(encoding='utf-8', errors='replace') if ideas_path.exists() else ''}"
    )
    from .drafting import create_draft

    return create_draft(text, draft_type, cwd=cwd, no_llm=no_llm)


def graph_review_markdown() -> str:
    ensure_workspace()
    with connect_db() as conn:
        target_rows = conn.execute(
            "select cluster, count(*) as count from target_accounts group by cluster order by cluster"
        ).fetchall()
        queue_rows = conn.execute(
            "select cluster, status, count(*) as count from follow_queue group by cluster, status order by cluster, status"
        ).fetchall()
        digest_rows = conn.execute(
            "select cluster, count(*) as count from digests group by cluster order by cluster"
        ).fetchall()
    lines = ["# Graph Review", ""]
    lines.append("## Target Accounts")
    lines.extend(_count_lines(target_rows))
    lines.append("")
    lines.append("## Follow Queue")
    lines.extend(_status_count_lines(queue_rows))
    lines.append("")
    lines.append("## Digests")
    lines.extend(_count_lines(digest_rows))
    lines.append("")
    lines.append("## Verdict")
    total_targets = sum(int(row["count"]) for row in target_rows)
    if total_targets < 50:
        lines.append("- account still looks early: add more target accounts before over-posting")
    else:
        lines.append("- target graph has enough raw material for daily digest-based strategy")
    lines.append("- keep manual actions human-only; no auto-follow or auto-like")
    return "\n".join(lines)


def _cluster_search_queries(cluster: str) -> list[str]:
    query_map = {
        "quant": [
            '"market microstructure" -is:retweet lang:en',
            '"backtesting realism" -is:retweet lang:en',
            '"execution assumptions" "backtest" -is:retweet lang:en',
            '"queue position" OR "partial fills" -is:retweet lang:en',
            '"order book" latency -is:retweet lang:en',
        ],
        "systems": [
            '"C++" "low latency"',
            '"performance debugging" systems',
            '"exchange connectivity" OR "kernel bypass"',
        ],
        "ml_infra": [
            '"recommender systems" "feature store"',
            '"model serving" "data pipelines"',
            '"ML systems" infrastructure',
        ],
        "ai_agents": [
            'Codex agents "developer tooling"',
            '"MCP" "local agents"',
            '"workflow automation" "AI coding"',
        ],
        "builders": [
            '"build log" "technical project"',
            '"public notebook" engineering',
            '"CS student" project',
        ],
    }
    return query_map.get(cluster, [cluster])


def _filter_scan_users(
    cluster: str,
    users: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for user in users:
        decision = _quality_decision_for_user(cluster, user)
        enriched = {
            **user,
            "quality_relevance": decision.relevance,
            "quality_noise": decision.noise,
            "quality_reasons": decision.reasons,
        }
        if decision.accepted:
            accepted.append(enriched)
        else:
            rejected.append(
                {
                    "kind": "account",
                    "handle": normalize_handle(str(user.get("username") or user.get("handle") or "")),
                    "text": str(user.get("description") or user.get("name") or ""),
                    "relevance": decision.relevance,
                    "noise": decision.noise,
                    "reasons": decision.reasons,
                }
            )
    return accepted, rejected


def _filter_scan_posts(
    cluster: str,
    posts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for post in posts:
        decision = _quality_decision_for_post(cluster, post)
        enriched = {
            **post,
            "quality_relevance": decision.relevance,
            "quality_noise": decision.noise,
            "quality_reasons": decision.reasons,
        }
        if decision.accepted:
            accepted.append(enriched)
        else:
            rejected.append(
                {
                    "kind": "post",
                    "handle": normalize_handle(str(post.get("author_username") or post.get("username") or "")),
                    "text": str(post.get("text") or ""),
                    "relevance": decision.relevance,
                    "noise": decision.noise,
                    "reasons": decision.reasons,
                }
            )
    accepted.sort(key=lambda post: (-float(post.get("quality_relevance") or 0.0), float(post.get("quality_noise") or 1.0)))
    return accepted, rejected


def _quality_decision_for_user(cluster: str, user: dict[str, Any]) -> QualityDecision:
    handle = normalize_handle(str(user.get("username") or user.get("handle") or ""))
    text = " ".join(
        [
            handle,
            str(user.get("name") or ""),
            str(user.get("description") or ""),
        ]
    )
    relevance, noise, reasons = _score_scan_text(cluster, text)
    if not str(user.get("description") or "").strip() and not _has_handle_signal(cluster, handle):
        reasons.append("empty_or_uninformative_bio")
        relevance -= 0.15
    accepted = relevance >= 0.45 and noise <= 0.45
    if not accepted:
        if relevance < 0.45:
            reasons.append("low_relevance")
        if noise > 0.45:
            reasons.append("noise")
    return QualityDecision(accepted, _clamp(relevance), _clamp(noise), sorted(set(reasons)))


def _quality_decision_for_post(cluster: str, post: dict[str, Any]) -> QualityDecision:
    text = str(post.get("text") or "")
    author_text = " ".join(
        [
            str(post.get("author_username") or ""),
            str(post.get("author_name") or ""),
            str(post.get("author_description") or ""),
        ]
    )
    relevance, noise, reasons = _score_scan_text(cluster, f"{text} {author_text}")
    stripped = text.strip()
    if stripped.lower().startswith("rt @"):
        reasons.append("retweet")
        noise += 0.4
        relevance -= 0.2
    if _looks_url_only(stripped):
        reasons.append("url_only")
        noise += 0.25
        relevance -= 0.15
    if len(stripped) < 45:
        reasons.append("too_short")
        relevance -= 0.1
    accepted = relevance >= 0.5 and noise <= 0.45
    if not accepted:
        if relevance < 0.5:
            reasons.append("low_relevance")
        if noise > 0.45:
            reasons.append("noise")
    return QualityDecision(accepted, _clamp(relevance), _clamp(noise), sorted(set(reasons)))


def _tag_source(items: list[dict], source: str, query: str) -> list[dict[str, Any]]:
    tagged = []
    for item in items:
        tagged.append({**dict(item), "scan_source": source, "scan_query": query})
    return tagged


def _dedupe_users(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_handle: dict[str, dict[str, Any]] = {}
    for user in users:
        handle = normalize_handle(str(user.get("username") or user.get("handle") or ""))
        if not handle:
            continue
        current = by_handle.get(handle, {})
        by_handle[handle] = {**current, **user, "username": handle}
    return sorted(by_handle.values(), key=_user_sort_key)[:100]


def _dedupe_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for post in posts:
        post_id = str(post.get("id") or post.get("post_id") or short_hash(str(post), 12))
        by_id[post_id] = {**by_id.get(post_id, {}), **post, "id": post_id}
    return list(by_id.values())[:100]


def _user_sort_key(user: dict[str, Any]) -> tuple[float, int, str]:
    metrics = user.get("public_metrics") or {}
    followers = int(metrics.get("followers_count") or user.get("followers_count") or 0)
    description = str(user.get("description") or "")
    risky = any(term in description.lower() for term in ["airdrop", "100x", "signal", "pnl"])
    return (1.0 if risky else 0.0, -followers, normalize_handle(str(user.get("username") or "")))


def _store_scan_user(user: dict[str, Any], cluster: str) -> None:
    metrics = user.get("public_metrics") or {}
    note = f"{user.get('scan_source', 'x_scan')}: {user.get('scan_query', '')}".strip()
    add_target_account(
        str(user.get("username") or user.get("handle") or ""),
        cluster,
        note=note,
        source=str(user.get("scan_source") or "x_scan"),
        display_name=str(user.get("name") or user.get("display_name") or ""),
        description=str(user.get("description") or ""),
        user_id=str(user.get("id") or user.get("user_id") or ""),
        followers_count=_maybe_int(metrics.get("followers_count") or user.get("followers_count")),
        following_count=_maybe_int(metrics.get("following_count") or user.get("following_count")),
        verified=bool(user.get("verified")) if user.get("verified") is not None else None,
    )


def _clear_scan_derived_targets(cluster: str) -> None:
    scan_sources = ("user_search", "seed_following", "recent_post_author", "x_scan")
    placeholders = ", ".join("?" for _ in scan_sources)
    with connect_db() as conn:
        rows = conn.execute(
            f"""
            select id
            from target_accounts
            where cluster = ?
              and coalesce(source, '') in ({placeholders})
            """,
            (cluster, *scan_sources),
        ).fetchall()
        account_ids = [row["id"] for row in rows]
        if not account_ids:
            return
        id_placeholders = ", ".join("?" for _ in account_ids)
        conn.execute(
            f"""
            delete from follow_queue
            where status = 'queued'
              and account_id in ({id_placeholders})
            """,
            account_ids,
        )
        conn.execute(
            f"delete from target_accounts where id in ({id_placeholders})",
            account_ids,
        )


def _store_scan_post(post: dict[str, Any], cluster: str) -> None:
    handle = normalize_handle(str(post.get("author_username") or post.get("username") or ""))
    text = str(post.get("text") or "").strip()
    post_id = str(post.get("id") or post.get("post_id") or short_hash(text, 12))
    if not text:
        return
    source_id = f"xscan_{handle or 'unknown'}_{post_id}"
    created_at = str(post.get("created_at") or iso_now())
    url = str(post.get("url") or (f"https://x.com/{handle}/status/{post_id}" if handle else ""))
    with connect_db() as conn:
        conn.execute(
            """
            insert or replace into sources(id, created_at, type, url, title, author, raw_text, summary, tags)
            values(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source_id, created_at, "x_post", url, f"X post {post_id}", handle, text, text, f"peer,{cluster},graph_scan"),
        )
        upsert_fts(conn, "sources_fts", (source_id, f"X post {post_id}", text, text, f"peer {cluster} graph_scan"))


def _user_from_post(post: dict[str, Any]) -> dict[str, Any] | None:
    handle = normalize_handle(str(post.get("author_username") or post.get("username") or ""))
    if not handle:
        return None
    return {
        "id": str(post.get("author_id") or ""),
        "username": handle,
        "name": str(post.get("author_name") or ""),
        "description": str(post.get("author_description") or ""),
        "scan_source": "recent_post_author",
        "scan_query": str(post.get("scan_query") or ""),
    }


def _scan_follow_suggestions_markdown(cluster: str, users: list[dict[str, Any]]) -> str:
    lines = [f"# Follow Suggestions: {cluster}", "", "Manual-only. Do not automate following.", ""]
    if not users:
        lines.append("- no live user candidates found")
        return "\n".join(lines) + "\n"
    for user in users[:30]:
        handle = display_handle(str(user.get("username") or ""))
        description = _compact(str(user.get("description") or ""), 180)
        source = user.get("scan_source", "x_scan")
        lines.append(f"- {handle} — {description or source}")
        lines.append(f"  - source: {source}")
        lines.append(f"  - link: https://x.com/{normalize_handle(handle)}")
    return "\n".join(lines) + "\n"


def _scan_reply_candidates_markdown(cluster: str, posts: list[dict[str, Any]]) -> str:
    lines = [f"# Optional Reply Candidates: {cluster}", "", "Manual-only. Skip by default unless the reply is concrete.", ""]
    if not posts:
        lines.append("- no reply candidates found")
        return "\n".join(lines) + "\n"
    for post in posts[:10]:
        lines.append(f"- {display_handle(str(post.get('author_username') or ''))}: {_compact(str(post.get('text') or ''), 240)}")
        lines.append("  - possible reply: add one implementation caveat or ask one bounded technical question")
        if post.get("url"):
            lines.append(f"  - source: {post['url']}")
    return "\n".join(lines) + "\n"


def _scan_quote_candidates_markdown(cluster: str, posts: list[dict[str, Any]]) -> str:
    lines = [f"# Optional Quote Candidates: {cluster}", "", "Manual-only. Quote at most one, and only with a concrete observation.", ""]
    if not posts:
        lines.append("- no quote candidates found")
        return "\n".join(lines) + "\n"
    for post in posts[:10]:
        lines.append(f"## {display_handle(str(post.get('author_username') or ''))}")
        lines.append(f"- source: {post.get('url') or ''}")
        lines.append(f"- text: {_compact(str(post.get('text') or ''), 280)}")
        lines.append("- quote angle: connect to your own project/backtest/systems lesson without fake expertise")
        lines.append("")
    return "\n".join(lines)


def _scan_report_markdown(
    cluster: str,
    queries: list[str],
    users: list[dict[str, Any]],
    posts: list[dict[str, Any]],
    queue_path: Path | None,
    rejects: list[dict[str, Any]],
    warnings: list[str] | None = None,
) -> str:
    lines = [
        f"# Graph Scan: {cluster}",
        "",
        "Mode: read-only / manual-only",
        "",
        "## Queries",
        *[f"- {query}" for query in queries],
        "",
        "## Account Candidates",
    ]
    if users:
        for user in users[:20]:
            lines.append(f"- {display_handle(str(user.get('username') or ''))} — {_compact(str(user.get('description') or ''), 180)}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Post Candidates")
    if posts:
        for post in posts[:20]:
            lines.append(f"- {display_handle(str(post.get('author_username') or ''))}: {_compact(str(post.get('text') or ''), 240)}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Manual Queue")
    lines.append(f"- {queue_path}" if queue_path else "- no queue created")
    lines.append("")
    lines.append("## Quality Filter")
    lines.append(f"- accepted accounts: {len(users)}")
    lines.append(f"- accepted posts: {len(posts)}")
    lines.append(f"- rejected candidates: {len(rejects)}")
    lines.append("- see rejects.md for reasons")
    if warnings:
        lines.append("")
        lines.append("## Provider Warnings")
        lines.extend(f"- {item}" for item in warnings[:12])
    lines.append("")
    lines.append("Safety: this scan creates files and local queue rows only. It does not follow, like, reply, quote, repost, or publish.")
    return "\n".join(lines) + "\n"


def _scan_rejects_markdown(rejects: list[dict[str, Any]]) -> str:
    lines = ["# Rejected Scan Candidates", "", "These were excluded before follow/reply/quote suggestions.", ""]
    if not rejects:
        lines.append("- none")
        return "\n".join(lines) + "\n"
    for item in rejects[:120]:
        handle = display_handle(str(item.get("handle") or ""))
        reasons = ", ".join(item.get("reasons") or [])
        text = _compact(str(item.get("text") or ""), 220)
        lines.append(f"- {item.get('kind')}: {handle} | relevance={item.get('relevance')} noise={item.get('noise')} | {reasons}")
        if text:
            lines.append(f"  - {text}")
    return "\n".join(lines) + "\n"


def weekly_review_markdown() -> str:
    ensure_workspace()
    with connect_db() as conn:
        actions = conn.execute(
            "select status, count(*) as count from bootstrap_actions group by status order by status"
        ).fetchall()
        digests = conn.execute("select count(*) as count from digests").fetchone()["count"]
        drafts = conn.execute("select count(*) as count from drafts").fetchone()["count"]
        followed = conn.execute(
            "select count(*) as count from follow_queue where status = 'followed_manually'"
        ).fetchone()["count"]
    return f"""# Weekly Bootstrap Review

## Execution
{chr(10).join(f"- {row['status']}: {row['count']}" for row in actions) if actions else "- no logged actions yet"}

## Graph / Content
- followed manually: {followed}
- digests created: {digests}
- drafts created: {drafts}

## Next Adjustment
- lower follow budget if the queue quality is weak
- keep quote notes optional
- do not add mandatory replies unless they are unusually relevant
"""


def write_distribution_bootstrap_artifact(folder: Path, config: Config, draft_type: str) -> Path:
    path = folder / "17_distribution_bootstrap.md"
    cluster = _infer_cluster_from_text((folder / "06_final_candidate.md").read_text(encoding="utf-8", errors="replace"))
    text = f"""# Distribution Bootstrap

## Account stage
{config.bootstrap_account_stage}

## Interaction mode
{config.bootstrap_interaction_mode}

## Recommended distribution
{_recommended_distribution(draft_type)}

## Why this works without heavy social interaction
This draft is meant to act as a clear topic signal for a cold account. It should be understandable as a standalone note and should not require a reply chain, coordinated engagement, or existing followers to make sense.

## Does this require existing followers?
no

## Graph target
cluster: {cluster}
target accounts: choose from the manual follow queue, not automated actions
possible audience: people already reading {cluster} / adjacent technical work

## Profile conversion check
bio: should name the working notebook angle clearly
pinned: should explain projects and current learning/build direction
seed posts: should make the account look alive and specific
topic consistency: avoid jumping into unrelated viral topics

## Manual action
- post as standalone
- save for later
- use as quote note only if there is a concrete source post
- skip
"""
    path.write_text(text, encoding="utf-8")
    return path


def normalize_cluster(cluster: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", cluster.strip().lower()).strip("_")
    return clean or "builders"


def score_account_fields(cluster: str, note: str, description: str) -> tuple[float, float, float]:
    relevance, noise, _reasons = _score_scan_text(cluster, f"{_scoreable_note(note)} {description}")
    social_fit = 0.25 + relevance * 0.55 - noise * 0.25
    return (_clamp(relevance), _clamp(social_fit), _clamp(noise))


def _scoreable_note(note: str) -> str:
    lowered = note.lower().strip()
    scan_prefixes = (
        "recent_post_author:",
        "recent_post_author;",
        "user_search:",
        "user_search;",
        "seed_following:",
        "seed_following;",
        "x_scan:",
        "x_scan;",
    )
    if lowered.startswith(scan_prefixes):
        return ""
    return note


def _score_scan_text(cluster: str, text: str) -> tuple[float, float, list[str]]:
    lowered = " " + re.sub(r"[^a-z0-9+#]+", " ", text.lower()) + " "
    relevance = 0.05
    noise = 0.08
    reasons: list[str] = []
    for phrase, weight in _cluster_positive_terms(cluster):
        if phrase in lowered:
            relevance += weight
            reasons.append(f"topic:{phrase.strip()}")
    for phrase, weight in _cluster_adjacent_terms(cluster):
        if phrase in lowered:
            relevance += weight
            reasons.append(f"adjacent:{phrase.strip()}")
    for phrase, weight in _noise_terms():
        if phrase in lowered:
            noise += weight
            relevance -= weight * 0.45
            reasons.append(f"noise:{phrase.strip()}")
    if _contains_mostly_non_latin(text):
        noise += 0.18
        reasons.append("language_friction")
    return (_clamp(relevance), _clamp(noise), reasons)


def _cluster_positive_terms(cluster: str) -> list[tuple[str, float]]:
    terms = {
        "quant": [
            (" market microstructure ", 0.42),
            (" microstructure ", 0.24),
            (" backtesting realism ", 0.32),
            (" backtest ", 0.2),
            (" backtests ", 0.2),
            (" execution assumptions ", 0.3),
            (" execution algorithms ", 0.34),
            (" execution systems ", 0.24),
            (" execution model ", 0.22),
            (" queue position ", 0.28),
            (" partial fills ", 0.26),
            (" order book ", 0.22),
            (" slippage ", 0.18),
            (" systematic trading ", 0.18),
            (" quant dev ", 0.22),
            (" low latency ", 0.24),
            (" exchange connectivity ", 0.26),
            (" market structure ", 0.26),
            (" realistic backtesting ", 0.32),
            (" hft data systems ", 0.28),
        ],
        "systems": [
            (" c++ ", 0.24),
            (" low latency ", 0.32),
            (" performance debugging ", 0.3),
            (" performance ", 0.2),
            (" systems programming ", 0.28),
            (" systems engineering ", 0.24),
            (" real time systems ", 0.26),
            (" engines programming ", 0.22),
            (" c++ debugging ", 0.26),
            (" cache ", 0.2),
            (" data cache ", 0.22),
            (" instruction cache ", 0.22),
            (" kernel ", 0.18),
            (" kernel bypass ", 0.34),
        ],
        "ml_infra": [
            (" recommender systems ", 0.32),
            (" feature store ", 0.28),
            (" model serving ", 0.28),
            (" data pipeline ", 0.22),
        ],
        "ai_agents": [
            (" agents ", 0.22),
            (" codex ", 0.28),
            (" developer tooling ", 0.28),
            (" developer tools ", 0.26),
            (" agentic developer experience ", 0.34),
            (" claude code ", 0.28),
            (" cli agents ", 0.28),
            (" local agents ", 0.28),
            (" mcp ", 0.24),
            (" ai readable docs ", 0.22),
        ],
        "builders": [
            (" built ", 0.2),
            (" building ", 0.18),
            (" build log ", 0.26),
            (" build logs ", 0.26),
            (" public notebook ", 0.28),
            (" technical project ", 0.24),
            (" technical builder ", 0.26),
            (" matching engine ", 0.28),
            (" learning ", 0.16),
        ],
    }
    return terms.get(cluster, [(f" {cluster} ", 0.22)])


def _cluster_adjacent_terms(cluster: str) -> list[tuple[str, float]]:
    terms = {
        "quant": [
            (" exchange ", 0.12),
            (" latency ", 0.12),
            (" hft ", 0.14),
            (" fills ", 0.14),
            (" market making ", 0.16),
            (" trading systems ", 0.16),
        ],
        "systems": [(" infrastructure ", 0.12), (" exchange ", 0.1), (" latency ", 0.12)],
        "ml_infra": [(" ml ", 0.1), (" infrastructure ", 0.12), (" serving ", 0.12)],
        "ai_agents": [(" automation ", 0.1), (" workflows ", 0.1)],
        "builders": [(" project ", 0.1), (" student ", 0.1), (" tool ", 0.1)],
    }
    return terms.get(cluster, [])


def _noise_terms() -> list[tuple[str, float]]:
    return [
        (" 100x ", 0.45),
        (" airdrop ", 0.4),
        (" alpha signal ", 0.4),
        (" crypto signal ", 0.42),
        (" trading signal ", 0.42),
        (" trading signals ", 0.42),
        (" free alpha ", 0.34),
        (" pnl ", 0.34),
        (" moon ", 0.3),
        (" giveaway ", 0.32),
        (" guru ", 0.26),
        (" crypto ", 0.55),
        (" defi ", 0.55),
        (" web3 ", 0.55),
        (" blockchain ", 0.5),
        (" onchain ", 0.5),
        (" tokenized ", 0.5),
        (" token ", 0.46),
        (" rwa ", 0.46),
        (" eth ", 0.46),
        (" xbt ", 0.46),
        (" btc ", 0.46),
        (" bitcoin ", 0.46),
        (" liquidity ", 0.18),
        (" dyor ", 0.3),
        (" nfa ", 0.28),
        (" not financial advice ", 0.5),
        (" financial advice ", 0.34),
        (" copy trading ", 0.34),
        (" whales ", 0.28),
        (" ambassador ", 0.5),
        (" community lead ", 0.5),
        (" content creator ", 0.38),
        (" content writer ", 0.38),
        (" dm for collab ", 0.42),
        (" marketing ", 0.38),
        (" marketer ", 0.38),
        (" creator collab ", 0.42),
        (" swing trader ", 0.36),
        (" futures trader ", 0.42),
        (" options trader ", 0.42),
        (" trader ", 0.24),
        (" market strategist ", 0.34),
        (" technical analysis ", 0.34),
        (" chart analysis ", 0.34),
        (" price action ", 0.3),
        (" elliott wave ", 0.38),
        (" gold futures ", 0.42),
        (" forex ", 0.4),
        (" polymarket ", 0.38),
        (" prediction market ", 0.32),
        (" betting market ", 0.32),
        (" options flow ", 0.34),
        (" stock market ", 0.28),
        (" stocks ", 0.26),
        (" trump ", 0.22),
        (" political commentator ", 0.26),
        (" daily wire ", 0.28),
        (" betting ", 0.22),
        (" meme ", 0.18),
    ]


def _has_handle_signal(cluster: str, handle: str) -> bool:
    lowered = handle.lower()
    handle_terms = {
        "quant": ["quant", "micro", "hft", "exec", "market", "trading"],
        "systems": ["cpp", "systems", "latency", "perf", "infra"],
        "ml_infra": ["ml", "recsys", "infra", "data"],
        "ai_agents": ["agent", "codex", "mcp", "devtool"],
        "builders": ["build", "notebook", "project"],
    }
    return any(term in lowered for term in handle_terms.get(cluster, [cluster]))


def _looks_url_only(text: str) -> bool:
    compact = text.strip()
    without_urls = re.sub(r"https?://\\S+|t\\.co/\\S+", "", compact).strip()
    return bool(compact) and len(without_urls) < 20 and ("http" in compact or "t.co/" in compact)


def _contains_mostly_non_latin(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    if len(letters) < 20:
        return False
    latin = [char for char in letters if ("a" <= char.lower() <= "z")]
    return len(latin) / max(1, len(letters)) < 0.45


def _bounded_days(days: int) -> int:
    return max(1, min(60, int(days)))


def _account_state_markdown() -> str:
    with connect_db() as conn:
        targets = conn.execute("select count(*) from target_accounts").fetchone()[0]
        queued = conn.execute("select count(*) from follow_queue where status = 'queued'").fetchone()[0]
        drafts = conn.execute("select count(*) from drafts").fetchone()[0]
        posts = conn.execute("select count(*) from posts").fetchone()[0]
    return f"""# Account State

- target accounts: {targets}
- queued manual follows: {queued}
- local drafts: {drafts}
- imported/recorded posts: {posts}

Interpretation:
- cold accounts need graph clarity before high posting volume
- queued follows are suggestions only
- publishing and following remain human actions
"""


def _graph_strategy_markdown(config: Config) -> str:
    clusters = ", ".join(config.bootstrap_default_clusters)
    return f"""# Graph Strategy

Mode: {config.bootstrap_interaction_mode}
Stage: {config.bootstrap_account_stage}
Manual budget: {config.bootstrap_manual_social_budget_minutes} minutes/day
Daily follow budget: {config.bootstrap_daily_follow_budget}
Clusters: {clusters}

Rules:
- build a relevant following graph before chasing reach
- use digests to avoid raw feed reading
- keep quote notes optional
- never automate follow, like, reply, quote, repost, or posting
- no mandatory replies in low_social mode
"""


def _personal_strategy_markdown(config: Config) -> str:
    workspace = ensure_workspace()
    profile = read_profile(workspace.root)
    with connect_db() as conn:
        drafts = conn.execute(
            """
            select created_at, status, type, title, final_text
            from drafts
            order by created_at desc, rowid desc
            limit 8
            """
        ).fetchall()
        posts = conn.execute(
            """
            select created_at, text
            from posts
            order by created_at desc, rowid desc
            limit 8
            """
        ).fetchall()
    profile_bits = [
        ("persona", profile.get("persona", "")),
        ("topics", profile.get("topics", "")),
        ("style", profile.get("style", "")),
        ("bootstrap agent", profile.get("graph_bootstrap_agent", "")),
    ]
    lines = [
        "# Personal Bootstrap Strategy",
        "",
        f"Stage: {config.bootstrap_account_stage}",
        f"Mode: {config.bootstrap_interaction_mode}",
        "",
        "## What this account is about",
    ]
    for name, text in profile_bits:
        snippet = _compact(text, 700)
        if snippet:
            lines.append(f"### {name}")
            lines.append(snippet)
            lines.append("")
    lines.append("## Recent Draft Signals")
    if drafts:
        for row in drafts:
            text = _compact(row["final_text"] or row["title"] or "", 260)
            lines.append(f"- {row['status']} / {row['type']}: {text}")
    else:
        lines.append("- no drafts yet")
    lines.append("")
    lines.append("## Recent Own Post Signals")
    if posts:
        for row in posts:
            lines.append(f"- {row['created_at']}: {_compact(row['text'], 260)}")
    else:
        lines.append("- no synced own posts yet")
    lines.append("")
    lines.append("## Strategy For This User")
    lines.append("- prioritize quant/systems/ML infra/agent-builder graph, not broad creator advice")
    lines.append("- use Russian digests internally if they reduce feed-reading friction")
    lines.append("- produce standalone/build notes first; replies and quotes are optional")
    lines.append("- use old drafts as topic memory, not as proof of expertise")
    lines.append("- keep all X actions manual")
    return "\n".join(lines) + "\n"


def _daily_operator_packet_markdown(
    day: int,
    days: int,
    cluster: str,
    target_rows: list[dict[str, Any]],
    items: list[dict[str, Any]],
    config: Config,
    scan_result: GraphScanResult | None,
) -> str:
    lines = [
        f"# Daily Operator Packet: Day {day}/{days}",
        "",
        f"Cluster focus: {cluster}",
        f"Mode: {config.bootstrap_interaction_mode}",
        "No mandatory replies. Manual-only execution.",
        "",
    ]
    if scan_result:
        lines.extend(
            [
                "## Live read-only X scan",
                f"- scan folder: {scan_result.folder}",
                f"- accounts found: {scan_result.account_count}",
                f"- posts found: {scan_result.post_count}",
                f"- manual queue: {scan_result.queue_path or 'not created'}",
                "",
            ]
        )
    lines.extend(
        [
        "## Read-only Twitter Refresh",
        "- uses cached/read-only X sources available in local memory",
        "- if live X API is configured, import sources with `tw x-read @handle --limit 100` before this packet",
        "- no write endpoints are called",
        "",
        "## Manual follows to consider",
        ]
    )
    if target_rows:
        for row in target_rows[: config.bootstrap_daily_follow_budget]:
            lines.append(f"- {display_handle(row['handle'])} — {row['notes'] or cluster}")
    else:
        lines.append("- no target accounts queued for this cluster yet")
    lines.append("")
    lines.append("## Optional reply candidates")
    if items:
        for item in items[:3]:
            lines.append(f"- {display_handle(item['handle'])}: {item['text']}")
            lines.append("  - only reply if you can add one concrete implementation caveat")
    else:
        lines.append("- none; skip replies today")
    lines.append("")
    lines.append("## Optional quote candidates")
    if items:
        for item in items[:3]:
            lines.append(f"- {item['url'] or display_handle(item['handle'])}")
            lines.append(f"  - source: {item['text']}")
            lines.append("  - quote angle: one specific observation, no generic agreement")
    else:
        lines.append("- none; skip quotes today")
    lines.append("")
    lines.append("## Standalone note direction")
    if items:
        lines.append(f"- Turn this into a standalone/build note: {items[0]['text']}")
    else:
        lines.append("- write one seed/build note from current project context")
    lines.append("")
    lines.append("## What to skip")
    lines.append("- reading the timeline manually")
    lines.append("- replying for the sake of replying")
    lines.append("- quote-posting without a concrete observation")
    lines.append("- any automated follow/like/reply/post behavior")
    return "\n".join(lines)


def _actions_for_day(day: int, days: int, config: Config) -> list[dict[str, str]]:
    clusters = config.bootstrap_default_clusters or DEFAULT_BOOTSTRAP_CLUSTERS
    cluster = _cluster_for_day(day, config)
    follow_budget = config.bootstrap_daily_follow_budget if day <= 3 else min(12, config.bootstrap_daily_follow_budget)
    if day >= 8:
        follow_budget = min(10, follow_budget)
    actions = [
        _action(day, "manual_follow", "Manual follow", f"Consider up to {follow_budget} accounts from graph/follow_queue. Human-only; do not automate following."),
        _action(day, "digest", "Digest", f"Run: tw x-digest --cluster {cluster} --limit 50 --ru. Use cached/read-only sources only."),
        _action(day, "draft_or_seed", "Seed/build note", "Create or choose one standalone/build note. No existing audience required."),
    ]
    if day in {4, 11}:
        actions.append(_action(day, "graph_review", "Graph review", "Run: tw graph-review and prune future suggestions, not mass unfollow."))
    if day in {5, 10, 13}:
        actions.append(_action(day, "optional_quote", "Optional quote candidate", "Run: tw quote-candidates latest; choose 0-1 only if you have a concrete observation."))
    if day in {7, 14} or day == days:
        actions.append(_action(day, "weekly_review", "Weekly review", "Run: tw weekly-review and adjust the next queue."))
    return actions


def _cluster_for_day(day: int, config: Config) -> str:
    clusters = config.bootstrap_default_clusters or DEFAULT_BOOTSTRAP_CLUSTERS
    return normalize_cluster(clusters[(day - 1) % len(clusters)])


def _action(day: int, action_type: str, title: str, details: str) -> dict[str, str]:
    return {
        "id": f"ba_day{day:02d}_{action_type}",
        "action_type": action_type,
        "title": title,
        "details": details,
    }


def _scoped_action(plan_id: str, action: dict[str, str]) -> dict[str, str]:
    return {**action, "id": f"{plan_id}_{action['id']}"}


def _plan_markdown(
    plan_id: str,
    days: int,
    config: Config,
    actions_by_day: dict[int, list[dict[str, str]]],
) -> str:
    lines = [
        f"# Graph Bootstrap Plan: {plan_id}",
        "",
        f"- days: {days}",
        f"- stage: {config.bootstrap_account_stage}",
        f"- mode: {config.bootstrap_interaction_mode}",
        f"- manual social budget: {config.bootstrap_manual_social_budget_minutes} minutes/day",
        f"- daily follow budget: {config.bootstrap_daily_follow_budget}",
        "",
        "Success is a clearer graph, not likes.",
        "",
        "Hard constraints:",
        "- manual follows only",
        "- no auto-like",
        "- no auto-reply",
        "- no auto-post",
        "- no mandatory replies in low_social mode",
        "",
        "## Daily Outline",
    ]
    for day, actions in actions_by_day.items():
        lines.append(f"### Day {day}")
        lines.extend(f"- {action['title']}: {action['details']}" for action in actions)
        lines.append("")
    return "\n".join(lines)


def _daily_markdown(
    day: int,
    days: int,
    actions: list[dict[str, str]],
    config: Config,
) -> str:
    lines = [
        f"# Day {day}/{days}",
        "",
        f"Mode: {config.bootstrap_interaction_mode}",
        "No mandatory replies. No manual timeline reading required.",
        "",
    ]
    for action in actions:
        lines.append(f"## {action['title']}")
        lines.append(f"- id: {action['id']}")
        lines.append(f"- type: {action['action_type']}")
        lines.append(f"- details: {action['details']}")
        lines.append("")
    lines.append("Manual execution only. Queue means suggestion, not action.")
    return "\n".join(lines)


def _latest_active_plan():
    ensure_workspace()
    with connect_db() as conn:
        return conn.execute(
            """
            select id, created_at, days, stage, interaction_mode, folder_path, status
            from bootstrap_plans
            where status = 'active'
            order by created_at desc, rowid desc
            limit 1
            """
        ).fetchone()


def _current_plan_day(plan) -> int:
    try:
        created = datetime.fromisoformat(str(plan["created_at"]))
        delta = (get_now().date() - created.date()).days
    except Exception:
        delta = 0
    return max(1, min(int(plan["days"]), delta + 1))


def _import_target_accounts_csv(path: Path, cluster: str | None) -> int:
    count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            handle = row.get("handle") or row.get("username") or ""
            row_cluster = row.get("cluster") or cluster or "builders"
            note = row.get("note") or row.get("reason") or ""
            if handle.strip():
                add_target_account(handle, row_cluster, note, source=f"import:{path.name}")
                count += 1
    return count


def _import_target_accounts_markdown(path: Path, cluster: str | None) -> int:
    current_cluster = normalize_cluster(cluster or "builders")
    count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        heading = re.match(r"^#+\s+(.+)$", line.strip())
        if heading:
            current_cluster = normalize_cluster(heading.group(1))
            continue
        match = re.search(r"@([A-Za-z0-9_]{1,15})(?:\s+[--]\s+|\s+—\s+)?(.*)", line)
        if match:
            add_target_account(match.group(1), current_cluster, match.group(2).strip(), source=f"import:{path.name}")
            count += 1
    return count


def _follow_queue_markdown(cluster: str, queued: list[dict[str, Any]]) -> str:
    lines = [
        f"# Manual follow queue: {cluster}",
        "",
        "Human-only queue. Open links manually; do not automate following.",
        "",
    ]
    if not queued:
        lines.append("No queued accounts yet. Add accounts with `tw target-accounts add @handle --cluster ...`.")
        return "\n".join(lines)
    for item in queued:
        lines.append(f"- {display_handle(item['handle'])} — {item['reason']}")
        lines.append(f"  - link: https://x.com/{normalize_handle(item['handle'])}")
        lines.append(f"  - queue_id: {item['queue_id']}")
        lines.append(f"  - priority: {item['priority']}")
    return "\n".join(lines) + "\n"


def _follow_queue_reason(row: dict[str, Any], cluster: str) -> str:
    note = _scoreable_note(str(row.get("notes") or "")).strip()
    if note:
        return _compact(note, 180)
    description = str(row.get("description") or "").strip()
    if description:
        return f"profile fit: {_compact(description, 160)}"
    relevance = row.get("relevance_score")
    noise = row.get("noise_score")
    if relevance is not None and noise is not None:
        return f"{cluster} target account; relevance={relevance}, noise={noise}"
    return f"{cluster} target account"


def _cached_source_posts(handles: list[str], limit: int):
    limit = max(1, min(200, limit))
    with connect_db() as conn:
        if handles:
            placeholders = ",".join("?" for _ in handles)
            return conn.execute(
                f"""
                select id, created_at, url, title, author, raw_text, summary, tags
                from sources
                where type = 'x_post' and lower(author) in ({placeholders})
                order by created_at desc
                limit ?
                """,
                [normalize_handle(handle) for handle in handles] + [limit],
            ).fetchall()
        return conn.execute(
            """
            select id, created_at, url, title, author, raw_text, summary, tags
            from sources
            where type = 'x_post'
            order by created_at desc
            limit ?
            """,
            (limit,),
        ).fetchall()


def _source_row_to_digest_item(row, cluster: str) -> dict[str, Any]:
    handle = normalize_handle(row["author"] or "")
    text = str(row["summary"] or row["raw_text"] or "").strip()
    post_id = str(row["id"] or "")
    return {
        "id": f"di_{short_hash(post_id + text, 12)}",
        "source_account_id": f"acct_{short_hash(handle, 12)}" if handle else "",
        "handle": handle,
        "post_id": post_id,
        "url": row["url"] or "",
        "created_at": row["created_at"] or iso_now(),
        "text": text,
        "public_metrics": "",
        "cluster": cluster,
        "relevance_score": 0.7 if text else 0.0,
        "actionability_score": 0.65 if text else 0.0,
        "suggested_action": "standalone_or_quote" if text else "ignore",
    }


def _digest_summary_markdown(cluster: str, items: list[dict[str, Any]], language: str) -> str:
    title = "Digest" if language == "en" else "Дайджест"
    lines = [f"# {title}: {cluster}", "", f"- raw items: {len(items)}", ""]
    if not items:
        lines.extend(
            [
                "No cached posts found for this cluster.",
                "Configure read-only X import or add target accounts with imported source posts.",
            ]
        )
        return "\n".join(lines)
    lines.append("## Important ideas")
    for item in items[:10]:
        lines.append(f"- {display_handle(item['handle'])}: {item['text']}")
    lines.append("")
    lines.append("## Ignore")
    lines.append("- generic hype without implementation detail")
    lines.append("- financial advice / trading signals")
    lines.append("- drama that does not improve the account graph")
    lines.append("")
    lines.append("## Project connections")
    lines.append("- connect observations to backtesting realism, systems work, or local agent workflows")
    lines.append("")
    lines.append("## Vocabulary")
    lines.append("- collect terms you do not yet own before using them as claims")
    return "\n".join(lines) + "\n"


def _standalone_ideas_markdown(cluster: str, items: list[dict[str, Any]]) -> str:
    lines = [f"# Standalone Ideas: {cluster}", ""]
    if not items:
        lines.append("- No standalone ideas yet; run a digest after importing read-only sources.")
        return "\n".join(lines) + "\n"
    for item in items[:3]:
        lines.append(f"- Write a build/learning note from this observation: {item['text']}")
        lines.append("  - angle: what assumption breaks in practice?")
        lines.append("  - avoid: pretending you already solved the whole problem")
    return "\n".join(lines) + "\n"


def _quote_candidates_markdown(cluster: str, items: list[dict[str, Any]]) -> str:
    lines = [f"# Quote Candidates: {cluster}", "", "Manual-only. Safe to skip.", ""]
    if not items:
        lines.append("- No quote candidates yet.")
        return "\n".join(lines) + "\n"
    for item in items[:5]:
        lines.append(f"## {display_handle(item['handle'])}")
        lines.append(f"- source: {item['url']}")
        lines.append(f"- why: concrete {cluster} observation")
        lines.append("- draft angle: add one specific implementation caveat, not 'great point'")
        lines.append(f"- source text: {item['text']}")
        lines.append("")
    return "\n".join(lines)


def _follow_suggestions_markdown(cluster: str) -> str:
    rows = list_target_accounts(cluster)[:5]
    lines = [f"# Follow Suggestions: {cluster}", "", "Manual-only.", ""]
    if not rows:
        lines.append("- No target accounts in this cluster yet.")
        return "\n".join(lines) + "\n"
    for row in rows:
        lines.append(f"- {display_handle(row['handle'])} — {row['notes'] or 'cluster target'}")
    return "\n".join(lines) + "\n"


def _count_lines(rows) -> list[str]:
    if not rows:
        return ["- none"]
    return [f"- {row['cluster']}: {row['count']}" for row in rows]


def _status_count_lines(rows) -> list[str]:
    if not rows:
        return ["- none"]
    return [f"- {row['cluster']} / {row['status']}: {row['count']}" for row in rows]


def _recommended_distribution(draft_type: str) -> str:
    if draft_type == "thread":
        return "thread"
    if draft_type in {"build-log", "article-note"}:
        return "standalone / build note"
    return "standalone"


def _infer_cluster_from_text(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ["backtest", "market", "execution", "fill"]):
        return "quant"
    if any(term in lowered for term in ["c++", "latency", "performance"]):
        return "systems"
    if any(term in lowered for term in ["agent", "codex", "mcp"]):
        return "ai_agents"
    if any(term in lowered for term in ["feature", "recsys", "pipeline"]):
        return "ml_infra"
    return "builders"


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)


def _compact(text: str, limit: int) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _maybe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
