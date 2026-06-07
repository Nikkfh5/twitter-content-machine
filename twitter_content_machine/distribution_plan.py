from __future__ import annotations

from pathlib import Path

from .algorithm_review import write_distribution_plan


def create_distribution_plan(draft_id: str) -> Path:
    return write_distribution_plan(draft_id)

