# LLM Context Bundle And X Read PR

Session anchor:
- date: 2026-06-07
- repo: `C:\N\hse\twitter-content-machine`
- feature_id: `llm-context-bundle-x-read`
- baseline_commit: `861cee2`

## User Direction

Implement the next architecture around:

```text
context bundle -> isolated generation workspace -> parse output -> review artifacts
```

The main correction:

- default model: `gpt-5.5`
- default reasoning effort: `xhigh`
- default speed: `fast`

These are config defaults and must stay overrideable.

## Non-Negotiables

- Draft-only.
- No X write API.
- No browser/computer automation for posting.
- No command named `post`.
- Codex content generation must not run from the source project as active
  instruction context.
- Source project `AGENTS.md` may be summarized in a context bundle, but must not
  become active content-generation instructions.
- Prefer isolated `CODEX_HOME=<draft_folder>/.codex_home`.

## Scope

Implement:

- `context_bundle.py`
- `generation_workspace.py`
- stronger `llm.py`
- `llm_parsing.py`
- stronger `x_read.py`
- `x_analysis.py`
- config `[llm]` and expanded `[x]`
- `tw draft --context-only`
- `tw draft --llm auto|manual|codex|openai-api`
- `tw draft --model`
- `tw draft --reasoning-effort`
- `tw draft --speed`
- `tw draft --require-llm`
- `tw draft --no-llm`
- `tw draft --print-prompt-path`
- `tw style-build --auto`
- `tw style-refresh`
- `tw style-stats`
- `tw x-read`
- `tw analyze-own`
- `tw analyze-peer`

Artifacts:

- `13_context_bundle.md`
- `13_context_bundle.json`
- `14_llm_request.md`
- `15_llm_raw_output.md` when LLM attempted
- `16_llm_parse_report.md`
- `AGENTS.override.md`
- `.codex_home/AGENTS.md`
- `.codex_home/config.toml`

## Acceptance Notes

Manual mode remains useful. If LLM is unavailable, fallback generation still
creates drafts and records parse/failure status.

X API support is read-only and testable by mocking HTTP. Missing credentials for
`sync-posted` should exit cleanly; explicit peer reads may return error code 1.

## Implemented In This Pass

- Config defaults: `model = "gpt-5.5"`, `reasoning_effort = "xhigh"`,
  `speed = "fast"`.
- Every draft creates context artifacts: `13_context_bundle.md`,
  `13_context_bundle.json`, `14_llm_request.md`, `16_llm_parse_report.md`,
  `AGENTS.override.md`, and isolated `.codex_home/`.
- `tw draft` supports `--llm`, `--model`, `--reasoning-effort`, `--speed`,
  `--require-llm`, `--no-llm`, `--context-only`, and `--print-prompt-path`.
- LLM parser handles raw JSON and fenced JSON; failures preserve fallback drafts.
- Auto identity selection is the fast path via `tw style-build <profile> --auto`,
  `tw style-refresh`, and `tw style-stats`.
- X API v2 read-only timeline import exists for own posts and peer/source posts.
- Project-aware memory search now prioritizes same-project memory in CLI/MCP.
- Repository README, `AGENTS.md`, and `skills/twitter-content/SKILL.md` were
  updated for the context-bundle architecture.

## Deferred / Future Work

- Codex adapter now parses `codex --help` / `codex exec --help` for core flags.
  A future hardening pass can add stdin-based prompt delivery and richer config
  override handling if the installed CLI supports it.
- OpenAI API mode is a clean fallback stub unless a real SDK/HTTP adapter is
  added and tested.
- X analysis is intentionally simple lexical summarization, not clustering.
- Article/source ingestion can still be deepened for claim extraction and
  project-specific test ideas.
