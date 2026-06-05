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
    "create virtual table if not exists ideas_fts using fts5(id, raw_text, tags)",
    "create virtual table if not exists drafts_fts using fts5(id, title, final_text, tags)",
    "create virtual table if not exists posts_fts using fts5(id, text, tags)",
    "create virtual table if not exists sources_fts using fts5(id, title, summary, raw_text, tags)",
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


def search_memory(query: str, limit: int = 10) -> list[dict[str, str]]:
    query = query.strip()
    if not query:
        return []
    results: list[dict[str, str]] = []
    with connect_db() as conn:
        searches = [
            ("idea", "ideas_fts", "raw_text"),
            ("draft", "drafts_fts", "final_text"),
            ("post", "posts_fts", "text"),
            ("source", "sources_fts", "summary"),
        ]
        for kind, table, column in searches:
            try:
                rows = conn.execute(
                    f"select id, {column} as text from {table} where {table} match ? limit ?",
                    (query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = conn.execute(
                    f"select id, {column} as text from {table} where {column} like ? limit ?",
                    (f"%{query}%", limit),
                ).fetchall()
            for row in rows:
                results.append({"type": kind, "id": row["id"], "text": row["text"] or ""})
    return results[:limit]


def latest_draft_id() -> str | None:
    with connect_db() as conn:
        row = conn.execute("select id from drafts order by created_at desc limit 1").fetchone()
    return row["id"] if row else None


def resolve_draft_id(value: str) -> str:
    if value == "latest":
        draft_id = latest_draft_id()
        if not draft_id:
            raise ValueError("No drafts found")
        return draft_id
    return value
