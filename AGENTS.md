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

Setup:
- `pip install -e .`
- Optional MCP support: `pip install -e ".[mcp]"`
- Initialize local workspace with `tw init` or `tw ensure`.

CLI workflow:
- Capture: `tw idea "<text>"`, `tw capture`
- Draft: `tw draft --short|--thread|--article-note|--build-log|--question "<text>"`
- Algorithm-aware draft: `tw draft --algo-aware --short "<text>"`
- Identity-style draft: `tw draft --identity-style tg_crypto_clean --identity-strength 0.35 --short "<text>"`
- Improve/check: `tw refine latest --pass human`, `tw review latest`
- X-fit review: `tw algo-review latest`, `tw media-plan latest`, `tw distribution-plan latest`
- Identity/style review: `tw style-review latest --profile tg_crypto_clean`
- Telegram import: `tw tg-import <result.json|folder|zip> --profile tg_crypto_clean`
- Style build/curation: `tw style-build tg_crypto_clean`, `tw style-curate tg_crypto_clean`
- Inspect: `tw queue`, `tw search "<query>"`, `tw open latest --print-path`
- Project context: `tw refresh-context --force`
- X/read-only: `tw x-read <user-or-url>`, `tw sync-posted`
- Status bookkeeping only: `tw mark-ready`, `tw reject`, `tw mark-posted --url <url>`
- `style-curate` currently writes a Markdown curation queue, not a full
  interactive labeling UI.

Draft artifacts:
- Draft folders live under `~/twitter-system/drafts/YYYY/MM/<draft_id>/`.
- Expected files: `00_raw_input.md`, `01_context_used.md`, `02_brief.md`,
  `03_variants.md`, `04_critique.md`, `05_selected.md`,
  `06_final_candidate.md`, `prompt_to_codex.md`, `meta.yaml`.
- Algorithm-aware commands append `07_algorithm_review.md`,
  `08_media_plan.md`, and `09_distribution_plan.md`.
- Identity-style commands append `10_identity_style_review.md`,
  `11_examples_used.md`, and `12_risk_flags.md`.
- Treat generation as workshop output: variants, critique, anti-GPT pass, final candidate.

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

Durable docs / resume:
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
  `$env:TWITTER_SYSTEM_ROOT='.tmp-twitter-system\identity-smoke'; python -m twitter_content_machine tg-import "C:\Users\v-353\Downloads\tg_identity_pack.zip" --profile tg_crypto_clean; python -m twitter_content_machine style-build tg_crypto_clean`
