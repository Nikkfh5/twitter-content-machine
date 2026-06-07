from __future__ import annotations

from .x_read import summarize_posts_from_db


def analyze_own_posts() -> str:
    return summarize_posts_from_db()


def analyze_peer_posts(username_or_url: str) -> str:
    return summarize_posts_from_db(username_or_url)

