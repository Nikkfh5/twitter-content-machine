# Workspace Refactor And UX V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current content workspace from a technically working TUI checkpoint into a maintainable author-facing workspace, while preserving the draft-only contract and avoiding unrelated dirty worktree changes.

**Architecture:** Keep the file-backed `Session -> Run -> Step -> Event -> Artifact` engine. Split the workspace code by responsibility: command/run orchestration, protocol artifact writing, view-model construction, Textual layout, and CLI routing. Improve UX through tested screen states before adding new flows.

**Tech Stack:** Python 3.11+, Textual, pytest, SQLite-backed existing draft storage, file-backed workspace sessions under `~/twitter-system/sessions/`.

---

## Current Ground Truth

Committed and pushed:
- `393f643 docs: design content workspace tui`
- `e14aa57 feat: add content workspace tui mvp`
- `bc98c69 refactor: split workspace view and protocol`

Current verified state after `bc98c69`:
- full suite: `87 passed`
- workspace service split:
  - `twitter_content_machine/workspace_service.py`
  - `twitter_content_machine/workspace_view.py`
  - `twitter_content_machine/workspace_protocol.py`
  - `twitter_content_machine/workspace_tui.py`

Current dirty tree has unrelated work:
- graph bootstrap files
- outcome files
- roadmap/doc updates
- CLI changes for bootstrap/outcomes
- tests outside workspace

Hard rule for this plan:
- stage and commit only files explicitly named in each task
- do not absorb unrelated dirty files
- preserve “draft only, never publish”

## File Structure Target

### Workspace Runtime

- `twitter_content_machine/workspace_service.py`
  - Owns slash command dispatch, session/run selection, step execution.
  - Must not render the TUI layout.
  - Must not write Codex protocol files directly.

- `twitter_content_machine/workspace_view.py`
  - Builds author-facing screen text/view-model from session/run/protocol state.
  - Owns labels, next action text, progress display, activity wording.
  - Must not execute steps or mutate files.

- `twitter_content_machine/workspace_protocol.py`
  - Owns workspace-specific protocol artifacts:
    - `AGENTS.md`
    - `TASK.md`
    - `OUTPUT_SCHEMA.md`
    - `interface_summary.md`
    - `interface_summary.json`
    - `artifacts.json`
  - Owns applying successful LLM output to draft files.

- `twitter_content_machine/workspace_tui.py`
  - Temporary Textual entrypoint.
  - Should shrink further by moving layout parsing and app class into focused modules.

### New Modules Planned

- `twitter_content_machine/workspace_tui_sections.py`
  - Pure parsing from screen text to sections used by Textual panels.
  - No Textual imports.

- `twitter_content_machine/workspace_tui_app.py`
  - Textual `WorkspaceApp` class.
  - Imports Textual.
  - Owns widgets, layout, refresh loop, command input.

- `twitter_content_machine/workspace_tui.py`
  - Thin import/fallback wrapper:
    - imports `WorkspaceApp`
    - handles Textual import failure
    - runs the app

- `twitter_content_machine/cli_parser.py`
  - Later phase.
  - Builds parser or parser groups when CLI dirty work is under control.

## Phase 0: Stabilize Baseline

### Task 0.1: Verify Current Workspace Checkpoint

**Files:**
- Read only:
  - `twitter_content_machine/workspace_service.py`
  - `twitter_content_machine/workspace_view.py`
  - `twitter_content_machine/workspace_protocol.py`
  - `twitter_content_machine/workspace_tui.py`
  - `tests/test_workspace_service.py`
  - `tests/test_workspace_tui.py`

- [ ] **Step 1: Run focused workspace tests**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_service.py tests\test_workspace_tui.py tests\test_workspace_cli.py tests\test_workspace_runs.py tests\test_workspace_sessions.py tests\test_output_protocol.py
```

Expected:

```text
18 passed
```

- [ ] **Step 2: Run smoke render without opening Textual**

Run:

```powershell
$smoke = Join-Path $env:TEMP ('tw-plan-smoke-' + [guid]::NewGuid().ToString('N'))
$env:TWITTER_SYSTEM_ROOT=$smoke
@'
from pathlib import Path
from twitter_content_machine.workspace_service import ContentWorkspaceService
from twitter_content_machine.workspace_tui import _split_screen
s = ContentWorkspaceService(cwd=Path.cwd())
s.handle('/draft refactor smoke')
s.handle('/continue')
sections = _split_screen(s.render_summary())
print(sections['next'])
print(sections['progress'].splitlines()[0])
'@ | python -
```

Expected:

```text
/continue --run - run Codex and create final candidate
[x] create draft files
```

- [ ] **Step 3: Record dirty baseline**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## main...origin/main
```

Plus unrelated modified/untracked files may appear. Do not stage them.

## Phase 1: Split Textual TUI Into Testable Units

Verdict: strong first refactor.

Edge:
- Removes the exact class of bug that just happened: Textual app code directly indexed a section key with no contract.

Risk:
- Textual import/runtime behavior can break if the wrapper and app module are split carelessly.

Simplify/drop:
- Do not add new UI features in this phase.
- Do not change visible screen copy except where tests require stable keys.

Becomes strong if:
- Pure section parsing is fully tested without Textual.
- Textual wrapper remains tiny and easy to inspect.

### Task 1.1: Move Section Parsing To `workspace_tui_sections.py`

**Files:**
- Create: `twitter_content_machine/workspace_tui_sections.py`
- Modify: `twitter_content_machine/workspace_tui.py`
- Test: `tests/test_workspace_tui.py`

- [ ] **Step 1: Write failing import/contract test**

Edit `tests/test_workspace_tui.py` so the import becomes:

```python
from twitter_content_machine.workspace_tui_sections import split_screen
```

Keep this test:

```python
def test_split_screen_returns_keys_used_by_tui_refresh() -> None:
    sections = split_screen(
        """Content Workspace

Status: active/needs_user
Next action: /continue --run - run Codex

Draft preview
draft text

Summary
summary text

Problems
- problem

Decisions
- decision

Progress
[x] create draft files

Files
- draft: C:/draft

Recent activity
- Waiting for your next command
"""
    )

    for key in [
        "state",
        "progress",
        "Draft preview",
        "Summary",
        "Problems",
        "Decisions",
        "Files",
        "Recent activity",
        "next",
    ]:
        assert key in sections
    assert sections["progress"] == "[x] create draft files"
    assert sections["next"] == "/continue --run - run Codex"
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_tui.py::test_split_screen_returns_keys_used_by_tui_refresh
```

Expected:

```text
ModuleNotFoundError: No module named 'twitter_content_machine.workspace_tui_sections'
```

- [ ] **Step 3: Create `workspace_tui_sections.py`**

Create:

```python
from __future__ import annotations


SCREEN_HEADINGS = [
    "Draft preview",
    "Summary",
    "Problems",
    "Decisions",
    "Progress",
    "Files",
    "Recent activity",
]


def split_screen(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"state": []}
    current = "state"
    for line in text.splitlines():
        if line in SCREEN_HEADINGS:
            current = line
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    result = {key: "\n".join(value).strip() for key, value in sections.items()}
    state_lines = result.get("state", "").splitlines()
    next_lines = [line for line in state_lines if line.startswith("Next action:")]
    result["state"] = "\n".join(line for line in state_lines if not line.startswith("Next action:")).strip()
    result["next"] = next_lines[0].replace("Next action:", "").strip() if next_lines else "/draft <idea>"
    for heading in SCREEN_HEADINGS:
        result.setdefault(heading, "")
    result["progress"] = result.get("Progress", "")
    return result
```

- [ ] **Step 4: Update `workspace_tui.py` import and usage**

In `twitter_content_machine/workspace_tui.py`, add:

```python
from .workspace_tui_sections import split_screen
```

Replace:

```python
sections = _split_screen(self.service.render_summary())
```

with:

```python
sections = split_screen(self.service.render_summary())
```

Delete `_split_screen` and keep `_panel` for now.

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_tui.py
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Run focused workspace tests**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_tui.py tests\test_workspace_service.py tests\test_workspace_cli.py
```

Expected:

```text
9 passed
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add tests\test_workspace_tui.py twitter_content_machine\workspace_tui.py twitter_content_machine\workspace_tui_sections.py
git commit -m "refactor: split workspace tui sections"
```

### Task 1.2: Move Textual App Class To `workspace_tui_app.py`

**Files:**
- Create: `twitter_content_machine/workspace_tui_app.py`
- Modify:
  - `twitter_content_machine/workspace_tui.py`
  - `tests/test_workspace_cli.py`

- [ ] **Step 1: Add test that wrapper still exposes `run_workspace_app`**

Append to `tests/test_workspace_cli.py`:

```python
def test_workspace_tui_wrapper_exports_run_workspace_app() -> None:
    from twitter_content_machine.workspace_tui import run_workspace_app

    assert callable(run_workspace_app)
```

- [ ] **Step 2: Verify test passes before move**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_cli.py::test_workspace_tui_wrapper_exports_run_workspace_app
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Create `workspace_tui_app.py`**

Move the Textual-dependent class from `workspace_tui.py` into:

```python
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Static

from .workspace_service import ContentWorkspaceService
from .workspace_tui_sections import split_screen


def panel(title: str, body: str) -> str:
    body = body.strip() or "none"
    return f"{title}\n\n{body}"


class WorkspaceApp(App):
    CSS = """...copy current CSS exactly..."""
    BINDINGS = [("ctrl+c", "quit", "Exit")]

    def __init__(self, cwd: Path | None = None) -> None:
        super().__init__()
        self.service = ContentWorkspaceService(cwd=cwd)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="workspace"):
            with Vertical(id="left", classes="column"):
                yield Static("", id="state", classes="panel")
                yield Static("", id="progress", classes="panel")
            with Vertical(id="center", classes="column"):
                yield Static("", id="preview", classes="panel")
                yield Static("", id="summary", classes="panel")
                yield Static("", id="problems", classes="panel")
            with Vertical(id="right", classes="column"):
                yield Static("", id="next", classes="panel")
                yield Static("", id="activity", classes="panel")
        yield Input(placeholder="/draft ...", id="command")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Content Workspace"
        self.refresh_screen()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        result = self.service.handle(event.value)
        self.refresh_screen(result.message)
        event.input.value = ""
        if result.exit_requested:
            self.exit()

    def refresh_screen(self, message: str = "") -> None:
        sections = split_screen(self.service.render_summary())
        self.query_one("#state", Static).update(panel("Session", sections["state"]))
        self.query_one("#progress", Static).update(panel("Progress", sections["progress"]))
        self.query_one("#preview", Static).update(panel("Draft preview", sections["Draft preview"]))
        self.query_one("#summary", Static).update(panel("Summary", sections["Summary"]))
        self.query_one("#problems", Static).update(panel("Problems / Decisions", sections["Problems"] + "\n\n" + sections["Decisions"]))
        next_text = sections["next"]
        if message:
            next_text = message + "\n\n" + next_text
        self.query_one("#next", Static).update(panel("Next action", next_text))
        self.query_one("#activity", Static).update(panel("Activity / Files", sections["Recent activity"] + "\n\n" + sections["Files"]))
```

When implementing, copy the current CSS body exactly instead of replacing it with the placeholder string above.

- [ ] **Step 4: Make `workspace_tui.py` a thin wrapper**

Replace `twitter_content_machine/workspace_tui.py` contents with:

```python
from __future__ import annotations

from pathlib import Path


def run_workspace_app(cwd: Path | None = None) -> int:
    try:
        from .workspace_tui_app import WorkspaceApp
    except Exception as exc:
        print("Textual workspace failed to start.")
        print(f"error: {exc}")
        print("Hints:")
        print("- install dependencies: pip install -e .")
        print("- existing CLI still works: tw draft --no-llm \"idea\"")
        return 1

    WorkspaceApp(cwd=cwd).run()
    return 0
```

- [ ] **Step 5: Verify focused tests**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_tui.py tests\test_workspace_cli.py
```

Expected:

```text
3 passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add twitter_content_machine\workspace_tui.py twitter_content_machine\workspace_tui_app.py tests\test_workspace_cli.py
git commit -m "refactor: split workspace tui app"
```

## Phase 2: Add View-Model Tests Before Further UX Changes

Verdict: strong.

Edge:
- Lets us improve the UX without opening the TUI every time.
- Prevents regressions like raw event spam and missing next-action panels.

Risk:
- Over-testing exact prose can freeze bad copy.

Simplify/drop:
- Test structure and required sections, not every sentence.

Becomes strong if:
- We have tests for empty, pending Codex, completed summary, and failed run.

### Task 2.1: Add Empty Workspace Screen Test

**Files:**
- Modify: `tests/test_workspace_service.py`
- Touch: `twitter_content_machine/workspace_view.py` only if test fails for a real issue

- [ ] **Step 1: Write test**

Add:

```python
def test_empty_workspace_screen_has_single_start_action(tw_root: Path, tmp_path: Path) -> None:
    service = ContentWorkspaceService(cwd=tmp_path)

    screen = service.render_summary()

    assert "Status: empty" in screen
    assert "Next action: /draft <idea>" in screen
    assert "No active draft yet." in screen
    assert "step_started" not in screen
    assert "events.jsonl" not in screen
```

- [ ] **Step 2: Run test**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_service.py::test_empty_workspace_screen_has_single_start_action
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Commit with other Task 2 view tests**

Do not commit yet if proceeding immediately to Task 2.2.

### Task 2.2: Add Completed Codex Summary Screen Test

**Files:**
- Modify: `tests/test_workspace_service.py`

- [ ] **Step 1: Write test using fake Codex result**

Add:

```python
def test_workspace_screen_shows_final_summary_after_codex(
    tw_root: Path, tmp_path: Path, monkeypatch
) -> None:
    def fake_create_draft(**kwargs):
        draft_folder = tw_root / "drafts" / "2026" / "06" / "draft_fake"
        draft_folder.mkdir(parents=True)
        for name in ["FORMAT_DECISION.md", "13_context_bundle.md", "13_context_bundle.json", "14_llm_request.md"]:
            (draft_folder / name).write_text(name, encoding="utf-8")
        (draft_folder / "06_final_candidate.md").write_text("fallback draft", encoding="utf-8")
        return type("Draft", (), {"id": "draft_fake", "folder": draft_folder, "final_text": "fallback draft"})()

    class Parsed:
        ok = True
        error = ""
        data = {
            "variants": [{"id": "A", "name": "direct", "text": "Final draft.", "intent": "dwell", "why_it_might_work": "specific", "risks": []}],
            "critique": {"real_point": "specific", "too_generic": False},
            "selected_variant_id": "A",
            "final_candidate": "Final draft.",
        }

    class Result:
        attempted = True
        ok = True
        raw_output = '{"final_candidate":"Final draft."}'
        parsed = Parsed()
        message = "codex ok"

    monkeypatch.setattr("twitter_content_machine.workspace_service.create_draft", fake_create_draft)
    monkeypatch.setattr("twitter_content_machine.workspace_service.run_llm", lambda *args, **kwargs: Result())
    service = ContentWorkspaceService(cwd=tmp_path)
    service.handle("/draft raw thought")
    service.handle("/continue")
    service.handle("/continue --run")

    screen = service.render_summary()

    assert "Final draft." in screen
    assert "MVP не публикует" in screen or "draft_only" in screen
    assert "[x] run Codex" in screen
    assert "step_finished" not in screen
```

- [ ] **Step 2: Run test**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_service.py::test_workspace_screen_shows_final_summary_after_codex
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Run all workspace service tests**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_service.py
```

Expected:

```text
8 passed
```

- [ ] **Step 4: Commit**

Run:

```powershell
git add tests\test_workspace_service.py
git commit -m "test: cover workspace screen states"
```

## Phase 3: UX V2 Without Rebuilding The Engine

Verdict: normal-to-strong.

Edge:
- This is where the product becomes usable: visible state, obvious next action, no log spam.

Risk:
- Textual can become a dashboard toy if we keep adding panels.

Simplify/drop:
- Do not add `/edit`, `/review`, `/ready`, `/posted` yet.
- Do not add SQLite index yet.
- Do not add mouse-heavy behavior; terminal-first remains the product.

Becomes strong if:
- The first viewport answers:
  - what is being written
  - current draft text
  - what is wrong
  - what to do next
  - where files live

### Task 3.1: Replace “Slash Command First” Empty State With Author Prompt

**Files:**
- Modify: `twitter_content_machine/workspace_view.py`
- Test: `tests/test_workspace_service.py`

- [ ] **Step 1: Write failing test for empty state copy**

Add:

```python
def test_empty_workspace_invites_plain_author_intent(tw_root: Path, tmp_path: Path) -> None:
    service = ContentWorkspaceService(cwd=tmp_path)

    screen = service.render_summary()

    assert "Write the raw idea first" in screen
    assert "/draft <idea>" in screen
    assert "No active draft yet." in screen
```

- [ ] **Step 2: Verify RED if current copy does not contain phrase**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_service.py::test_empty_workspace_invites_plain_author_intent
```

Expected:

```text
FAIL: assert 'Write the raw idea first' in screen
```

- [ ] **Step 3: Update empty screen copy**

In `render_empty_workspace_screen`, use:

```python
"Write the raw idea first. It can be rough, mixed-language, or just a note.",
"Command: /draft <idea>",
```

Keep `Next action: /draft <idea>` unchanged because the TUI parser depends on it.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_service.py::test_empty_workspace_invites_plain_author_intent
```

Expected:

```text
1 passed
```

### Task 3.2: Add Plain Text Convenience As A Tested Follow-Up

Do this only after Task 3.1.

**Files:**
- Modify: `twitter_content_machine/workspace_service.py`
- Test: `tests/test_workspace_service.py`

- [ ] **Step 1: Write failing test**

Add:

```python
def test_plain_text_starts_draft_when_no_session_exists(tw_root: Path, tmp_path: Path) -> None:
    service = ContentWorkspaceService(cwd=tmp_path)

    result = service.handle("rough note about validation")

    assert result.ok is True
    assert result.run is not None
    assert result.run.input_text == "rough note about validation"
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_service.py::test_plain_text_starts_draft_when_no_session_exists
```

Expected:

```text
FAIL: result.ok is False
```

- [ ] **Step 3: Implement minimal behavior**

In `ContentWorkspaceService.handle`, replace the non-slash branch:

```python
if not command.startswith("/"):
    if self.session is None:
        return self.draft(command)
    return WorkspaceCommandResult(False, "Commands for an active draft still need slash syntax. Try: /continue or /help", self.session)
```

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_service.py::test_plain_text_starts_draft_when_no_session_exists
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Run focused workspace tests**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_service.py tests\test_workspace_tui.py tests\test_workspace_cli.py
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add twitter_content_machine\workspace_service.py twitter_content_machine\workspace_view.py tests\test_workspace_service.py
git commit -m "feat: improve workspace first-run input"
```

## Phase 4: CLI Refactor Only After Dirty CLI Work Is Resolved

Verdict: currently weak to do immediately.

Reason:
- `twitter_content_machine/cli.py` is dirty with unrelated bootstrap/outcome changes.
- Refactoring it now risks mixing features and infrastructure.

Required precondition:
- Decide whether the current dirty bootstrap/outcomes changes should be committed, reverted by the user, or left for another branch.

### Task 4.1: Audit CLI Dirty State Before Touching It

**Files:**
- Read only:
  - `twitter_content_machine/cli.py`
  - `twitter_content_machine/cli_commands.py`
  - `twitter_content_machine/commands/*.py`

- [ ] **Step 1: Inspect CLI diff**

Run:

```powershell
git diff -- twitter_content_machine\cli.py twitter_content_machine\cli_commands.py
```

Expected:

```text
Diff shows bootstrap/outcome/workspace changes. Do not stage unrelated hunks.
```

- [ ] **Step 2: List parser commands**

Run:

```powershell
python - <<'PY'
from twitter_content_machine.cli import build_parser
parser = build_parser()
for action in parser._actions:
    if action.__class__.__name__ == "_SubParsersAction":
        print("\n".join(sorted(action.choices)))
PY
```

Expected:

```text
List includes existing commands. No command named post.
```

- [ ] **Step 3: Stop for decision**

Do not refactor CLI until user chooses one:

```text
A. Commit dirty bootstrap/outcome changes separately first.
B. Leave CLI alone and continue workspace UX.
C. Create a clean branch/worktree from origin/main for CLI refactor.
```

## Phase 5: Encoding/Mojibake Cleanup

Verdict: normal.

Edge:
- Russian UX text becomes readable in source and terminal.

Risk:
- Touching many files creates noisy diffs and can hide behavior changes.

Simplify/drop:
- Clean only workspace-owned files first.
- Do not rewrite old docs or unrelated modules.

### Task 5.1: Check Workspace Files For Mojibake

**Files:**
- Read only first:
  - `twitter_content_machine/workspace_service.py`
  - `twitter_content_machine/workspace_view.py`
  - `twitter_content_machine/workspace_protocol.py`
  - `twitter_content_machine/workspace_tui.py`
  - `tests/test_workspace_service.py`

- [ ] **Step 1: Search obvious mojibake markers**

Run:

```powershell
rg -n "Р.|С.|вЂ|Рџ|Рљ|Рќ|Рњ|Рґ|Рµ" twitter_content_machine\workspace_service.py twitter_content_machine\workspace_view.py twitter_content_machine\workspace_protocol.py twitter_content_machine\workspace_tui.py tests\test_workspace_service.py
```

Expected:

```text
No matches in workspace-owned files after bc98c69 and protocol split.
```

- [ ] **Step 2: If matches exist, write targeted test**

Add to `tests/test_workspace_service.py`:

```python
def test_workspace_screen_has_no_mojibake_markers(tw_root: Path, tmp_path: Path) -> None:
    service = ContentWorkspaceService(cwd=tmp_path)

    screen = service.render_summary()

    for marker in ["Рџ", "Рљ", "Рќ", "СЃ", "вЂ"]:
        assert marker not in screen
```

- [ ] **Step 3: Fix only workspace-owned strings**

Replace mojibake strings in workspace-owned files with readable Russian or English. Prefer English in internal terminal UI unless the spec requires Russian summary sections.

- [ ] **Step 4: Verify**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_service.py
```

Expected:

```text
all workspace service tests pass
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add twitter_content_machine\workspace_service.py twitter_content_machine\workspace_view.py twitter_content_machine\workspace_protocol.py tests\test_workspace_service.py
git commit -m "chore: clean workspace ui text encoding"
```

## Phase 6: Full Verification And Push

### Task 6.1: Full Suite

**Files:**
- No edits.

- [ ] **Step 1: Run full tests**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q
```

Expected:

```text
87+ passed
```

- [ ] **Step 2: Run doctor**

Run:

```powershell
python -m twitter_content_machine doctor
```

Expected key line:

```text
safety: draft-only; no publish command is exposed
```

- [ ] **Step 3: Run no-Codex smoke**

Run:

```powershell
$smoke = Join-Path $env:TEMP ('tw-final-smoke-' + [guid]::NewGuid().ToString('N'))
$env:TWITTER_SYSTEM_ROOT=$smoke
@'
from pathlib import Path
from twitter_content_machine.workspace_service import ContentWorkspaceService
s = ContentWorkspaceService(cwd=Path.cwd())
print(s.render_summary())
s.handle('/draft final smoke idea')
s.handle('/continue')
print('---')
print(s.render_summary())
'@ | python -
```

Expected:

```text
First render shows empty workspace.
Second render shows Next action: /continue --run.
No KeyError.
No raw step_started spam.
```

- [ ] **Step 4: Check staged scope before every commit**

Run:

```powershell
git diff --cached --name-only
```

Expected:

```text
Only files named by the current task.
```

- [ ] **Step 5: Push after clean commits**

Run:

```powershell
git push origin main
```

Expected:

```text
main -> main
```

## Backlog After This Plan

Promote:
- Workspace UI split and view-model tests.
- Plain-text first input when no session exists.
- Encoding cleanup for workspace-owned files.

Defer:
- CLI parser refactor until dirty bootstrap/outcome changes are resolved.
- SQLite index for sessions/runs.
- `/edit`, `/review`, `/ready`, `/posted`, `/done` inside TUI.

Drop for now:
- More panels.
- Raw debug view as default screen.
- Browser/mouse automation.
- Any publish/post/X write path.

## Self-Review

Spec coverage:
- Covers current crash class: `Progress` vs `progress` section contract.
- Covers workspace module split.
- Covers author-facing UX tests.
- Covers dirty worktree risk.
- Covers full verification and safety checks.

Placeholder scan:
- No `TBD`.
- No unbounded “add error handling”.
- CLI refactor is explicitly gated instead of underspecified.

Type consistency:
- `split_screen` is the exported parser function.
- `WorkspaceApp.refresh_screen` is the Textual method.
- `render_workspace_screen`, `render_empty_workspace_screen`, and `render_session_without_run_screen` remain the view entrypoints.

Scope:
- This plan intentionally does not implement full `/edit`, `/review`, `/ready`, `/posted`, SQLite, or graph bootstrap cleanup.
