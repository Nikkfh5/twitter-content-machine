# Twitter Content Machine

Local terminal-first workflow for drafting X/Twitter posts. Draft-only MVP. It never publishes.

## Install

```bash
pip install -e .
tw init
tw doctor
```

Default workspace:

```text
~/twitter-system/
```

For tests or custom installs, prefer a repo-local ignored root on this Windows
setup:

```powershell
$env:TWITTER_SYSTEM_ROOT = ".tmp-twitter-system\smoke"
```

## Daily Use

```bash
tw idea "read an article about risk regimes; seems useful for thinking about backtests"
tw draft --short "today I realized my backtest execution model is fake"
tw draft --thread --url "https://example.com/article"
tw draft --build-log "cache key ignored branch and polluted results"
tw draft --short --identity-style tg_crypto_clean --identity-strength 0.35 "today I misunderstood fills"
tw refine latest --pass human
tw review latest
tw style-review latest --profile tg_crypto_clean
tw algo-review latest
tw media-plan latest
tw distribution-plan latest
tw queue
tw open latest
tw sync-posted
```

`tw open latest --print-path` prints the folder path without opening a GUI.

## Workspace Layout

`tw ensure` creates the central workspace:

```text
~/twitter-system/
  profile/
  identity_styles/
  inbox/
  drafts/
  projects/
  sources/
    articles/
    x_posts/
    telegram/
    notes/
  db/content.sqlite
  logs/
```

The current project directory is not written to by default. Project summaries
and Telegram identity/style corpora stay central.

## What A Draft Creates

Every draft gets a stable folder:

```text
~/twitter-system/drafts/YYYY/MM/YYYYMMDD-HHMMSS-slug-a1b2c3/
```

Files:

```text
00_raw_input.md
01_context_used.md
02_brief.md
03_variants.md
04_critique.md
05_selected.md
06_final_candidate.md
07_algorithm_review.md    # when --algo-aware or tw algo-review is used
08_media_plan.md          # when --algo-aware or tw media-plan is used
09_distribution_plan.md   # when --algo-aware or tw distribution-plan is used
10_identity_style_review.md # when --identity-style or tw style-review is used
11_examples_used.md         # when --identity-style is used
12_risk_flags.md            # when --identity-style is used
prompt_to_codex.md
meta.yaml
```

Generation is a workshop, not a fake polished final answer:

- Variant A: direct/raw
- Variant B: clearer/structured
- Variant C: sharper/more opinionated
- critique
- anti-GPT pass
- final candidate

## Algorithm-Aware Review

This layer is a local heuristic, not a claim about exact X production weights.
It optimizes for personalized recommendation fit:

- clear audience / topic cluster
- likely positive action
- low negative feedback risk
- good format and media choice
- consistency with the account direction

Run after creating a draft:

```bash
tw algo-review latest
tw media-plan latest
tw distribution-plan latest
```

Or generate all review artifacts at draft time:

```bash
tw draft --algo-aware --short "small build note from today's backtest"
```

The decision label `publish candidate` means "safe enough for a human to
consider manually posting". The tool still never publishes.

## Telegram Identity Style

Import the prepared Telegram identity/style package or a raw Telegram Desktop
`result.json`:

```powershell
tw tg-import "C:\Users\v-353\Downloads\tg_identity_pack.zip" --profile tg_crypto_clean
tw style-build tg_crypto_clean
tw style-curate tg_crypto_clean
```

Known local inputs from the current setup:

```text
C:\Users\v-353\Downloads\tg_identity_pack.zip
C:\Users\v-353\Downloads\tg_identity_pack\
C:\Users\v-353\Downloads\AyuGram Desktop\ChatExport_2026-06-07\result.json
```

Use it while drafting:

```bash
tw draft --short --algo-aware --identity-style tg_crypto_clean --identity-strength 0.35 "raw idea"
tw style-review latest --profile tg_crypto_clean
```

Rules:

- this is `identity_style`, not "voice"
- `forwarded_other` messages are stored as topic/source memory, not default style examples
- curated `private` and `reject` examples must never be used for generation
- identity strength above `0.6` is risky and should be manually reviewed
- `style-curate` currently creates a Markdown curation queue; it is not a full
  interactive labeling UI yet

## Project Context

Run `tw` from any project directory. It detects:

1. `git rev-parse --show-toplevel`
2. otherwise current working directory

It stores summaries centrally:

```text
~/twitter-system/projects/<project_id>/context.md
~/twitter-system/projects/<project_id>/recent_changes.md
~/twitter-system/projects/<project_id>/public_angle.md
~/twitter-system/projects/<project_id>/cache_meta.yaml
```

It does not write into the project directory by default.

Ignored as context:

- `.git/`
- `.env*`
- secrets, keys, credentials, tokens
- `node_modules`, `venv`, `.venv`
- build artifacts
- binary/large data files
- private logs

Refresh manually:

```bash
tw refresh-context --force
```

## Memory

SQLite lives at:

```text
~/twitter-system/db/content.sqlite
```

It stores projects, ideas, drafts, revisions, posts, sources, Telegram messages,
and identity/style profile metadata. FTS5 powers:

```bash
tw search "backtest execution"
```

## X/Twitter Sync

Default config:

```toml
[x]
provider = "none"
readonly = true
```

`tw sync-posted` exits cleanly when disabled. MVP has no write/post command and no publish MCP tool.

## MCP

Run:

```bash
tw mcp serve
```

Tools exposed:

- `tw_algo_review`
- `tw_create_draft`
- `tw_search_memory`
- `tw_get_project_context`
- `tw_refresh_project_context`
- `tw_save_idea`
- `tw_get_draft`
- `tw_import_telegram`
- `tw_list_drafts`
- `tw_mark_posted`
- `tw_mark_ready`
- `tw_refine_draft`
- `tw_review_draft`
- `tw_style_build`
- `tw_style_curate`
- `tw_style_review`
- `tw_sync_posted_readonly`

No publish tool is exposed.

Install optional MCP dependency if needed:

```bash
pip install -e ".[mcp]"
```

## Codex Skill

Skill source:

```text
skills/twitter-content/SKILL.md
```

Install by copying or symlinking this directory into your Codex skills folder:

```powershell
Copy-Item -Recurse .\skills\twitter-content "$env:USERPROFILE\.codex\skills\twitter-content"
```

Then invoke:

```text
$twitter-content
```

or:

```text
Use the twitter-content skill to turn this project update into a short post and a thread.
```

## Tests

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
```

On Windows PowerShell:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q
```

## Smoke Test

```powershell
$env:TWITTER_SYSTEM_ROOT = ".tmp-twitter-system\identity-smoke"
python -m twitter_content_machine ensure
python -m twitter_content_machine tg-import "C:\Users\v-353\Downloads\tg_identity_pack.zip" --profile tg_crypto_clean
python -m twitter_content_machine style-build tg_crypto_clean
python -m twitter_content_machine draft --short --algo-aware --identity-style tg_crypto_clean --identity-strength 0.35 "I realized my backtest execution assumptions are fake"
python -m twitter_content_machine style-review latest --profile tg_crypto_clean
python -m twitter_content_machine queue --limit 1
```

Expected: no posting, dated draft folder, `07_*` through `12_*` review files,
and no publish MCP tool.
