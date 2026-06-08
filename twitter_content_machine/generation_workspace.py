from __future__ import annotations

from pathlib import Path

from .config import Config


AGENTS_OVERRIDE = """# Draft Generation Instructions

You are generating draft X/Twitter content for Nikita.
Draft only. Never publish. Never call X write APIs.
Default output language is English. If input notes are Russian or mixed-language,
translate/adapt the meaning into English unless the request explicitly overrides
the language.

Use only the context files in this draft folder:
- 13_context_bundle.md
- 13_context_bundle.json
- 14_llm_request.md

Do not inspect parent source repositories unless explicitly asked.
Do not read secrets.
Do not modify source project files.
Do not create files outside this draft folder.

Generate structured output only according to the requested schema.
"""


def prepare_generation_workspace(draft_folder: Path, config: Config) -> None:
    (draft_folder / "AGENTS.override.md").write_text(AGENTS_OVERRIDE, encoding="utf-8")
    (draft_folder / "AGENTS.md").write_text(AGENTS_OVERRIDE, encoding="utf-8")
    codex_home = draft_folder / ".codex_home"
    codex_home.mkdir(exist_ok=True)
    (codex_home / "AGENTS.md").write_text(AGENTS_OVERRIDE, encoding="utf-8")
    (codex_home / "config.toml").write_text(
        f"""model = "{config.llm_model}"
model_reasoning_effort = "{config.llm_reasoning_effort}"
service_tier = "{config.llm_speed}"
""",
        encoding="utf-8",
    )
