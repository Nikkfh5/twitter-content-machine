from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .db import connect_db, upsert_fts
from .security import risk_flags, sanitize_public_text
from .utils import iso_now, short_hash
from .workspace import ensure_workspace


PREPARED_FILES = {
    "telegram_messages_cleaned.jsonl": ("parsed", "telegram_messages_cleaned.jsonl"),
    "identity_style_card.md": ("", "identity_style_card.md"),
    "anti_patterns.md": ("", "anti_patterns.md"),
    "gold_candidates_for_manual_curation.md": ("curated", "gold_examples.md"),
    "telegram_cleanup_report.md": ("", "import_report.md"),
}


@dataclass(frozen=True)
class TelegramImportResult:
    profile_name: str
    profile_dir: Path
    imported: int
    own_original: int
    forwarded_other: int
    source_path: Path


def _profile_dir(profile_name: str) -> Path:
    workspace = ensure_workspace()
    profile_dir = workspace.root / "identity_styles" / profile_name
    for rel in ["raw", "parsed", "curated"]:
        (profile_dir / rel).mkdir(parents=True, exist_ok=True)
    for name in ["anti_examples.md", "rejected_examples.md", "private_examples.md"]:
        path = profile_dir / "curated" / name
        if not path.exists():
            path.write_text(f"# {name.removesuffix('.md').replace('_', ' ').title()}\n\n", encoding="utf-8")
    return profile_dir


def _normalize_telegram_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _reaction_count(message: dict[str, Any]) -> int:
    raw = message.get("reactions")
    if isinstance(raw, list):
        total = 0
        for item in raw:
            if isinstance(item, dict):
                total += int(item.get("count") or 0)
        return total
    if isinstance(raw, dict):
        return int(raw.get("count") or 0)
    return 0


def _classify(message: dict[str, Any], text_clean: str, own_names: set[str]) -> str:
    if message.get("type") != "message":
        return "service"
    if not text_clean:
        return "empty_or_media_only"
    forwarded_from = str(message.get("forwarded_from") or "")
    author = str(message.get("from") or "")
    if forwarded_from:
        if forwarded_from in own_names or forwarded_from == author:
            return "own_forwarded_self"
        return "forwarded_other"
    return "own_original"


def _row_from_raw_message(profile_name: str, message: dict[str, Any], own_names: set[str]) -> dict[str, Any]:
    raw_text = _normalize_telegram_text(message.get("text"))
    text_clean = sanitize_public_text(raw_text)
    source_role = _classify(message, text_clean, own_names)
    flags = risk_flags(text_clean, source_role)
    message_id = str(message.get("id", ""))
    media_type = str(message.get("media_type") or "") or None
    has_photo = 1 if message.get("photo") else 0
    return {
        "id": f"{profile_name}:{message_id}",
        "profile_name": profile_name,
        "telegram_message_id": message_id,
        "date": str(message.get("date") or ""),
        "source_role": source_role,
        "forwarded_from": str(message.get("forwarded_from") or ""),
        "author": str(message.get("from") or ""),
        "text_clean": text_clean,
        "text_raw_hash": short_hash(raw_text, 16),
        "length": len(text_clean),
        "reactions": _reaction_count(message),
        "has_photo": has_photo,
        "media_type": media_type or "",
        "risk_flags": json.dumps(flags, ensure_ascii=False),
        "labels": "",
        "imported_at": iso_now(),
    }


def _row_from_cleaned_json(profile_name: str, item: dict[str, Any]) -> dict[str, Any]:
    message_id = str(item.get("telegram_message_id") or item.get("id") or short_hash(json.dumps(item, ensure_ascii=False), 12))
    text_clean = str(item.get("text_clean") or "")
    source_role = str(item.get("source_role") or "own_original")
    flags = item.get("risk_flags")
    if not isinstance(flags, list):
        flags = risk_flags(text_clean, source_role)
    return {
        "id": f"{profile_name}:{message_id}",
        "profile_name": profile_name,
        "telegram_message_id": message_id,
        "date": str(item.get("date") or ""),
        "source_role": source_role,
        "forwarded_from": str(item.get("forwarded_from") or ""),
        "author": str(item.get("author") or ""),
        "text_clean": text_clean,
        "text_raw_hash": str(item.get("text_raw_hash") or short_hash(text_clean, 16)),
        "length": int(item.get("length") or len(text_clean)),
        "reactions": int(item.get("reactions") or 0),
        "has_photo": 1 if item.get("has_photo") else 0,
        "media_type": str(item.get("media_type") or ""),
        "risk_flags": json.dumps(flags, ensure_ascii=False),
        "labels": str(item.get("labels") or ""),
        "imported_at": iso_now(),
    }


def _insert_rows(rows: Iterable[dict[str, Any]]) -> tuple[int, int, int]:
    imported = 0
    own_original = 0
    forwarded_other = 0
    with connect_db() as conn:
        for row in rows:
            conn.execute(
                """
                insert or replace into telegram_messages(
                  id, profile_name, telegram_message_id, date, source_role,
                  forwarded_from, author, text_clean, text_raw_hash, length,
                  reactions, has_photo, media_type, risk_flags, labels, imported_at
                ) values(
                  :id, :profile_name, :telegram_message_id, :date, :source_role,
                  :forwarded_from, :author, :text_clean, :text_raw_hash, :length,
                  :reactions, :has_photo, :media_type, :risk_flags, :labels, :imported_at
                )
                """,
                row,
            )
            upsert_fts(conn, "telegram_messages_fts", (row["id"], row["profile_name"], row["text_clean"], row["labels"]))
            imported += 1
            own_original += 1 if row["source_role"] == "own_original" else 0
            forwarded_other += 1 if row["source_role"] == "forwarded_other" else 0
    return imported, own_original, forwarded_other


def _copy_prepared_file(profile_dir: Path, name: str, data: bytes) -> None:
    rel_dir, target_name = PREPARED_FILES[name]
    target_dir = profile_dir / rel_dir if rel_dir else profile_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / target_name).write_bytes(data)


def _copy_prepared_folder(source: Path, profile_dir: Path) -> Path | None:
    cleaned: Path | None = None
    for name in PREPARED_FILES:
        path = source / name
        if path.exists():
            data = path.read_bytes()
            _copy_prepared_file(profile_dir, name, data)
            if name == "telegram_messages_cleaned.jsonl":
                cleaned = profile_dir / "parsed" / "telegram_messages_cleaned.jsonl"
    return cleaned


def _copy_prepared_zip(source: Path, profile_dir: Path) -> Path | None:
    cleaned: Path | None = None
    with zipfile.ZipFile(source) as zf:
        for entry in zf.infolist():
            name = Path(entry.filename).name
            if name in PREPARED_FILES:
                _copy_prepared_file(profile_dir, name, zf.read(entry))
                if name == "telegram_messages_cleaned.jsonl":
                    cleaned = profile_dir / "parsed" / "telegram_messages_cleaned.jsonl"
    return cleaned


def _iter_cleaned_jsonl(path: Path, profile_name: str) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield _row_from_cleaned_json(profile_name, json.loads(line))


def _import_raw_result(path: Path, profile_name: str, profile_dir: Path, own_names: set[str]) -> TelegramImportResult:
    raw_target = profile_dir / "raw" / "result.json"
    shutil.copyfile(path, raw_target)
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    messages = data.get("messages", []) if isinstance(data, dict) else data
    rows = [_row_from_raw_message(profile_name, message, own_names) for message in messages if isinstance(message, dict)]
    parsed_path = profile_dir / "parsed" / "telegram_messages_cleaned.jsonl"
    with parsed_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(
                json.dumps(
                    {
                        "id": row["telegram_message_id"],
                        "date": row["date"],
                        "source_role": row["source_role"],
                        "forwarded_from": row["forwarded_from"],
                        "author": row["author"],
                        "length": row["length"],
                        "reactions": row["reactions"],
                        "has_photo": bool(row["has_photo"]),
                        "media_type": row["media_type"] or None,
                        "risk_flags": json.loads(row["risk_flags"]),
                        "text_clean": row["text_clean"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    imported, own_original, forwarded_other = _insert_rows(rows)
    _write_import_report(profile_dir, profile_name, imported, own_original, forwarded_other)
    return TelegramImportResult(profile_name, profile_dir, imported, own_original, forwarded_other, path)


def _write_import_report(profile_dir: Path, profile_name: str, imported: int, own_original: int, forwarded_other: int) -> None:
    report = profile_dir / "import_report.md"
    if report.exists() and report.stat().st_size > 0:
        existing = report.read_text(encoding="utf-8", errors="replace")
    else:
        existing = "# Telegram Import Report\n\n"
    report.write_text(
        existing.rstrip()
        + f"""

## Latest import

- profile: {profile_name}
- imported: {imported}
- own_original: {own_original}
- forwarded_other: {forwarded_other}
- imported_at: {iso_now()}
""",
        encoding="utf-8",
    )


def import_telegram(path: Path | str, profile_name: str = "tg_crypto_clean", own_name: str = "Nik Nik") -> TelegramImportResult:
    source = Path(path).expanduser().resolve()
    profile_dir = _profile_dir(profile_name)
    own_names = {own_name, "Nik Nik", ""}
    cleaned: Path | None = None
    if source.is_dir():
        cleaned = _copy_prepared_folder(source, profile_dir)
        raw = source / "result.json"
        if raw.exists():
            return _import_raw_result(raw, profile_name, profile_dir, own_names)
    elif source.suffix.lower() == ".zip":
        cleaned = _copy_prepared_zip(source, profile_dir)
    elif source.name == "result.json":
        return _import_raw_result(source, profile_name, profile_dir, own_names)
    elif source.suffix.lower() == ".jsonl":
        cleaned = profile_dir / "parsed" / "telegram_messages_cleaned.jsonl"
        shutil.copyfile(source, cleaned)
    if not cleaned or not cleaned.exists():
        raise ValueError(f"Telegram import source not recognized: {source}")
    rows = list(_iter_cleaned_jsonl(cleaned, profile_name))
    imported, own_original, forwarded_other = _insert_rows(rows)
    _write_import_report(profile_dir, profile_name, imported, own_original, forwarded_other)
    return TelegramImportResult(profile_name, profile_dir, imported, own_original, forwarded_other, source)

