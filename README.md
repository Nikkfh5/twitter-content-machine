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
tw draft "today I realized my backtest execution model is fake"
tw draft --thread --url "https://example.com/article"
tw draft --build-log "cache key ignored branch and polluted results"
tw draft "today I misunderstood fills"
tw show
tw edit "make it shorter"
tw review
tw algo
tw ready
tw style-learn
tw drafts
tw use 2
tw path
tw search --smart "execution assumptions"
tw style-gold-import "C:\Users\v-353\Downloads\style_content_gold.zip"
tw codex --prepare --thread
tw codex --run
tw sync-posted
tw analyze-own --sync
```

`tw draft "..."` makes the new draft active. Most draft commands can omit
`draft_id` and operate on that active draft. `tw path` prints the active draft
folder without opening a GUI.

Default draft format is adaptive: short only when the idea is small, fuller
single-post drafts when the idea has enough context. Use `--short` only when
you explicitly want a compact post.

Debug-only draft flags such as `--llm`, `--model`, `--reasoning-effort`,
`--speed`, `--context-only`, and `--no-llm` still exist, but they are not part
of the daily workflow.

Russian CLI guide:

```text
docs/cli_descripsion_russion.md
```

Future style-learning backlog:

```text
docs/style-learning-from-posts-backlog.md
```

## Active Draft UX

The current draft pointer is stored centrally:

```text
~/twitter-system/state/current_draft.txt
```

Use one-draft-at-a-time commands:

```powershell
tw show
tw path
tw edit "make it less certain"
tw review
tw algo
tw ready
tw reject
tw posted --url "https://x.com/..."
```

Switch focus:

```powershell
tw drafts
tw use 2
tw use latest
```

Old explicit ids still work, for example `tw show latest` or
`tw algo-review <draft_id>`.

## Native Codex Content Sessions

Use this when you already have a prepared article note, draft, or thread input
and want to work inside a clean Codex folder with content-specific instructions:

```powershell
tw codex --prepare
tw codex --prepare --thread
tw codex --prepare --file "C:\path\article_notes.md" --thread
tw codex --run
```

This creates:

```text
~/twitter-system/codex_sessions/<session_id>/
  AGENTS.md
  TASK.md
  INPUT.md
  CONTEXT_BUNDLE.md
  OUTPUT_SCHEMA.md
  README.md
  output/
  .codex_home/AGENTS.md
  .codex_home/config.toml
```

The session `AGENTS.md` is for content finalization only. It is separate from
the repo `AGENTS.md`, so Codex does not confuse code instructions with writing
instructions. `tw codex --run` starts Codex from the session folder with isolated
`CODEX_HOME`.

The current session pointer is stored at:

```text
~/twitter-system/state/current_codex_session.txt
```

Import stronger style/content references:

```powershell
tw style-gold-import "C:\Users\v-353\Downloads\style_content_gold.zip"
```

This writes:

```text
~/twitter-system/profile/style_gold.md
~/twitter-system/profile/content_gold.md
~/twitter-system/profile/style_content_gold_report.md
```

## Workspace Layout

`tw ensure` creates the central workspace:

```text
~/twitter-system/
  profile/
  identity_styles/
  inbox/
  drafts/
  state/
  codex_sessions/
  projects/
  searches/
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
07_algorithm_review.md    # default, unless --no-algo-aware is used
08_media_plan.md          # default, unless --no-algo-aware is used
09_distribution_plan.md   # default, unless --no-algo-aware is used
10_identity_style_review.md # when tg_crypto_clean/default or --identity-style is active
11_examples_used.md         # when identity_style is active
12_risk_flags.md            # when identity_style is active
13_context_bundle.md
13_context_bundle.json
14_llm_request.md
15_llm_raw_output.md       # when an LLM is attempted
16_llm_parse_report.md
AGENTS.override.md
.codex_home/AGENTS.md     # when isolated Codex home is enabled
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

## LLM / Codex Generation

Every draft now gets an inspectable context bundle before any model call:

```text
source project cwd
  -> central project context
  -> related memory
  -> identity_style examples
  -> 13_context_bundle.md/json
  -> 14_llm_request.md
  -> draft-folder Codex generation
  -> parsed variants/final
```

Defaults in `config.toml`:

```toml
default_language = "en"

[llm]
mode = "auto"
model = "gpt-5.5"
reasoning_effort = "xhigh"
speed = "fast"
codex_isolate_home = true
codex_timeout_seconds = 600
codex_progress_interval_seconds = 15
```

Modes:

```powershell
tw draft "raw idea"
tw draft --no-llm "raw idea"
tw draft --llm codex --model gpt-5.5 --reasoning-effort xhigh --speed fast "raw idea"
tw draft --context-only --print-prompt-path "raw idea"
```

Critical behavior:

- `tw` may be launched from any project folder.
- Default content output is English. Russian or mixed-language input notes are
  translated/adapted into English draft text.
- While Codex is running, `tw draft` prints progress to stderr. Large projects
  can legitimately take several minutes while Codex reads context.
- Source project context is summarized into the bundle.
- Content generation runs from the draft folder, not from the source project.
- `AGENTS.md`, `AGENTS.override.md`, and `.codex_home/AGENTS.md` in the draft
  folder are content-generation instructions only.
- `CODEX_HOME` is isolated only when the draft-local `.codex_home` contains
  Codex auth; otherwise global Codex auth is reused while the active cwd and
  AGENTS instructions remain draft-local.
- Source project `AGENTS.md` may be summarized as context, but must not become active instructions for drafting.
- `tw draft "..."` requires Codex CLI; if Codex is missing or returns invalid output, the command fails after writing the report.
- `--no-llm` and `--context-only` are explicit local fallback/debug modes.

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
tw algo
```

Or generate all review artifacts at draft time:

```bash
tw draft "small build note from today's backtest"
```

The decision label `publish candidate` means "safe enough for a human to
consider manually posting". The tool still never publishes.

## Telegram Identity Style

Import the prepared Telegram identity/style package or a raw Telegram Desktop
`result.json`:

```powershell
tw tg-import "C:\Users\v-353\Downloads\tg_identity_pack.zip"
tw style-build --auto
tw style-refresh
tw style-stats
tw style-learn
tw style-curate
```

Known local inputs from the current setup:

```text
C:\Users\v-353\Downloads\tg_identity_pack.zip
C:\Users\v-353\Downloads\tg_identity_pack\
C:\Users\v-353\Downloads\AyuGram Desktop\ChatExport_2026-06-07\result.json
```

Use it while drafting:

```bash
tw draft "raw idea"
tw style-review
```

Rules:

- this is `identity_style`, not "voice"
- `forwarded_other` messages are stored as topic/source memory, not default style examples
- curated `private` and `reject` examples must never be used for generation
- identity strength above `0.6` is risky and should be manually reviewed
- `style-build --auto` is the default fast path; manual `style-curate` is optional
- `style-learn` updates the default style from approved own writing only:
  `ready`, `posted`, and local own posts. Rejected drafts, draft-only text,
  peer posts, external sources, and X-read material are excluded.

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
tw search --smart "backtest execution"
```

Plain `tw search` is lexical. `tw search --smart` gathers local memory
candidates and asks Codex CLI to rank/explain them in a read-only search folder
under `~/twitter-system/searches/`.

## X/Twitter Sync

Default config:

```toml
[x]
provider = "none"
readonly = true
```

`tw sync-posted` exits cleanly when disabled. MVP has no write/post command and no publish MCP tool.

Configure read-only X API import:

```toml
[x]
provider = "x_api"
user_id = "<your-user-id>"
readonly = true
max_import = 200
exclude_retweets = true
```

Environment:

```powershell
$env:X_BEARER_TOKEN = "<read-only bearer token>"
```

Commands:

```powershell
tw sync-posted
tw x-read @handle --limit 100
tw analyze-own --sync
tw analyze-peer @handle --limit 100
```

`sync-posted` imports own recent posts into local memory. `x-read` imports peer
posts as sources under `sources/x_posts/`; it does not treat them as user style.

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
python -m twitter_content_machine tg-import "C:\Users\v-353\Downloads\tg_identity_pack.zip"
python -m twitter_content_machine style-build --auto
python -m twitter_content_machine draft --no-llm "I realized my backtest execution assumptions are fake"
python -m twitter_content_machine style-review
python -m twitter_content_machine drafts --limit 1
```

Expected: no posting, dated draft folder, `07_*` through `16_*` review/context files,
and no publish MCP tool.
