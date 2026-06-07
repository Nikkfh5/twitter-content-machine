# Telegram Identity Style MVP

Session anchor:
- date: 2026-06-07
- repo: `C:\N\hse\twitter-content-machine`
- feature_id: `telegram-identity-style-layer`
- source_prompt: `C:\Users\v-353\Downloads\tg_identity_pack\codex_prompt_content_machine_with_identity_style.md`
- prepared_pack_folder: `C:\Users\v-353\Downloads\tg_identity_pack`
- prepared_pack_zip: `C:\Users\v-353\Downloads\tg_identity_pack.zip`
- raw_result_sample: `C:\Users\v-353\Downloads\AyuGram Desktop\ChatExport_2026-06-07\result.json`

## Goal

Implement the identity/style layer described in the prompt while preserving the
existing draft-only content machine.

This is not a voice clone. Use these terms:

- `identity_style`
- `style_corpus`
- `gold_examples`
- `anti_examples`
- `topic_memory`

## Scope

Implement now:

- SQLite tables for Telegram messages and identity/style profiles/examples.
- Workspace directories under `identity_styles/<profile>/`.
- `tw tg-import <path> --profile <name>` for `result.json`, folder, zip, and
  prepared cleaned package.
- `tw style-build <profile>` to create style cards and support files.
- `tw style-curate <profile>` as a safe non-blocking curation scaffold.
- `tw style-review <draft_id|latest> --profile <name>`.
- `tw draft --identity-style <profile> --identity-strength <float>`.
- `10_identity_style_review.md`, `11_examples_used.md`, `12_risk_flags.md`.
- MCP wrappers for import/build/review and algo review.

Postponed:

- Real interactive curation UI.
- X API read provider.
- Embeddings or graph memory.
- Autoposting: explicitly forbidden.

## Safety

- No command named `post`.
- No X write API.
- `mark-posted` remains local bookkeeping only.
- `forwarded_other` messages are stored as source/topic memory, not used as
  default identity/style examples.
- `private` and `reject` examples are never used for generation.
- Identity strength above `0.6` should create warnings in risk files.

## Verification Target

Expected commands:

```powershell
$env:TWITTER_SYSTEM_ROOT = ".tmp-twitter-system\identity-smoke"
python -m twitter_content_machine ensure
python -m twitter_content_machine tg-import "C:\Users\v-353\Downloads\tg_identity_pack.zip"
python -m twitter_content_machine style-build --auto
python -m twitter_content_machine draft --no-llm "I realized my backtest execution assumptions are fake"
python -m twitter_content_machine style-review latest
python -m twitter_content_machine mcp serve
```

`mcp serve` may exit with missing optional dependency, but fallback tool list
must include local wrappers and no publish tool.
