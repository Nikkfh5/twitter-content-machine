# Instruction File Quality Report

Session anchor:
- date: 2026-06-09
- repo: `C:\N\hse\twitter-content-machine`
- skill: `claude-md-improver`

## Summary

Files found:
- `AGENTS.md`
- `README.md`
- `.codex/css/*.md` session-state files

Files not found:
- `CLAUDE.md`
- `.claude.local.md`
- `.codex/rules`

Average score: 91/100.

Files needing updates:
- `AGENTS.md`: small currency update for the latest roadmap scoring/progress and repeated-post detector behavior.
- `README.md`: small roadmap pointer update.

## File-by-File Assessment

### `AGENTS.md`

Score: 92/100.

| Criterion | Score | Notes |
| --- | ---: | --- |
| Commands/workflows | 19/20 | Current daily commands are documented: `tw draft`, active draft UX, `tw edit`, `tw algo`, `tw codex`, `tw search --smart`, style commands. |
| Architecture clarity | 19/20 | Entrypoints and core modules are clear, including LLM/context, Codex sessions, X read, identity style, and algorithm review. |
| Project invariants | 20/20 | Draft-only, no X write APIs, no publish MCP tool, central workspace, no secrets-as-context are explicit. |
| Conciseness | 13/15 | Long, but mostly operational. No large generic coding advice. |
| Currency | 13/15 | Missing newest roadmap scoring/progress links and explicit repeated-post detector status. |
| Actionability | 9/10 | Good command examples and stop rules. |

Issues:
- Durable docs section does not yet include `docs/product-roadmap-scoring.md`.
- Durable docs section does not yet include `docs/superpowers/progress/2026-06-08-product-roadmap-progress.md`.
- Algorithm-aware review section does not explain the new status-aware repeated-post rule.
- It does not state the next roadmap priority after the repeated-post fix.

Recommended changes:
- Add roadmap scoring and latest product progress log to durable docs.
- Add current priority: adaptive format decision artifact.
- Add a concise repeated-post risk rule: captured ideas and ordinary drafts are not repetition; ready/posted/own posts are.

### `README.md`

Score: 89/100.

| Criterion | Score | Notes |
| --- | ---: | --- |
| Commands/workflows | 19/20 | Daily workflow and active draft UX are clear. |
| Architecture clarity | 17/20 | Explains workspace, draft artifacts, Codex sessions, memory, X read. |
| Project invariants | 19/20 | Draft-only/no publish is clear. |
| Conciseness | 13/15 | Long but useful for a user-facing README. |
| Currency | 13/15 | Product roadmap link exists; scoring link is not called out. |
| Actionability | 9/10 | Commands are directly runnable. |

Issues:
- Roadmap section points to top-level roadmap only; the scored priority file is easy to miss.

Recommended changes:
- Add `docs/product-roadmap-scoring.md` beside the roadmap pointer.

### `.codex/css/*.md`

Score: 85/100 as session-state artifacts, not project instructions.

Notes:
- These are useful handoff files and should remain short.
- They should not be treated as authoritative repo instructions.
- The current active CSS path is `.codex/css/20260609-173212-twitter-content-machine-roadmap.md`.

