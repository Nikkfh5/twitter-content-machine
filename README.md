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

For tests or custom installs:

```bash
set TWITTER_SYSTEM_ROOT=C:\tmp\twitter-system
```

## Daily Use

```bash
tw idea "read an article about risk regimes; seems useful for thinking about backtests"
tw draft --short "today I realized my backtest execution model is fake"
tw draft --thread --url "https://example.com/article"
tw draft --build-log "cache key ignored branch and polluted results"
tw refine latest --pass human
tw review latest
tw queue
tw open latest
tw sync-posted
```

`tw open latest --print-path` prints the folder path without opening a GUI.

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

It stores projects, ideas, drafts, revisions, posts, and sources. FTS5 powers:

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

- `tw_search_memory`
- `tw_get_project_context`
- `tw_refresh_project_context`
- `tw_save_idea`
- `tw_create_draft`
- `tw_get_draft`
- `tw_list_drafts`
- `tw_refine_draft`
- `tw_review_draft`
- `tw_mark_ready`
- `tw_mark_posted`
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
