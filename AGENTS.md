# Twitter Content Machine Agent Notes

This repo builds a local, terminal-first content machine for draft X/Twitter writing.

Hard rules:
- Draft only by default.
- Never publish to X/Twitter.
- Do not add browser automation that clicks Post.
- Do not expose a publish MCP tool.
- X integration is read-only in MVP.
- Do not read `.env`, tokens, keys, credentials, or private logs as content context.
- Store project context centrally under `~/twitter-system/projects/<project_id>/`.
- Do not write into the current project directory unless explicitly requested.

Architecture:
- CLI entrypoint: `tw`
- Python package: `twitter_content_machine`
- Central workspace: `~/twitter-system` or `TWITTER_SYSTEM_ROOT`
- Storage: SQLite + FTS5
- MCP server: `tw mcp serve`, local-memory tools only
- Codex skill: `skills/twitter-content/SKILL.md`

Useful checks:
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`
- `python -m twitter_content_machine doctor`
