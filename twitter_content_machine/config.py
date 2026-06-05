from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG = """# Twitter Content Machine
default_language = "auto" # auto | en | ru
llm_mode = "manual" # manual | codex | openai-api
context_cache_minutes = 30

[x]
provider = "none" # none | x_api | mcp_external | manual
username = ""
readonly = true
"""


@dataclass(frozen=True)
class Config:
    root: Path
    default_language: str
    llm_mode: str
    context_cache_minutes: int
    x_provider: str
    x_username: str
    x_readonly: bool


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
    return Config(
        root=root,
        default_language=str(data.get("default_language", "auto")),
        llm_mode=str(data.get("llm_mode", "manual")),
        context_cache_minutes=int(data.get("context_cache_minutes", 30)),
        x_provider=str(x.get("provider", "none")),
        x_username=str(x.get("username", "")),
        x_readonly=bool(x.get("readonly", True)),
    )
