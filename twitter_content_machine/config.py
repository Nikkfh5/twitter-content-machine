from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG = """# Twitter Content Machine
default_language = "auto" # auto | en | ru
context_cache_minutes = 30

[llm]
mode = "auto" # auto | codex
model = "gpt-5.5"
reasoning_effort = "xhigh" # low | medium | high | xhigh
speed = "fast"
temperature = 0.7
max_context_chars = 120000
max_memory_items = 12
max_telegram_examples = 8
max_project_context_chars = 30000
max_source_chars = 20000
codex_isolate_home = true
codex_home_mode = "draft" # draft | default
codex_command = "codex"
codex_timeout_seconds = 180

[x]
provider = "none" # none | x_api | manual
username = ""
user_id = ""
readonly = true
max_import = 200
exclude_replies = false
exclude_retweets = true
"""


@dataclass(frozen=True)
class Config:
    root: Path
    default_language: str
    llm_mode: str
    llm_model: str
    llm_reasoning_effort: str
    llm_speed: str
    llm_temperature: float
    llm_max_context_chars: int
    llm_max_memory_items: int
    llm_max_telegram_examples: int
    llm_max_project_context_chars: int
    llm_max_source_chars: int
    llm_codex_isolate_home: bool
    llm_codex_home_mode: str
    llm_codex_command: str
    llm_codex_timeout_seconds: int
    context_cache_minutes: int
    x_provider: str
    x_username: str
    x_user_id: str
    x_readonly: bool
    x_max_import: int
    x_exclude_replies: bool
    x_exclude_retweets: bool


def default_root() -> Path:
    override = os.environ.get("TWITTER_SYSTEM_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / "twitter-system").resolve()


def load_config(root: Path | None = None) -> Config:
    root = (root or default_root()).expanduser().resolve()
    path = root / "config.toml"
    data: dict = {}
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    x = data.get("x", {})
    llm = data.get("llm", {})
    legacy_mode = data.get("llm_mode", "auto")
    raw_llm_mode = str(llm.get("mode", legacy_mode))
    llm_mode = raw_llm_mode if raw_llm_mode in {"auto", "codex"} else "auto"
    return Config(
        root=root,
        default_language=str(data.get("default_language", "auto")),
        llm_mode=llm_mode,
        llm_model=str(llm.get("model", os.environ.get("OPENAI_MODEL", "gpt-5.5"))),
        llm_reasoning_effort=str(llm.get("reasoning_effort", os.environ.get("OPENAI_REASONING_EFFORT", "xhigh"))),
        llm_speed=str(llm.get("speed", "fast")),
        llm_temperature=float(llm.get("temperature", 0.7)),
        llm_max_context_chars=int(llm.get("max_context_chars", 120000)),
        llm_max_memory_items=int(llm.get("max_memory_items", 12)),
        llm_max_telegram_examples=int(llm.get("max_telegram_examples", 8)),
        llm_max_project_context_chars=int(llm.get("max_project_context_chars", 30000)),
        llm_max_source_chars=int(llm.get("max_source_chars", 20000)),
        llm_codex_isolate_home=bool(llm.get("codex_isolate_home", True)),
        llm_codex_home_mode=str(llm.get("codex_home_mode", "draft")),
        llm_codex_command=str(llm.get("codex_command", "codex")),
        llm_codex_timeout_seconds=int(llm.get("codex_timeout_seconds", 180)),
        context_cache_minutes=int(data.get("context_cache_minutes", 30)),
        x_provider=str(x.get("provider", "none")),
        x_username=str(x.get("username", os.environ.get("X_USERNAME", ""))),
        x_user_id=str(x.get("user_id", os.environ.get("X_USER_ID", ""))),
        x_readonly=bool(x.get("readonly", True)),
        x_max_import=int(x.get("max_import", 200)),
        x_exclude_replies=bool(x.get("exclude_replies", False)),
        x_exclude_retweets=bool(x.get("exclude_retweets", True)),
    )
