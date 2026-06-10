from __future__ import annotations

import json
from pathlib import Path

from twitter_content_machine.output_protocol import load_artifacts, load_interface_summary


def test_validate_interface_summary_json(tw_root: Path) -> None:
    run_path = tw_root / "sessions" / "s" / "runs" / "r"
    run_path.mkdir(parents=True)
    (run_path / "interface_summary.json").write_text(
        json.dumps(
            {
                "language": "ru",
                "summary": "Черновик про баг.",
                "audience": ["инженеры"],
                "not_for": ["широкая аудитория"],
                "problems": ["мало конкретики"],
                "fixes": ["добавить пример"],
                "decisions": [{"name": "format", "value": "short", "reason": "одна мысль"}],
                "files": [{"label": "draft", "path": "C:/draft.md"}],
                "next_commands": [{"command": "/path", "reason": "открыть папку"}],
            }
        ),
        encoding="utf-8",
    )
    (run_path / "interface_summary.md").write_text("# Interface Summary\n\nfallback", encoding="utf-8")

    loaded = load_interface_summary(run_path)

    assert loaded.json_valid is True
    assert loaded.data is not None
    assert loaded.data.summary == "Черновик про баг."
    assert loaded.warnings == []


def test_interface_summary_falls_back_to_markdown_when_json_invalid(tw_root: Path) -> None:
    run_path = tw_root / "sessions" / "s" / "runs" / "r"
    run_path.mkdir(parents=True)
    (run_path / "interface_summary.json").write_text("{bad json", encoding="utf-8")
    (run_path / "interface_summary.md").write_text("# Summary\n\nMarkdown fallback", encoding="utf-8")

    loaded = load_interface_summary(run_path)

    assert loaded.json_valid is False
    assert loaded.data is None
    assert "Markdown fallback" in loaded.markdown
    assert loaded.warnings


def test_parse_artifacts_json(tw_root: Path) -> None:
    run_path = tw_root / "sessions" / "s" / "runs" / "r"
    run_path.mkdir(parents=True)
    (run_path / "artifacts.json").write_text(
        json.dumps(
            {
                "created": [{"label": "final_candidate", "path": "C:/final.md", "required": True}],
                "missing": [{"label": "interface_summary_json", "required": True}],
            }
        ),
        encoding="utf-8",
    )

    artifacts = load_artifacts(run_path)

    assert artifacts.created[0].label == "final_candidate"
    assert artifacts.missing[0].label == "interface_summary_json"
