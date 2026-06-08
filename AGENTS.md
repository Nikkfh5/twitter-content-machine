# Twitter Content Machine Agent Notes

This repo builds a local, terminal-first content machine for draft X/Twitter writing.

Hard rules:
- Draft only by default.
- Never publish to X/Twitter.
- Do not add any CLI command named `post` in MVP.
- Do not add browser automation that clicks Post.
- Do not expose a publish MCP tool.
- Do not call X write APIs.
- X integration is read-only in MVP.
- Do not read `.env`, tokens, keys, credentials, or private logs as content context.
- Store project context centrally under `~/twitter-system/projects/<project_id>/`.
- Do not write into the current project directory unless explicitly requested.

Architecture:
- CLI entrypoint: `tw`
- Python package: `twitter_content_machine`
- Console script target: `twitter_content_machine.cli:main`
- Central workspace: `~/twitter-system` or `TWITTER_SYSTEM_ROOT`
- Storage: SQLite + FTS5
- MCP server: `tw mcp serve`, local-memory tools only
- Codex skill: `skills/twitter-content/SKILL.md`
- Telegram identity/style layer: `twitter_content_machine/telegram_import.py`,
  `twitter_content_machine/identity_style.py`, `twitter_content_machine/security.py`
- Algorithm layer: `twitter_content_machine/algorithm_review.py`
- LLM/context layer: `twitter_content_machine/context_bundle.py`,
  `twitter_content_machine/generation_workspace.py`,
  `twitter_content_machine/llm.py`, `twitter_content_machine/llm_parsing.py`
- Native content Codex sessions: `twitter_content_machine/codex_session.py`
- X read/analysis layer: `twitter_content_machine/x_read.py`,
  `twitter_content_machine/x_analysis.py`

## Critical: two AGENTS contexts

This repository has two different instruction contexts.

1. Repository `AGENTS.md`
   - Used when Codex is modifying the `twitter-content-machine` codebase.
   - Contains engineering rules, tests, safety constraints, and architecture.

2. Generated draft `AGENTS.override.md`
   - Created inside each draft folder.
   - Used only when Codex is generating X/Twitter draft text.
   - Must be content-specific and draft-only.
   - Must not modify source project files.
   - Must not publish.
   - Must not call X write APIs.

When implementing or debugging LLM generation:
- `tw` may be invoked from any directory.
- `tw` should collect/summarize context from that directory.
- Codex content generation must run from the draft folder, not from the source
  project directory.
- Source project `AGENTS.md` may be summarized into `13_context_bundle.md/json`,
  but must not become active instruction for content generation.
- The draft folder always gets content-specific `AGENTS.md` /
  `AGENTS.override.md`; `CODEX_HOME=<draft_folder>/.codex_home` is used only
  when that isolated home has Codex auth, otherwise normal Codex auth is reused.

Setup:
- `pip install -e .`
- Optional MCP support: `pip install -e ".[mcp]"`
- Initialize local workspace with `tw init` or `tw ensure`.

CLI workflow:
- Capture: `tw idea "<text>"`, `tw capture`
- Draft: `tw draft "<text>"` uses Codex CLI, adaptive format, X-fit review, and default identity style when available.
- Default content output language is English. Russian or mixed-language raw
  ideas should be translated/adapted into English draft text.
- Format override: `tw draft --short|--thread|--article-note|--build-log|--question "<text>"`; adaptive is default.
- LLM/context flags such as `--llm`, `--model`, `--reasoning-effort`,
  `--speed`, `--no-llm`, and `--context-only` are debug/advanced, not daily UX.
- Identity-style override/debug: `tw draft --identity-style none "<text>"`
- Active draft UX: new drafts become current; `tw show`, `tw path`, `tw edit
  "<instruction>"`, `tw ready`, `tw reject`, and `tw algo` default to the
  current draft.
- Switch active draft: `tw drafts`, `tw use 2`, `tw use latest`
- Native content Codex session: `tw codex --prepare`, `tw codex --prepare
  --file <notes.md> --thread`, `tw codex --run`
- Import style/content gold references: `tw style-gold-import <zip|folder>`
- Improve/check: prefer `tw edit "<instruction>"`, `tw review`; `refine --pass`
  is legacy/debug.
- X-fit review: prefer `tw algo`; individual `tw algo-review`, `tw media-plan`,
  and `tw distribution-plan` are legacy/debug.
- Identity/style review: `tw style-review`
- Telegram import: `tw tg-import <result.json|folder|zip>`
- Style build/curation: `tw style-build --auto`, `tw style-refresh`,
  `tw style-stats`, `tw style-learn`, `tw style-curate`
- Inspect: prefer `tw drafts`, `tw search "<query>"`,
  `tw search --smart "<query>"`, `tw path`
- Project context: `tw refresh-context --force`
- X/read-only: `tw x-read <user-or-url>`, `tw sync-posted`
- X analysis: `tw analyze-own --sync`, `tw analyze-peer <user-or-url> --limit 100`
- Status bookkeeping only: prefer `tw ready`, `tw reject`,
  `tw posted --url <url>`; `mark-ready` and `mark-posted` are legacy aliases.
- `style-curate` currently writes a Markdown curation queue, not a full
  interactive labeling UI.
- Manual curation is optional. The fast path is `tw style-build --auto`;
  this creates `auto_gold`, `auto_neutral`, `auto_source_only`, and `auto_reject`
  labels.

Draft artifacts:
- Draft folders live under `~/twitter-system/drafts/YYYY/MM/<draft_id>/`.
- Expected files: `00_raw_input.md`, `01_context_used.md`, `02_brief.md`,
  `03_variants.md`, `04_critique.md`, `05_selected.md`,
  `06_final_candidate.md`, `prompt_to_codex.md`, `meta.yaml`.
- New LLM/context artifacts are expected on every draft:
  `13_context_bundle.md`, `13_context_bundle.json`, `14_llm_request.md`,
  `16_llm_parse_report.md`, `AGENTS.override.md`, and usually
  `.codex_home/AGENTS.md`; `15_llm_raw_output.md` appears when an LLM is
  attempted.
- Algorithm-aware commands append `07_algorithm_review.md`,
  `08_media_plan.md`, and `09_distribution_plan.md`.
- Identity-style commands append `10_identity_style_review.md`,
  `11_examples_used.md`, and `12_risk_flags.md`.
- Treat generation as workshop output: variants, critique, anti-GPT pass, final candidate.
- Default LLM config is `mode = "auto"`, `model = "gpt-5.5"`,
  `reasoning_effort = "xhigh"`, `speed = "fast"`, `default_language = "en"`.
  `tw draft` requires Codex
  CLI unless `--no-llm` or `--context-only` is used.
- Default Codex timeout is 600 seconds. `tw draft` emits progress to stderr
  while Codex is running so large-project context reads do not look frozen.
- Active draft state lives at `~/twitter-system/state/current_draft.txt`.
  This is only a pointer to the current draft id; it is not content memory.
- `tw edit` uses Codex CLI from the draft folder, writes
  `17_edit_request.md`, `18_edit_raw_output.md`, `19_edit_parse_report.md`,
  updates `06_final_candidate.md`, and stores a revision under `revisions/`.
- `tw search --smart` is read-only. It creates a folder under
  `~/twitter-system/searches/`, asks Codex CLI to rank/explain local memory
  candidates, and must not generate or publish posts.
- `tw codex` creates a separate content-writing session under
  `~/twitter-system/codex_sessions/<session_id>/` with its own content-only
  `AGENTS.md`, `.codex_home/AGENTS.md`, `TASK.md`, `INPUT.md`,
  `CONTEXT_BUNDLE.md`, `OUTPUT_SCHEMA.md`, and `output/`. This is the
  preferred native folder for manually running Codex on already prepared notes
  or drafts.
- `tw style-gold-import` copies `style_gold.md` and `content_gold.md` into
  `~/twitter-system/profile/`. Treat these as strong style/structure
  references, not as permission to reuse old crypto shilling or advice.

Project context behavior:
- `tw` detects the git root with `git rev-parse --show-toplevel`; fallback is cwd.
- Context files are written under `~/twitter-system/projects/<project_id>/`.
- Context refresh may read safe public files such as `README.md`, `AGENTS.md`,
  `PROJECT_CONTEXT.md`, `.twitter-context.md`, `.public-notes.md`, and `docs/*.md`.
- Secret-like content is redacted, but agents still must not use `.env`, tokens,
  keys, credentials, or private logs as context.

MCP tools:
- Exposed: `tw_algo_review`, `tw_create_draft`, `tw_get_draft`,
  `tw_get_project_context`, `tw_import_telegram`, `tw_list_drafts`,
  `tw_mark_posted`, `tw_mark_ready`, `tw_refine_draft`,
  `tw_refresh_project_context`, `tw_review_draft`, `tw_save_idea`,
  `tw_search_memory`, `tw_style_build`, `tw_style_curate`,
  `tw_style_review`, `tw_sync_posted_readonly`.
- `tw_mark_posted` is local status bookkeeping after a human manually posts.
- There must be no publish/post-to-X tool.

Algorithm-aware review:
- Treat X-fit as a heuristic review layer, not a real viral score or exact
  production-ranker model.
- Optimize for clear audience/topic fit, one or two likely positive actions,
  low negative feedback risk, format/media fit, and stable account positioning.
- Never recommend spam, fake controversy, financial advice, crypto shilling, or
  decorative media.
- Stage 2 ideas are documented in `docs/algorithm-aware/ideas-and-backlog.md`;
  do not silently discard them when working on this feature later.

Telegram identity/style:
- Use the term `identity_style`, not only `voice`.
- Prepared pack source is documented in `docs/identity-style-telegram-mvp.md`.
- Known local inputs:
  `C:\Users\v-353\Downloads\tg_identity_pack.zip`,
  `C:\Users\v-353\Downloads\tg_identity_pack\`,
  `C:\Users\v-353\Downloads\AyuGram Desktop\ChatExport_2026-06-07\result.json`.
- `forwarded_other` Telegram messages are source/topic memory, not default
  user-style examples.
- `private` and `reject` examples must never be used in generation.
- The layer preserves directness/rhythm/thinking patterns while adapting away
  old crypto-channel shilling, airdrops, price calls, and guru tone.
- Identity-style draft artifacts: `10_identity_style_review.md`,
  `11_examples_used.md`, `12_risk_flags.md`.
- Identity strength `>0.6` is risky; require manual review.
- Future backlog: let `tg_crypto_clean` learn from the user's own approved,
  manually posted, or ready drafts over time. Do not import rejected drafts,
  peer posts, source posts, or X-read external material as user style.
- Implemented default daily command: `tw style-learn`. It uses the single
  default style profile internally and learns only from approved own writing:
  `ready`, `posted`, and locally stored own posts.

Durable docs / resume:
- Russian CLI guide: `docs/cli_descripsion_russion.md`
- Style learning from future posts backlog:
  `docs/style-learning-from-posts-backlog.md`
- Algorithm backlog: `docs/algorithm-aware/ideas-and-backlog.md`
- Algorithm design/plan/progress:
  `docs/superpowers/specs/2026-06-06-algorithm-aware-review-layer-design.md`,
  `docs/superpowers/plans/2026-06-06-algorithm-aware-review-layer.md`,
  `docs/superpowers/progress/2026-06-06-algorithm-aware-review-layer-progress.md`
- Telegram identity MVP: `docs/identity-style-telegram-mvp.md`
- Telegram progress:
  `docs/superpowers/progress/2026-06-07-telegram-identity-style-progress.md`

Useful checks:
- `pip install -e .`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`
- PowerShell: `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q`
- `python -m twitter_content_machine doctor`
- `make test` and `make doctor` exist, but direct PowerShell commands are safer on Windows.
- For isolated smoke tests, prefer repo-local `.tmp-twitter-system` as
  `TWITTER_SYSTEM_ROOT`; `C:\tmp` may hit Windows permission issues here.
- Identity smoke:
  `$env:TWITTER_SYSTEM_ROOT='.tmp-twitter-system\identity-smoke'; python -m twitter_content_machine tg-import "C:\Users\v-353\Downloads\tg_identity_pack.zip"; python -m twitter_content_machine style-build --auto`
