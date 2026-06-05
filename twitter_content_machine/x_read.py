from __future__ import annotations

import os

from .config import load_config
from .models import SyncResult
from .workspace import ensure_workspace


class XReadProvider:
    def get_own_recent_posts(self) -> list[dict[str, str]]:
        return []

    def get_user_recent_posts(self, username: str, limit: int) -> list[dict[str, str]]:
        return []

    def get_post_thread(self, url_or_id: str) -> list[dict[str, str]]:
        return []


class NoneProvider(XReadProvider):
    pass


def get_provider() -> XReadProvider:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    if config.x_provider == "none":
        return NoneProvider()
    if config.x_provider == "x_api" and not os.environ.get("X_BEARER_TOKEN"):
        return NoneProvider()
    return NoneProvider()


def sync_posted() -> SyncResult:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    if config.x_provider == "none":
        return SyncResult(0, "read-only X sync is disabled. Set [x].provider in config.toml to enable imports.")
    if not config.x_readonly:
        return SyncResult(0, "Refusing X sync because readonly=false. MVP supports read-only imports only.")
    if config.x_provider == "x_api" and not os.environ.get("X_BEARER_TOKEN"):
        return SyncResult(0, "X API provider configured, but X_BEARER_TOKEN is missing. Nothing imported.")
    return SyncResult(0, "No read-only X provider implemented for this configuration yet. Nothing imported.")
