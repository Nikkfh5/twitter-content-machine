# Content Workspace TUI Design

Session anchor:
- date: 2026-06-10
- repo: `C:\N\hse\twitter-content-machine`
- base_commit: `9f78104`
- feature_id: `content-workspace-tui`

## Verdict

Idea strength: strong.

The product should not become "Codex for content" by reimplementing Codex. The
strong version is a Codex-native content production workspace:

```text
raw author intent
  -> session
  -> runs
  -> resumable steps
  -> Codex output protocol
  -> Russian interface summary
  -> next commands
```

The real edge is resumable content production. The user should be able to stop a
generation or close the UI, reopen `tw`, see the exact production state, and run
`/continue` without rebuilding everything from scratch.

## Product Shape

User-facing model:

```text
Content Workspace
  Session
    Runs
      Steps
      Events
      Artifacts
```

Internal product rule:

- `Session` is the author's working unit.
- `Run` is the resumability unit.
- `Step` is an executable production action.
- `Event` is a semantic log item for the interface.
- `Artifact` is durable output on disk.

The user should not have to think in run ids during normal use. The UI shows
sessions, summaries, problems, file paths, and next commands. Runs remain visible
through `/runs` for inspection and debugging.

## Scope

Build the first usable workspace, not the final operating system.

In scope for MVP:

- `tw` with no arguments opens the Textual workspace
- `tw work` exists as an explicit alias
- Textual is a core dependency
- TUI fallback: if Textual fails to start, show a clear error and CLI hints
- new session folder model for new workspace sessions
- run folders under sessions
- minimal run engine for draft generation
- `/draft <text>`
- `/continue`
- `/continue --run`
- `/status`
- `/runs`
- `/path`
- `/help`
- `/exit`
- live semantic event stream
- Codex output protocol
- interrupted session resume

Out of scope for MVP:

- full `/edit` flow inside TUI
- full `/review` flow inside TUI
- `/ready` and `/posted` as complete TUI flows
- SQLite session index
- RAG or embeddings
- cloud sync
- multi-user product behavior
- autoposting
- any X write API
- browser automation that clicks Post
- reimplementing Codex terminal UI, approvals, sandboxing, or model runtime

Target product direction after MVP:

- keep readable files as the source of human auditability
- add SQLite as an index for session/run/event state, search, resume, and
  cross-links
- keep Codex as runtime and `tw` as product/session/context layer

## Entry Points

CLI behavior:

```text
tw
  opens the Textual workspace

tw "raw idea or instruction"
  keeps the existing fast draft path

tw work
  explicit alias for opening the workspace
```

Existing commands must continue to work. The TUI must not replace the normal CLI
surface.

## Workspace UI

Main screen:

```text
Content Workspace

Session
  status: active | interrupted | done
  draft: <draft_id or none>
  path: <session path>

Codex Summary
  Kratko: ...
  Dlya kogo: ...
  Komu ne zaydet: ...
  Problemy: ...
  Kak ispravit: ...
  Osnovnye resheniya: ...
  Fayly: ...

Timeline
  10:21 session created
  10:21 run draft_generation created
  10:22 context ready
  10:22 waiting: /continue --run

Command
  /draft ...
```

Display text in the actual TUI should be polished Russian where it is meant for
the user. The ASCII text above is only a design sketch.

The default screen shows semantic production state, not raw stdout/stderr. Raw
logs are reserved for a later `/debug` view.

## Commands

MVP commands:

```text
/draft <text>
/continue
/continue --run
/status
/runs
/path
/help
/exit
```

Target commands after MVP:

```text
/edit <text>
/review
/ready
/posted --url <url>
/debug
```

Command rules:

- Commands use slash syntax.
- Plain text without a slash can later become a convenience input:
  - if no draft/session exists, treat as `/draft <text>`
  - if an active draft exists, treat as `/edit <text>`
- This plain-text convenience is not required for MVP.

## Continue Semantics

`/continue` reads session state and executes the next unfinished step.

Local steps run immediately.

Codex steps require explicit confirmation:

```text
/continue
  shows pending Codex step and suggested command

/continue --run
  runs Codex
```

Reason:

- Codex can take several minutes.
- The user should not accidentally start a long model run.
- Resume should remain explicit but low-friction.

The UI should present pending Codex work like:

```text
Next Codex run:
  action: generate final candidate
  reason: draft context and format decision are ready
  estimate: up to 10 min

Run:
  /continue --run
```

## Session Selection

When `tw` starts:

```text
if an interrupted or in_progress session exists:
  open it
else:
  open an empty workspace
```

Completed sessions must not reopen by default.

Old draft folders are not migrated and not mutated silently. The session layer
applies only to new workspace sessions.

## Session Lifecycle

User-facing states:

```text
active
interrupted
done
```

Internal states:

```text
idle
running
needs_user
failed
```

Done labels:

```text
/ready
  done: ready_for_manual_post

/posted
  done: manually_posted

/done
  done: archived_without_posting
```

`/ready`, `/posted`, and `/done` may remain target commands after MVP. The MVP
should design state so these labels fit later without migration.

## Storage

MVP storage:

```text
~/twitter-system/sessions/<session_id>/
  SESSION.md
  state.json
  timeline.md
  runs/
    <run_id>/
      run.json
      events.jsonl
      interface_summary.md
      interface_summary.json
      artifacts.json
```

Target product storage:

```text
SQLite + files
```

Files remain the human-readable audit trail. SQLite later becomes the index for
fast resume, search, state queries, and cross-links.

## Run Model

MVP run type:

```text
draft_generation
```

Suggested MVP steps:

```text
create_session
create_run
create_draft
write_context
write_format_decision
prepare_codex_contract
run_codex
load_output_protocol
mark_needs_user
```

Step state:

```json
{
  "id": "run_codex",
  "kind": "codex",
  "status": "pending",
  "requires_confirmation": true,
  "started_at": null,
  "finished_at": null,
  "artifacts": []
}
```

Valid step statuses:

```text
pending
running
done
failed
skipped
```

Resume rule:

```text
Never regenerate a completed artifact unless the step explicitly allows it.
```

This is the core anti-frustration requirement.

## Event Protocol

`tw` guarantees outer events. Codex may add optional semantic events.

Guaranteed events:

```text
session_created
run_created
step_started
step_finished
codex_started
codex_finished
summary_loaded
needs_user
failed
```

Optional Codex semantic events:

```text
draft_angle_found
audience_problem_found
rewrite_decision
risk_note
next_action
```

Event shape:

```json
{
  "ts": "2026-06-10T12:00:00+03:00",
  "source": "tw",
  "type": "step_finished",
  "message": "Format decision ready",
  "step_id": "write_format_decision",
  "severity": "info"
}
```

The TUI streams semantic events from `events.jsonl`. It should not depend on
Codex writing optional events. If Codex is silent, the UI still shows `tw`
events and remains useful.

## Codex Output Protocol

Codex is controlled through the session contract:

```text
AGENTS.md
TASK.md
OUTPUT_SCHEMA.md
```

Required v1 run artifacts:

```text
interface_summary.md
interface_summary.json
events.jsonl
artifacts.json
```

Ownership:

- `tw` creates and owns `events.jsonl`
- `tw` creates and owns `artifacts.json`
- Codex must write `interface_summary.md`
- Codex should write `interface_summary.json`
- Codex may append optional semantic events to `events.jsonl`
- Codex may add artifact claims, but `tw` validates paths before showing them

Optional later artifacts:

```text
decision_log.md
next_actions.json
```

### `interface_summary.md`

Human-readable Russian screen for the TUI.

Required sections:

```text
# Interface Summary

## Kratko
Russian text. What the draft is about.

## Dlya kogo
Russian text. Who benefits.

## Komu ne zaydet
Russian text. Why some audience will ignore it.

## Problemy
Russian text. 2-4 main weaknesses.

## Kak ispravit
Russian text. Concrete edits.

## Osnovnye resheniya
Russian text. Format, style, constraints, and choices.

## Fayly
Paths to draft/session/artifacts.

## Next Commands
Slash commands to continue.
```

The actual file content should use Russian headings in implementation. The
transliterated headings above keep this spec ASCII-safe.

### `interface_summary.json`

Machine-readable structure for the TUI.

Shape:

```json
{
  "language": "ru",
  "summary": "string",
  "audience": ["string"],
  "not_for": ["string"],
  "problems": ["string"],
  "fixes": ["string"],
  "decisions": [
    {
      "name": "format",
      "value": "build-log",
      "reason": "string"
    }
  ],
  "files": [
    {
      "label": "draft",
      "path": "C:/..."
    }
  ],
  "next_commands": [
    {
      "command": "/continue --run",
      "reason": "string"
    }
  ]
}
```

If Codex writes invalid JSON:

- the session must not crash
- `tw` appends a warning event
- TUI falls back to `interface_summary.md`
- `/continue` treats the output protocol as incomplete if needed

### `artifacts.json`

Purpose: make resume and UI state explicit without scraping Markdown.

Shape:

```json
{
  "created": [
    {
      "label": "final_candidate",
      "path": "C:/...",
      "required": true
    }
  ],
  "missing": [
    {
      "label": "interface_summary_json",
      "required": true
    }
  ]
}
```

## Codex Safety Contract

Generated session instructions must preserve these hard rules:

- draft only
- never publish
- no X write API
- no browser automation that clicks Post
- do not read `.env`, tokens, keys, credentials, or private logs
- do not modify source project files
- do not inspect parent repositories unless explicitly included as safe context
- source project `AGENTS.md` may be summarized as context but must not become
  active content-generation instruction

## Implementation Boundaries

Textual is the UI shell. It should not own business logic.

Suggested module boundaries:

```text
twitter_content_machine.workspace_tui
  Textual app, widgets, rendering, input dispatch

twitter_content_machine.sessions
  session creation, active session resolution, state load/save

twitter_content_machine.runs
  run creation, step state, event writing, resume logic

twitter_content_machine.output_protocol
  validate interface_summary.json, read Markdown fallback, artifacts.json

twitter_content_machine.codex_session
  existing Codex preparation/runtime helpers, extended only where needed
```

The TUI should call a small internal service API. It should not shell out to
`tw` for core commands, and it should not duplicate existing CLI handler logic.

## Error Handling

Expected failure modes:

- Textual import/start failure
- no active session
- interrupted Codex run
- Codex command missing
- Codex returns non-zero
- required output protocol file missing
- invalid `interface_summary.json`
- corrupted `state.json`

Behavior:

- write an event
- preserve existing artifacts
- show the next safe command
- never delete or regenerate completed files silently
- give a path the user can inspect

## Tests

Use the existing Windows-safe command:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q
```

Required unit coverage:

- create session folder and `state.json`
- create run folder and `run.json`
- append and read `events.jsonl`
- find interrupted/in-progress session
- do not reopen completed session by default
- resolve next unfinished step
- do not rerun completed artifact step
- validate `interface_summary.json`
- fallback when JSON is missing or invalid
- parse `artifacts.json`

Required CLI/workspace coverage:

- `tw` with no args reaches workspace entrypoint
- `/draft <text>` creates session and run
- `/continue` advances local steps
- `/continue` stops before Codex step
- `/continue --run` marks Codex step running/done/failed
- restarted workspace opens interrupted session
- `/path` returns session path
- `/runs` shows grouped run state

Required safety coverage:

- generated session instructions contain draft-only/no-publish rules
- no publish command or X write tool is added
- source project files are not modified by content Codex sessions

## Rollout Plan

Phase 1: file-backed session/run engine.

Phase 2: Textual workspace shell with read-only rendering plus `/help`,
`/status`, `/path`, `/runs`, `/exit`.

Phase 3: `/draft` creates a session/run and local artifacts.

Phase 4: `/continue` and `/continue --run` execute the MVP draft-generation run.

Phase 5: output protocol validation and Russian interface summary display.

Phase 6: interruption/resume tests and manual smoke test.

Do not begin SQLite indexing until the file-backed engine proves useful.

## Stop Conditions

Stop and ask for design review if:

- Textual forces major business-logic rewrites
- resume requires rewriting current draft generation end to end
- Codex output protocol proves unreliable without a validator/fallback
- the first implementation plan exceeds the narrow `/draft` plus `/continue`
  scenario

## Success Criteria

The MVP is successful when:

- `tw` opens a workspace
- `/draft <idea>` creates a new session and run
- local steps are visible as semantic events
- Codex steps require `/continue --run`
- after interruption, `tw` reopens the interrupted session
- completed artifacts are not regenerated
- the TUI shows a Russian Codex summary with problems, decisions, file paths,
  and next commands
- all existing CLI commands still work
- the full test suite passes
