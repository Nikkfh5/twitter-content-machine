# CLI Simplification And Style Learn Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a simple `tw style-learn` command that learns from the user's approved own posts/drafts, and simplify the Russian CLI documentation around the commands the user will actually use.

**Architecture:** Keep the existing `tg_crypto_clean` profile as the single default identity style internally, but hide the profile argument from the daily CLI. Store learned post examples in a separate SQLite table and Markdown report so Telegram examples, manual gold files, X peer sources, and processed own posts stay distinguishable.

**Tech Stack:** Python argparse CLI, SQLite, existing `identity_style.py`, pytest, Markdown docs.

---

### Task 1: Add Processed Post Example Storage

**Files:**
- Modify: `twitter_content_machine/db.py`
- Test: `tests/test_core_workflow.py`

- [x] Add a `processed_style_examples` table with `profile_name`, `source_kind`, `source_id`, `text`, `label`, `reason`, and timestamps.
- [x] Add `processed_style_examples_fts` for future search support.
- [x] Verify `tw init` creates the table.

### Task 2: Implement `style_learn`

**Files:**
- Modify: `twitter_content_machine/identity_style.py`
- Test: `tests/test_core_workflow.py`

- [x] Add a public `style_learn(profile_name: str = "tg_crypto_clean") -> Path`.
- [x] Select only own approved material: drafts with status `ready` or `posted`, plus rows in `posts` with non-empty text.
- [x] Exclude rejected/draft-only/external material.
- [x] Deduplicate by text hash.
- [x] Store safe examples as `processed_post_gold`.
- [x] Write `identity_styles/tg_crypto_clean/processed_posts_report.md`.
- [x] Write `identity_styles/tg_crypto_clean/post_gold_examples.md`.
- [x] Refresh `style_stats.md`.

### Task 3: Wire CLI And MCP

**Files:**
- Modify: `twitter_content_machine/cli.py`
- Modify: `twitter_content_machine/mcp_server.py`
- Test: `tests/test_core_workflow.py`

- [x] Add command `tw style-learn` with no required profile argument.
- [x] Keep the profile internal to the default style; do not expose `--profile` on daily `tw style-learn`.
- [x] Expose MCP wrapper `tw_style_learn`.
- [x] Do not add any publish/write-X command.

### Task 4: Simplify Russian CLI Documentation

**Files:**
- Modify: `docs/cli_descripsion_russion.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/style-learning-from-posts-backlog.md`

- [x] Move daily commands to the top: `tw draft`, `tw edit`, `tw ready`, `tw posted`, `tw style-learn`.
- [x] Remove daily emphasis from redundant flags: `--llm`, `--model`, `--reasoning-effort`, `--speed`, `--algo-aware`, `--short`, `--context-only`, `--print-prompt-path`.
- [x] Mark `queue`, `mark-ready`, `mark-posted`, `open --print-path`, detailed `algo-review/media-plan/distribution-plan`, and `refine --pass ...` as legacy/debug.
- [x] Document that `ready` and `posted` are both "approved own texts" for `style-learn`.

### Task 5: Verification

**Files:**
- Test: `tests/test_core_workflow.py`

- [x] Run focused tests for style learning.
- [x] Run full test suite with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`.
- [x] Commit and push.
