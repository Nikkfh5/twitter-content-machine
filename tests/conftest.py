from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def tw_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "twitter-system"
    monkeypatch.setenv("TWITTER_SYSTEM_ROOT", str(root))
    monkeypatch.setenv("TW_TEST_FIXED_NOW", "2026-06-06T21:30:45")
    return root
