from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path


SENSITIVE_NAME_RE = re.compile(
    r"(^|[._-])(env|secret|secrets|token|tokens|credential|credentials|key|keys|private|passwd|password)([._-]|$)",
    re.IGNORECASE,
)

BINARY_EXTENSIONS = {
    ".7z",
    ".bin",
    ".db",
    ".dll",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jpg",
    ".jpeg",
    ".mp4",
    ".parquet",
    ".pdf",
    ".png",
    ".pyc",
    ".sqlite",
    ".zip",
}

IGNORED_DIRS = {
    ".agents",
    ".codex",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tmp-twitter-system",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "twitter-system",
    "venv",
}


def get_now() -> datetime:
    fixed = os.environ.get("TW_TEST_FIXED_NOW")
    if fixed:
        return datetime.fromisoformat(fixed)
    return datetime.now().replace(microsecond=0)


def iso_now() -> str:
    return get_now().isoformat(timespec="seconds")


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "i",
    "me",
    "my",
    "of",
    "realize",
    "realized",
    "the",
    "today",
    "to",
    "fake",
}


def slugify(text: str, max_words: int = 5, max_length: int = 56) -> str:
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    filtered = [word for word in words if word not in STOPWORDS]
    slug = "-".join(filtered[:max_words] or words[:max_words]) or "draft"
    return slug[:max_length].strip("-") or "draft"


def short_hash(value: str, length: int = 6) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:length]


def safe_read_text(path: Path, limit: int = 20_000) -> str:
    try:
        if path.stat().st_size > limit:
            return path.read_text(encoding="utf-8", errors="replace")[:limit] + "\n[truncated]\n"
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def is_sensitive_path(path: Path) -> bool:
    return any(SENSITIVE_NAME_RE.search(part) for part in path.parts)


def should_ignore_path(path: Path) -> bool:
    if any(part in IGNORED_DIRS for part in path.parts):
        return True
    if is_sensitive_path(path):
        return True
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    return False


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip(" #\t")
        if stripped:
            return stripped
    return ""


def format_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- none"
