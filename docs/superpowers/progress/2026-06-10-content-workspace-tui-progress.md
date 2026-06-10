# Content Workspace TUI MVP Progress

Session anchor:
- date: 2026-06-10
- spec: `docs/superpowers/specs/2026-06-10-content-workspace-tui-design.md`
- feature_id: `content-workspace-tui`

## Implemented

- `tw` with no arguments now opens the workspace entrypoint.
- `tw work` is an explicit workspace alias.
- Textual is a core dependency in `pyproject.toml`.
- Added file-backed session storage under `~/twitter-system/sessions/<session_id>/`.
- Added run folders under each session with `run.json`, `events.jsonl`, protocol files, and artifacts manifest.
- Added MVP slash commands:
  - `/draft <text>`
  - `/continue`
  - `/continue --run`
  - `/status`
  - `/runs`
  - `/path`
  - `/help`
  - `/exit`
- Added resume behavior:
  - interrupted `running` sessions reopen as `interrupted/needs_user`
  - completed sessions are skipped by default
  - completed steps are not rerun
- Added Codex confirmation boundary:
  - `/continue` runs local steps and stops before `run_codex`
  - `/continue --run` executes the Codex step
- Added Russian interface summary protocol:
  - `interface_summary.md`
  - `interface_summary.json`
  - `artifacts.json`
- Added fallback protocol loading:
  - invalid/missing JSON does not crash summary loading
  - Markdown fallback is preserved
- Preserved draft-only safety in generated workspace Codex contract:
  - never publish
  - no X write APIs
  - no browser automation that clicks Post
  - no `.env`, tokens, keys, credentials, or private logs

## Main Files

- `twitter_content_machine/sessions.py`
- `twitter_content_machine/runs.py`
- `twitter_content_machine/output_protocol.py`
- `twitter_content_machine/workspace_service.py`
- `twitter_content_machine/workspace_tui.py`
- `twitter_content_machine/cli.py`
- `twitter_content_machine/workspace.py`
- `pyproject.toml`

## Tests Added

- `tests/test_workspace_sessions.py`
- `tests/test_workspace_runs.py`
- `tests/test_output_protocol.py`
- `tests/test_workspace_service.py`
- `tests/test_workspace_cli.py`

## Verification

Focused workspace tests:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\test_workspace_sessions.py tests\test_workspace_runs.py tests\test_output_protocol.py tests\test_workspace_service.py tests\test_workspace_cli.py
```

Result:

```text
16 passed
```

Full suite:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q
```

Result:

```text
72 passed
```

Runtime dependency:

```powershell
pip install -e .
python -c "import textual; print(textual.__version__)"
```

Result:

```text
8.2.7
```

Doctor:

```powershell
python -m twitter_content_machine doctor
```

Key result:

```text
safety: draft-only; no publish command is exposed
```

Smoke without Codex:

```text
/draft -> ok
/continue -> stops before Codex with /continue --run
/path -> shows session path
/runs -> shows grouped run state
```

Real Codex smoke in a temp `TWITTER_SYSTEM_ROOT`:

```text
/draft -> ok
/continue -> ok, Codex pending
/continue --run -> ok
interface_summary.md -> created
artifacts.json -> created
```

## Current State

MVP is implemented and verified. The next product step is polish, not core
enablement:

- richer Textual layout and event rendering
- `/debug` raw log view
- `/edit`, `/review`, `/ready`, `/posted`, `/done` workspace flows
- SQLite index over sessions/runs/events after file-backed model proves useful
