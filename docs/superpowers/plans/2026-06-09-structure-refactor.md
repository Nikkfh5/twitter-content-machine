# Structure Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `refactoring` plus `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce oversized files and make the repo readable without changing CLI behavior, draft artifacts, database behavior, or public commands.

**Architecture:** Refactor by stable responsibility boundaries. Start with test layout because it is the lowest-risk structure change, then split runtime modules only after tests are easier to navigate. Keep `tw = twitter_content_machine.cli:main` stable.

**Tech Stack:** Python 3.11+, pytest, argparse, SQLite/FTS5, Codex CLI wrappers.

---

## Current Hotspots

Measured on 2026-06-09:

| File | Lines | Problem |
| --- | ---: | --- |
| `tests/test_core_workflow.py` | 1184 | Tests for workspace, drafting, LLM, Codex sessions, algorithm review, identity style, X read, and MCP are mixed together. |
| `twitter_content_machine/cli.py` | 582 | Parser construction, command handlers, display helpers, and workflow glue are in one file. |
| `twitter_content_machine/identity_style.py` | 554 | Profile loading, auto-selection, style learning, stats, curation, and review artifact writing are mixed. |
| `twitter_content_machine/algorithm_review.py` | 463 | Constants, risk detection, scoring, review rendering, media plan, and distribution plan are mixed. |
| `twitter_content_machine/drafting.py` | 371 | Draft creation, fallback generation, LLM orchestration, file writing, review, status changes are mixed. |

## Non-Negotiables

- No behavior changes.
- No new features in refactor commits.
- No X publishing or write APIs.
- Keep `tw` entrypoint stable.
- Keep old CLI commands/aliases working.
- Full test suite must pass after each meaningful slice.
- Prefer mechanical moves over rewrites.

## Target Structure

### Tests

Create:
- `tests/conftest.py`
- `tests/test_workspace_context.py`
- `tests/test_drafting_workflow.py`
- `tests/test_llm_codex.py`
- `tests/test_active_draft_cli.py`
- `tests/test_codex_sessions.py`
- `tests/test_algorithm_review.py`
- `tests/test_identity_style.py`
- `tests/test_memory_x_mcp.py`

Remove:
- `tests/test_core_workflow.py` after all tests are moved.

### Runtime, Later Slices

CLI:
- keep `twitter_content_machine/cli.py` as the public entrypoint
- extract command groups later into `twitter_content_machine/commands/`
- extract parser construction only after command handlers are stable

Algorithm review:
- `algorithm_terms.py`: constants and phrase lists
- `algorithm_scoring.py`: tokenization, repeated memory, risk facts, scoring
- `algorithm_artifacts.py`: markdown rendering for review/media/distribution
- keep compatibility wrappers in `algorithm_review.py`

Identity style:
- `identity_context.py`: load profile/context/examples
- `identity_auto_select.py`: auto-gold scoring/selection
- `identity_learning.py`: style-learn from approved own writing
- `identity_artifacts.py`: stats/curation/review files
- keep compatibility wrappers in `identity_style.py`

Drafting:
- `draft_fallbacks.py`: template fallback variants
- `draft_artifacts.py`: draft folder file writing
- `draft_status.py`: ready/reject/posted state changes
- keep `create_draft`, `get_draft`, `review_draft`, `refine_draft`, `set_draft_status` stable

## Task 1: Split The Giant Test File

**Files:**
- Create: `tests/conftest.py`
- Create: domain test files listed above
- Delete: `tests/test_core_workflow.py`

- [x] **Step 1: Run baseline tests**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q
```

Expected:

```text
51 passed
```

- [x] **Step 2: Move `tw_root` fixture**

Create `tests/conftest.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def tw_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "twitter-system"
    monkeypatch.setenv("TWITTER_SYSTEM_ROOT", str(root))
    monkeypatch.setenv("TW_TEST_FIXED_NOW", "2026-06-06T21:30:45")
    return root
```

- [x] **Step 3: Move tests mechanically by domain**

Use the current import block from `tests/test_core_workflow.py` in each new test file first. Remove unused imports only after the split is green.

Domain mapping:
- workspace/context/config/review basics -> `tests/test_workspace_context.py`
- draft creation/defaults/context-only/default identity/prompt path -> `tests/test_drafting_workflow.py`
- LLM parser/Codex invocation/progress -> `tests/test_llm_codex.py`
- active draft commands/edit/search/style-gold -> `tests/test_active_draft_cli.py`
- native content Codex sessions -> `tests/test_codex_sessions.py`
- algorithm/media/distribution review -> `tests/test_algorithm_review.py`
- Telegram import/identity style/style learn -> `tests/test_identity_style.py`
- MCP/project-aware memory/X read -> `tests/test_memory_x_mcp.py`

- [x] **Step 4: Run focused collection check**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest --collect-only -q
```

Expected:

```text
51 tests collected
```

- [x] **Step 5: Run full tests**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q
```

Expected:

```text
51 passed
```

- [x] **Step 6: Commit**

```powershell
git add tests
git commit -m "refactor: split core workflow tests"
```

## Task 2: Split Algorithm Review Internals

**Files:**
- Create: `twitter_content_machine/algorithm_terms.py`
- Create: `twitter_content_machine/algorithm_scoring.py`
- Create: `twitter_content_machine/algorithm_artifacts.py`
- Modify: `twitter_content_machine/algorithm_review.py`
- Test: `tests/test_algorithm_review.py`

- [x] **Step 1: Move constants only**
- [x] **Step 2: Run `tests/test_algorithm_review.py`**
- [x] **Step 3: Move scoring/facts only**
- [x] **Step 4: Run `tests/test_algorithm_review.py`**
- [x] **Step 5: Move artifact rendering only**
- [x] **Step 6: Run full tests**
- [x] **Step 7: Commit**

Commit:

```powershell
git commit -m "refactor: split algorithm review internals"
```

## Task 3: Split Identity Style Internals

**Files:**
- Create: `twitter_content_machine/identity_context.py`
- Create: `twitter_content_machine/identity_auto_select.py`
- Create: `twitter_content_machine/identity_learning.py`
- Create: `twitter_content_machine/identity_artifacts.py`
- Modify: `twitter_content_machine/identity_style.py`
- Test: `tests/test_identity_style.py`

- [x] **Step 1: Move profile/context loading**
- [x] **Step 2: Run `tests/test_identity_style.py`**
- [x] **Step 3: Move auto-selection**
- [x] **Step 4: Run `tests/test_identity_style.py`**
- [x] **Step 5: Move style learning**
- [x] **Step 6: Run `tests/test_identity_style.py`**
- [x] **Step 7: Move artifact rendering**
- [x] **Step 8: Run full tests**
- [ ] **Step 9: Commit**

Commit:

```powershell
git commit -m "refactor: split identity style internals"
```

## Task 4: Split CLI Without Changing Entrypoint

**Files:**
- Create: `twitter_content_machine/commands/`
- Create: command group modules after tests are already split
- Modify: `twitter_content_machine/cli.py`
- Test: all CLI test files

- [ ] **Step 1: Extract command handlers by group, keep parser in `cli.py`**
- [ ] **Step 2: Run CLI-focused tests**
- [ ] **Step 3: Extract parser construction if still needed**
- [ ] **Step 4: Run full tests**
- [ ] **Step 5: Commit**

Commit:

```powershell
git commit -m "refactor: split cli command handlers"
```

## Task 5: Split Drafting Internals

**Files:**
- Create: `twitter_content_machine/draft_fallbacks.py`
- Create: `twitter_content_machine/draft_artifacts.py`
- Create: `twitter_content_machine/draft_status.py`
- Modify: `twitter_content_machine/drafting.py`
- Test: `tests/test_drafting_workflow.py`, `tests/test_active_draft_cli.py`

- [ ] **Step 1: Move fallback variant generation**
- [ ] **Step 2: Run drafting tests**
- [ ] **Step 3: Move draft artifact file-writing helpers**
- [ ] **Step 4: Run drafting tests**
- [ ] **Step 5: Move status changes**
- [ ] **Step 6: Run full tests**
- [ ] **Step 7: Commit**

Commit:

```powershell
git commit -m "refactor: split drafting internals"
```

## Completion Criteria

- No public command behavior changed.
- `python -m pytest -q` passes with plugin autoload disabled.
- No file in `twitter_content_machine/` exceeds roughly 350 lines unless it has a clear reason.
- Test files are domain-readable.
- `AGENTS.md`/README are updated only if module names or workflow docs changed.
