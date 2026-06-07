from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from .utils import iso_now
from .workspace import ensure_workspace


GOLD_FILES = ("style_gold.md", "content_gold.md")


@dataclass(frozen=True)
class StyleGoldImportResult:
    profile_dir: Path
    imported: list[Path]
    report_path: Path


def import_style_content_gold(path: str | Path) -> StyleGoldImportResult:
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"style/content gold path not found: {source}")
    workspace = ensure_workspace()
    profile_dir = workspace.root / "profile"
    imported: list[Path] = []
    if source.is_dir():
        found = _find_gold_files_in_dir(source)
        for name, file_path in found.items():
            target = profile_dir / name
            target.write_text(file_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            imported.append(target)
    elif source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            names = {Path(name).name: name for name in zf.namelist() if Path(name).name in GOLD_FILES}
            missing = [name for name in GOLD_FILES if name not in names]
            if missing:
                raise ValueError(f"missing in zip: {', '.join(missing)}")
            for name in GOLD_FILES:
                target = profile_dir / name
                target.write_text(zf.read(names[name]).decode("utf-8", errors="replace"), encoding="utf-8")
                imported.append(target)
    else:
        raise ValueError("expected folder or .zip with style_gold.md and content_gold.md")

    missing_after = [name for name in GOLD_FILES if not (profile_dir / name).exists()]
    if missing_after:
        raise ValueError(f"missing gold files after import: {', '.join(missing_after)}")
    report_path = profile_dir / "style_content_gold_report.md"
    report_path.write_text(
        "# Style/Content Gold Import Report\n\n"
        f"- imported_at: {iso_now()}\n"
        f"- source: {source}\n"
        + "".join(f"- imported: {path.name}\n" for path in imported),
        encoding="utf-8",
    )
    return StyleGoldImportResult(profile_dir, imported, report_path)


def _find_gold_files_in_dir(source: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for file_path in source.rglob("*.md"):
        if file_path.name in GOLD_FILES and file_path.name not in found:
            found[file_path.name] = file_path
    missing = [name for name in GOLD_FILES if name not in found]
    if missing:
        raise ValueError(f"missing in folder: {', '.join(missing)}")
    return found
