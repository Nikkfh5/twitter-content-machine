from __future__ import annotations

import re
import urllib.request
from html.parser import HTMLParser

from .db import connect_db, upsert_fts
from .utils import iso_now, short_hash


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_skip = False
        self.parts: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.in_skip = True
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self.in_skip = False
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text or self.in_skip:
            return
        if self._in_title:
            self.title += text
        self.parts.append(text)


def fetch_article(url: str) -> dict[str, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "twitter-content-machine/0.1"})
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read(1_000_000).decode("utf-8", errors="replace")
    except Exception as exc:
        return {"url": url, "title": "", "raw_text": "", "summary": f"Fetch failed: {exc}"}
    parser = _TextExtractor()
    parser.feed(html)
    raw = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    summary = raw[:1000] + ("..." if len(raw) > 1000 else "")
    return {"url": url, "title": parser.title[:200], "raw_text": raw[:50_000], "summary": summary}


def store_article(url: str) -> str:
    article = fetch_article(url)
    source_id = f"source_{short_hash(url, 12)}"
    with connect_db() as conn:
        conn.execute(
            "insert or replace into sources(id, created_at, type, url, title, author, raw_text, summary, tags) values(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_id,
                iso_now(),
                "article",
                url,
                article["title"],
                "",
                article["raw_text"],
                article["summary"],
                "",
            ),
        )
        upsert_fts(conn, "sources_fts", (source_id, article["title"], article["summary"], article["raw_text"], ""))
    return source_id
