from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import default_root


SCHEMA = [
    """
    create table if not exists projects(
      id text primary key,
      name text,
      root_path text,
      created_at text,
      updated_at text,
      summary text,
      public_angle text
    )
    """,
    """
    create table if not exists ideas(
      id text primary key,
      created_at text,
      project_id text,
      raw_text text,
      source_url text,
      tags text,
      status text
    )
    """,
    """
    create table if not exists drafts(
      id text primary key,
      created_at text,
      updated_at text,
      project_id text,
      type text,
      status text,
      title text,
      folder_path text,
      source_idea_id text,
      selected_variant text,
      final_text text,
      tags text
    )
    """,
    """
    create table if not exists draft_revisions(
      id text primary key,
      draft_id text,
      created_at text,
      revision_number integer,
      text text,
      change_note text
    )
    """,
    """
    create table if not exists posts(
      id text primary key,
      created_at text,
      platform text,
      platform_post_id text,
      url text,
      text text,
      thread_id text,
      project_id text,
      source_draft_id text,
      tags text
    )
    """,
    """
    create table if not exists sources(
      id text primary key,
      created_at text,
      type text,
      url text,
      title text,
      author text,
      raw_text text,
      summary text,
      tags text
    )
    """,
    """
    create table if not exists telegram_messages(
      id text primary key,
      profile_name text,
      telegram_message_id text,
      date text,
      source_role text,
      forwarded_from text,
      author text,
      text_clean text,
      text_raw_hash text,
      length integer,
      reactions integer,
      has_photo integer,
      media_type text,
      risk_flags text,
      labels text,
      imported_at text
    )
    """,
    """
    create table if not exists identity_style_profiles(
      profile_name text primary key,
      created_at text,
      updated_at text,
      summary text,
      default_strength real,
      status text
    )
    """,
    """
    create table if not exists identity_style_examples(
      id text primary key,
      profile_name text,
      telegram_message_id text,
      label text,
      note text,
      created_at text
    )
    """,
    "create virtual table if not exists ideas_fts using fts5(id, raw_text, tags)",
    "create virtual table if not exists drafts_fts using fts5(id, title, final_text, tags)",
    "create virtual table if not exists posts_fts using fts5(id, text, tags)",
    "create virtual table if not exists sources_fts using fts5(id, title, summary, raw_text, tags)",
    "create virtual table if not exists telegram_messages_fts using fts5(id, profile_name, text_clean, labels)",
]


def db_path(root: Path | None = None) -> Path:
    root = root or default_root()
    return root / "db" / "content.sqlite"


def migrate(db_file: Path) -> None:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_file) as conn:
        conn.execute("pragma journal_mode=wal")
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()


@contextmanager
def connect_db(root: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path(root))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_fts(conn: sqlite3.Connection, table: str, values: tuple[str, ...]) -> None:
    placeholders = ",".join("?" for _ in values)
    conn.execute(f"delete from {table} where id = ?", (values[0],))
    conn.execute(f"insert into {table} values ({placeholders})", values)


def _matches(text: str, query: str) -> bool:
    lowered = text.lower()
    return all(part.lower() in lowered for part in query.split())


def search_memory(
    query: str,
    limit: int = 10,
    project_id: str | None = None,
    include_global: bool = True,
    kinds: list[str] | None = None,
) -> list[dict[str, str]]:
    query = query.strip()
    if not query:
        return []
    results: list[dict[str, str]] = []
    with connect_db() as conn:
        requested = set(kinds or ["idea", "draft", "post", "source", "telegram"])
        if "idea" in requested:
            rows = conn.execute("select id, project_id, raw_text from ideas").fetchall()
            for row in rows:
                text = row["raw_text"] or ""
                if _matches(text, query) and (include_global or not project_id or row["project_id"] == project_id):
                    results.append({"type": "idea", "kind": "idea", "id": row["id"], "project_id": row["project_id"] or "", "text": text, "reason": "lexical"})
        if "draft" in requested:
            rows = conn.execute("select id, project_id, final_text from drafts").fetchall()
            for row in rows:
                text = row["final_text"] or ""
                if _matches(text, query) and (include_global or not project_id or row["project_id"] == project_id):
                    results.append({"type": "draft", "kind": "draft", "id": row["id"], "project_id": row["project_id"] or "", "text": text, "reason": "lexical"})
        if "post" in requested:
            rows = conn.execute("select id, project_id, text from posts").fetchall()
            for row in rows:
                text = row["text"] or ""
                if _matches(text, query) and (include_global or not project_id or row["project_id"] == project_id):
                    results.append({"type": "post", "kind": "post", "id": row["id"], "project_id": row["project_id"] or "", "text": text, "reason": "lexical"})
        if "source" in requested:
            rows = conn.execute("select id, summary, raw_text, tags from sources").fetchall()
            for row in rows:
                text = row["summary"] or row["raw_text"] or ""
                if _matches(text, query):
                    results.append({"type": "source", "kind": "source", "id": row["id"], "project_id": "", "text": text, "reason": "lexical", "tags": row["tags"] or ""})
        if "telegram" in requested:
            rows = conn.execute("select id, profile_name, source_role, text_clean, risk_flags from telegram_messages").fetchall()
            for row in rows:
                text = row["text_clean"] or ""
                if _matches(text, query):
                    results.append({
                        "type": "telegram",
                        "kind": "telegram",
                        "id": row["id"],
                        "project_id": "",
                        "text": text,
                        "source_role": row["source_role"] or "",
                        "risk_flags": row["risk_flags"] or "",
                        "reason": "lexical",
                    })
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in results:
        key = item["id"] + (item.get("text") or "")[:80]
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    if project_id:
        deduped.sort(key=lambda item: 0 if item.get("project_id") == project_id else 1)
    return deduped[:limit]


def latest_draft_id() -> str | None:
    with connect_db() as conn:
        row = conn.execute("select id from drafts order by created_at desc, rowid desc limit 1").fetchone()
    return row["id"] if row else None


def resolve_draft_id(value: str) -> str:
    if value == "latest":
        draft_id = latest_draft_id()
        if not draft_id:
            raise ValueError("No drafts found")
        return draft_id
    return value
