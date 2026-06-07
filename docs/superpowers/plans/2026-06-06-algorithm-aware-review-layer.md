# Algorithm-Aware Review Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local, draft-only algorithm-aware review layer for X/Twitter drafts.

**Architecture:** Keep draft generation unchanged by default. Add a focused algorithm review module that reads existing draft artifacts, writes `07_algorithm_review.md`, `08_media_plan.md`, and `09_distribution_plan.md`, and exposes CLI commands plus `tw draft --algo-aware`.

**Tech Stack:** Python 3.11 stdlib, SQLite/FTS5, pytest.

---

## Task 1: Documentation And Resume Trail

**Files:**
- Create: `docs/algorithm-aware/ideas-and-backlog.md`
- Create: `docs/superpowers/specs/2026-06-06-algorithm-aware-review-layer-design.md`
- Create: `docs/superpowers/plans/2026-06-06-algorithm-aware-review-layer.md`
- Create: `docs/superpowers/progress/2026-06-06-algorithm-aware-review-layer-progress.md`

- [x] Capture the user research, Stage 1 MVP, Stage 2 backlog, and session anchor.
- [x] Record why Stage 2 ideas are strong but postponed.
- [x] Append final verification evidence after implementation.

## Task 2: RED Tests For New CLI Commands

**Files:**
- Modify: `tests/test_core_workflow.py`

- [x] Add tests for `algo-review`, `media-plan`, `distribution-plan`, and `draft --algo-aware`.
- [x] Run tests and verify they fail because commands/files do not exist.

Command:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q
```

Expected: failures mentioning missing CLI commands or missing review files.

## Task 3: Algorithm Review Module

**Files:**
- Create: `twitter_content_machine/algorithm_review.py`

- [x] Implement draft resolution through existing draft metadata.
- [x] Implement heuristic scoring and decisions.
- [x] Implement writers for `07_algorithm_review.md`, `08_media_plan.md`, `09_distribution_plan.md`.
- [x] Keep all output local to the draft folder.

## Task 4: CLI Wiring

**Files:**
- Modify: `twitter_content_machine/cli.py`

- [x] Add `tw algo-review <draft_id>`.
- [x] Add `tw media-plan <draft_id>`.
- [x] Add `tw distribution-plan <draft_id>`.
- [x] Add `tw draft --algo-aware`.
- [x] Ensure default draft behavior remains unchanged.

## Task 5: Workspace Defaults

**Files:**
- Modify: `twitter_content_machine/workspace.py`

- [x] Add `profile/x_algorithm_principles.md`.
- [x] Add `profile/x_fit_rubric.yaml`.
- [x] Preserve existing user-edited profile files.

## Task 6: Skill And Agent Notes

**Files:**
- Modify: `skills/twitter-content/SKILL.md`
- Modify: `AGENTS.md`
- Modify: `README.md`

- [x] Document algorithm-aware drafting rules.
- [x] Document new CLI commands.
- [x] Preserve draft-only/no-publish rules.

## Task 7: Verification

**Files:**
- Modify: `docs/superpowers/progress/2026-06-06-algorithm-aware-review-layer-progress.md`

- [x] Run full tests.
- [x] Run `python -m twitter_content_machine doctor`.
- [x] Run a repo-local smoke command with `.tmp-twitter-system` if needed.
- [x] Record exact command outputs in progress log.
