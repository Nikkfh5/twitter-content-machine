from __future__ import annotations

from pathlib import Path

from twitter_content_machine.cli import build_parser, run_cli
from twitter_content_machine.db import connect_db
from twitter_content_machine.drafting import create_draft
from twitter_content_machine.workspace import ensure_workspace
from twitter_content_machine.x_read import XAPIProvider


class FakeBootstrapProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def search_users(self, query: str, limit: int):
        self.calls.append(("search_users", query, limit))
        return [
            {
                "id": "100",
                "username": "micro_builder",
                "name": "Micro Builder",
                "description": "market microstructure and execution systems",
                "public_metrics": {"followers_count": 4200, "following_count": 500},
                "verified": False,
            }
        ]

    def search_recent_posts(self, query: str, limit: int):
        self.calls.append(("search_recent_posts", query, limit))
        return [
            {
                "id": "200",
                "text": "Queue position and latency assumptions make many backtests look better than they are.",
                "created_at": "2026-06-06T20:00:00Z",
                "author_id": "100",
                "author_username": "micro_builder",
                "author_name": "Micro Builder",
                "author_description": "execution systems",
                "url": "https://x.com/micro_builder/status/200",
                "public_metrics": {"reply_count": 3, "retweet_count": 8, "like_count": 42},
            }
        ]

    def get_user_following(self, username: str, limit: int):
        self.calls.append(("get_user_following", username, limit))
        return [
            {
                "id": "101",
                "username": "latency_notes",
                "name": "Latency Notes",
                "description": "C++ low latency and exchange connectivity",
                "public_metrics": {"followers_count": 9000, "following_count": 700},
            }
        ]


class NoisyBootstrapProvider:
    def search_users(self, query: str, limit: int):
        return [
            {"id": "1", "username": "kanyewest", "name": "Ye", "description": ""},
            {
                "id": "2",
                "username": "benshapiro",
                "name": "Ben Shapiro",
                "description": "Daily Wire co-founder and political commentator",
            },
            {
                "id": "3",
                "username": "quantdev_real",
                "name": "Quant Dev Real",
                "description": "market microstructure, execution systems, backtesting realism",
                "public_metrics": {"followers_count": 2400, "following_count": 350},
            },
            {
                "id": "4",
                "username": "crypto_signal_guru",
                "name": "Crypto Signal Guru",
                "description": "100x crypto signals, PnL screenshots, free alpha",
            },
        ]

    def search_recent_posts(self, query: str, limit: int):
        return [
            {
                "id": "10",
                "text": "RT @someone: market microstructure pervert fun one with 2x ETF",
                "author_username": "rt_noise",
                "author_description": "retweets finance memes",
            },
            {
                "id": "11",
                "text": "Bitcoin alpha signal: 100x long setup, insane PnL soon.",
                "author_username": "crypto_signal_guru",
                "author_description": "100x crypto signals",
            },
            {
                "id": "12",
                "text": "Queue position and partial fills are the easiest way to make a toy backtest lie.",
                "author_username": "execution_notes",
                "author_description": "execution assumptions, exchange simulation, backtesting realism",
                "url": "https://x.com/execution_notes/status/12",
            },
            {
                "id": "13",
                "text": "No slippage or partial fills. DeFi execution layer powered by tokenized RWA liquidity.",
                "author_username": "defi_execution",
                "author_description": "Web3 DeFi tokenized RWA execution and crypto liquidity",
                "url": "https://x.com/defi_execution/status/13",
            },
            {
                "id": "14",
                "text": "Market microstructure is where queue position, partial fills, and latency make a clean backtest too optimistic.",
                "author_username": "market_micro_tourist",
                "author_description": "trading cards, gym, and family",
                "url": "https://x.com/market_micro_tourist/status/14",
            },
        ]

    def get_user_following(self, username: str, limit: int):
        return []


def test_bootstrap_plan_creates_daily_low_social_files(
    tw_root: Path, capsys
) -> None:
    ensure_workspace()

    assert run_cli(["bootstrap-plan", "--days", "14"]) == 0
    output = capsys.readouterr().out

    plan_dir = tw_root / "graph" / "plans" / "20260606-14day-bootstrap"
    assert "bootstrap plan" in output.lower()
    assert (plan_dir / "plan.md").exists()
    assert (plan_dir / "plan.json").exists()
    assert (plan_dir / "account_state.md").exists()
    assert (plan_dir / "graph_strategy.md").exists()
    assert (plan_dir / "personal_strategy.md").exists()
    assert (plan_dir / "daily" / "day_01.md").exists()
    day_01 = (plan_dir / "daily" / "day_01.md").read_text(encoding="utf-8").lower()
    assert "manual follow" in day_01
    assert "reply to 10" not in day_01
    assert "read the feed" not in day_01

    with connect_db() as conn:
        plan_count = conn.execute("select count(*) from bootstrap_plans").fetchone()[0]
        action_count = conn.execute("select count(*) from bootstrap_actions").fetchone()[0]
    assert plan_count == 1
    assert action_count >= 14 * 3


def test_bootstrap_plan_uses_profile_and_recent_drafts(
    tw_root: Path, tmp_path: Path, capsys
) -> None:
    project = tmp_path / "profile-project"
    project.mkdir()
    workspace = ensure_workspace()
    (workspace.root / "profile" / "persona.md").write_text(
        "Nikita builds public notebooks about C++, quant systems, and local agents.",
        encoding="utf-8",
    )
    create_draft("I found that execution assumptions erased the fake edge", "short", project, no_llm=True)

    assert run_cli(["bootstrap", "--days", "14"]) == 0
    capsys.readouterr()

    strategy_path = tw_root / "graph" / "plans" / "20260606-14day-bootstrap" / "personal_strategy.md"
    text = strategy_path.read_text(encoding="utf-8")
    assert "Nikita builds public notebooks" in text
    assert "execution assumptions" in text
    assert "quant systems" in text


def test_today_shows_current_bootstrap_actions(tw_root: Path, capsys) -> None:
    ensure_workspace()
    assert run_cli(["bootstrap-plan", "--days", "14"]) == 0
    capsys.readouterr()

    assert run_cli(["today"]) == 0
    output = capsys.readouterr().out

    assert "day 1/14" in output.lower()
    assert "Manual follow" in output
    assert "No mandatory replies" in output
    assert str(tw_root / "graph" / "plans" / "20260606-14day-bootstrap" / "daily" / "day_01.md") in output


def test_today_refresh_creates_daily_operator_packet(
    tw_root: Path, capsys
) -> None:
    ensure_workspace()
    assert run_cli(["target-accounts", "add", "@quant_dev", "--cluster", "quant", "--note", "execution realism"]) == 0
    capsys.readouterr()
    with connect_db() as conn:
        conn.execute(
            """
            insert into sources(id, created_at, type, url, title, author, raw_text, summary, tags)
            values(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "xsrc_quant_dev_refresh_1",
                "2026-06-06T20:00:00",
                "x_post",
                "https://x.com/quant_dev/status/42",
                "X post 42",
                "quant_dev",
                "Queue position is the missing variable in many toy execution models.",
                "Queue position is the missing variable in many toy execution models.",
                "peer",
            ),
        )
    assert run_cli(["bootstrap-plan", "--days", "14"]) == 0
    capsys.readouterr()

    assert run_cli(["today", "--refresh"]) == 0
    output = capsys.readouterr().out

    assert "daily operator packet" in output.lower()
    assert "@quant_dev" in output
    assert "Optional reply candidates" in output
    assert "Optional quote candidates" in output
    assert "No mandatory replies" in output
    packet = tw_root / "graph" / "plans" / "20260606-14day-bootstrap" / "daily" / "day_01_operator.md"
    assert packet.exists()
    text = packet.read_text(encoding="utf-8")
    assert "Queue position" in text
    assert "manual-only" in text.lower()


def test_graph_scan_runs_readonly_provider_and_writes_candidates(
    tw_root: Path, monkeypatch, capsys
) -> None:
    ensure_workspace()
    provider = FakeBootstrapProvider()
    monkeypatch.setattr("twitter_content_machine.bootstrap.get_provider", lambda: provider)
    monkeypatch.setattr("twitter_content_machine.commands.bootstrap_ops.x_read_setup_problem", lambda: None)
    assert run_cli(["target-accounts", "add", "@seed_quant", "--cluster", "quant", "--note", "seed account"]) == 0
    capsys.readouterr()

    assert run_cli(["graph-scan", "--cluster", "quant", "--limit", "20", "--posts", "25"]) == 0
    output = capsys.readouterr().out

    assert "graph scan:" in output.lower()
    assert any(call[0] == "search_users" for call in provider.calls)
    assert any(call[0] == "search_recent_posts" for call in provider.calls)
    assert any(call[0] == "get_user_following" for call in provider.calls)
    scan_dir = tw_root / "graph" / "scans" / "20260606-2130-quant"
    assert (scan_dir / "scan_report.md").exists()
    assert (scan_dir / "follow_suggestions.md").exists()
    assert (scan_dir / "reply_candidates.md").exists()
    assert (scan_dir / "quote_candidates.md").exists()
    report = (scan_dir / "scan_report.md").read_text(encoding="utf-8")
    assert "@micro_builder" in report
    assert "Queue position" in report
    assert "manual-only" in report.lower()
    with connect_db() as conn:
        handles = {
            row["handle"]
            for row in conn.execute("select handle from target_accounts").fetchall()
        }
        queued = {
            row["handle"]
            for row in conn.execute("select handle from follow_queue where status = 'queued'").fetchall()
        }
    assert {"micro_builder", "latency_notes"}.issubset(handles)
    assert "micro_builder" in queued


def test_graph_scan_filters_noisy_accounts_and_posts(
    tw_root: Path, monkeypatch, capsys
) -> None:
    ensure_workspace()
    provider = NoisyBootstrapProvider()
    monkeypatch.setattr("twitter_content_machine.bootstrap.get_provider", lambda: provider)
    monkeypatch.setattr("twitter_content_machine.commands.bootstrap_ops.x_read_setup_problem", lambda: None)
    assert run_cli(
        [
            "target-accounts",
            "add",
            "@old_query_noise",
            "--cluster",
            "quant",
            "--note",
            'recent_post_author: "market microstructure" OR "execution assumptions"',
        ]
    ) == 0
    capsys.readouterr()

    assert run_cli(["graph-scan", "--cluster", "quant", "--limit", "20", "--posts", "25"]) == 0
    capsys.readouterr()

    scan_dir = tw_root / "graph" / "scans" / "20260606-2130-quant"
    report = (scan_dir / "scan_report.md").read_text(encoding="utf-8")
    suggestions = (scan_dir / "follow_suggestions.md").read_text(encoding="utf-8")
    replies = (scan_dir / "reply_candidates.md").read_text(encoding="utf-8")
    rejects = (scan_dir / "rejects.md").read_text(encoding="utf-8")
    queue_text = sorted((tw_root / "graph" / "follow_queue").glob("*quant-follow_queue.md"))[-1].read_text(
        encoding="utf-8"
    )

    assert "@quantdev_real" in suggestions
    assert "@execution_notes" in suggestions
    assert "Queue position" in replies
    assert "@kanyewest" not in suggestions
    assert "@benshapiro" not in suggestions
    assert "@crypto_signal_guru" not in suggestions
    assert "@defi_execution" not in suggestions
    assert "@market_micro_tourist" not in suggestions
    assert "@old_query_noise" not in suggestions
    assert "@old_query_noise" not in queue_text
    assert "@defi_execution" not in queue_text
    assert "@market_micro_tourist" not in queue_text
    assert "recent_post_author:" not in queue_text
    assert "Market microstructure is where queue position" in replies
    assert "RT @someone" not in replies
    assert "@kanyewest" in rejects
    assert "low_relevance" in rejects
    assert "noise" in rejects


def test_graph_scan_without_x_provider_explains_setup(tw_root: Path, capsys) -> None:
    ensure_workspace()

    assert run_cli(["graph-scan", "--cluster", "quant", "--limit", "20", "--posts", "25"]) == 1
    output = capsys.readouterr().out

    assert "live X read provider is not configured" in output
    assert "[x]" in output
    assert "provider = \"x_api\"" in output
    assert "X_BEARER_TOKEN" in output


def test_today_refresh_live_x_includes_scan_packet(
    tw_root: Path, monkeypatch, capsys
) -> None:
    ensure_workspace()
    provider = FakeBootstrapProvider()
    monkeypatch.setattr("twitter_content_machine.bootstrap.get_provider", lambda: provider)
    monkeypatch.setattr("twitter_content_machine.commands.bootstrap_ops.x_read_setup_problem", lambda: None)
    assert run_cli(["bootstrap", "--days", "14"]) == 0
    capsys.readouterr()

    assert run_cli(["today", "--refresh", "--live-x"]) == 0
    output = capsys.readouterr().out

    assert "Live read-only X scan" in output
    assert "@micro_builder" in output
    packet = tw_root / "graph" / "plans" / "20260606-14day-bootstrap" / "daily" / "day_01_operator.md"
    assert "graph/scans/20260606-2130-quant" in packet.read_text(encoding="utf-8").replace("\\", "/")


def test_x_api_provider_uses_get_readonly_endpoints(monkeypatch) -> None:
    seen_urls: list[str] = []

    def fake_request(url: str, token: str, timeout: int = 30):
        seen_urls.append(url)
        if "/users/by/username/" in url:
            return {"data": {"id": "42", "username": "seed", "name": "Seed"}}
        if "/users/42/following" in url:
            return {"data": [{"id": "43", "username": "next", "name": "Next"}]}
        if "/users/search" in url:
            return {"data": [{"id": "44", "username": "search_hit", "name": "Search Hit"}]}
        if "/tweets/search/recent" in url:
            return {
                "data": [{"id": "55", "author_id": "44", "text": "execution systems"}],
                "includes": {"users": [{"id": "44", "username": "search_hit", "name": "Search Hit"}]},
            }
        raise AssertionError(url)

    monkeypatch.setattr("twitter_content_machine.x_read._request_json", fake_request)
    provider = XAPIProvider("token")

    assert provider.get_user_following("seed", 10)[0]["username"] == "next"
    assert provider.search_users("market microstructure", 10)[0]["username"] == "search_hit"
    assert provider.search_recent_posts("market microstructure", 10)[0]["author_username"] == "search_hit"

    assert seen_urls
    assert all("/following" in url or "/users/search" in url or "/tweets/search/recent" in url or "/users/by/username/" in url for url in seen_urls)
    assert not any("/following" in url and "POST" in url for url in seen_urls)


def test_log_action_marks_bootstrap_action_done(tw_root: Path, capsys) -> None:
    ensure_workspace()
    assert run_cli(["bootstrap-plan", "--days", "14"]) == 0
    capsys.readouterr()
    with connect_db() as conn:
        action_id = conn.execute(
            "select id from bootstrap_actions order by day, rowid limit 1"
        ).fetchone()["id"]

    assert run_cli(["log-action", action_id, "--done", "--note", "followed manually"]) == 0
    output = capsys.readouterr().out

    assert "done" in output
    with connect_db() as conn:
        row = conn.execute(
            "select status, details from bootstrap_actions where id = ?",
            (action_id,),
        ).fetchone()
    assert row["status"] == "done"
    assert "followed manually" in row["details"]


def test_follow_seed_creates_manual_queue_without_follow_command(
    tw_root: Path, capsys
) -> None:
    ensure_workspace()
    assert run_cli(["target-accounts", "add", "@micro_dev", "--cluster", "quant", "--note", "market microstructure"]) == 0
    capsys.readouterr()

    assert run_cli(["follow-seed", "--cluster", "quant", "--limit", "5"]) == 0
    output = capsys.readouterr().out

    parser = build_parser()
    command_names = {
        name
        for action in parser._actions
        if getattr(action, "choices", None)
        for name in action.choices
    }
    assert "follow" not in command_names
    assert "manual follow queue" in output.lower()
    queue_files = list((tw_root / "graph" / "follow_queue").glob("*quant*.md"))
    assert queue_files
    text = queue_files[-1].read_text(encoding="utf-8")
    assert "@micro_dev" in text
    assert "manual" in text.lower()
    with connect_db() as conn:
        row = conn.execute("select handle, status from follow_queue").fetchone()
    assert row["handle"] == "micro_dev"
    assert row["status"] == "queued"


def test_x_digest_uses_cached_readonly_sources(tw_root: Path, capsys) -> None:
    ensure_workspace()
    assert run_cli(["target-accounts", "add", "@quant_dev", "--cluster", "quant", "--note", "execution realism"]) == 0
    capsys.readouterr()
    with connect_db() as conn:
        conn.execute(
            """
            insert into sources(id, created_at, type, url, title, author, raw_text, summary, tags)
            values(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "xsrc_quant_dev_1",
                "2026-06-06T20:00:00",
                "x_post",
                "https://x.com/quant_dev/status/1",
                "X post 1",
                "quant_dev",
                "Backtests break when execution assumptions ignore queue position and latency.",
                "Backtests break when execution assumptions ignore queue position and latency.",
                "peer",
            ),
        )

    assert run_cli(["x-digest", "--cluster", "quant", "--limit", "50", "--ru"]) == 0
    output = capsys.readouterr().out

    assert "digest:" in output.lower()
    digest_dirs = list((tw_root / "graph" / "digests").glob("*quant"))
    assert digest_dirs
    latest = digest_dirs[-1]
    assert (latest / "raw_items.json").exists()
    assert "execution assumptions" in (latest / "digest.md").read_text(encoding="utf-8")
    assert (latest / "quote_candidates.md").exists()
    assert (latest / "standalone_ideas.md").exists()
    assert (latest / "follow_suggestions.md").exists()


def test_bootstrap_enabled_drafts_get_distribution_artifact(
    tw_root: Path, tmp_path: Path, capsys
) -> None:
    project = tmp_path / "bootstrap-draft"
    project.mkdir()
    ensure_workspace()

    assert run_cli(["draft", "--no-llm", "I learned that fake fills can erase a backtest edge"], cwd=project) == 0
    capsys.readouterr()
    with connect_db() as conn:
        row = conn.execute("select folder_path from drafts order by created_at desc limit 1").fetchone()
    folder = Path(row["folder_path"])

    artifact = folder / "17_distribution_bootstrap.md"
    assert artifact.exists()
    text = artifact.read_text(encoding="utf-8")
    assert "Distribution Bootstrap" in text
    assert "low_social" in text
    assert "Manual action" in text
