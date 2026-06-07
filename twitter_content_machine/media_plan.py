from __future__ import annotations

from pathlib import Path

from .algorithm_review import write_media_plan


def create_media_plan(draft_id: str) -> Path:
    return write_media_plan(draft_id)

