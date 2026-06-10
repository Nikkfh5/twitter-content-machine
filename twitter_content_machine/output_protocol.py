from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SummaryDecision:
    name: str
    value: str
    reason: str


@dataclass(frozen=True)
class SummaryFile:
    label: str
    path: str


@dataclass(frozen=True)
class SummaryCommand:
    command: str
    reason: str


@dataclass(frozen=True)
class InterfaceSummary:
    language: str
    summary: str
    audience: list[str]
    not_for: list[str]
    problems: list[str]
    fixes: list[str]
    decisions: list[SummaryDecision]
    files: list[SummaryFile]
    next_commands: list[SummaryCommand]


@dataclass(frozen=True)
class LoadedInterfaceSummary:
    data: InterfaceSummary | None
    markdown: str
    json_valid: bool
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ArtifactEntry:
    label: str
    path: str = ""
    required: bool = False


@dataclass(frozen=True)
class LoadedArtifacts:
    created: list[ArtifactEntry]
    missing: list[ArtifactEntry]
    warnings: list[str] = field(default_factory=list)


def load_interface_summary(run_path: Path) -> LoadedInterfaceSummary:
    warnings: list[str] = []
    markdown_path = run_path / "interface_summary.md"
    json_path = run_path / "interface_summary.json"
    markdown = markdown_path.read_text(encoding="utf-8", errors="replace") if markdown_path.exists() else ""
    if not json_path.exists():
        warnings.append("interface_summary.json is missing")
        return LoadedInterfaceSummary(None, markdown, False, warnings)
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return LoadedInterfaceSummary(_summary_from_json(data), markdown, True, warnings)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        warnings.append(f"invalid interface_summary.json: {exc}")
        return LoadedInterfaceSummary(None, markdown, False, warnings)


def load_artifacts(run_path: Path) -> LoadedArtifacts:
    path = run_path / "artifacts.json"
    if not path.exists():
        return LoadedArtifacts([], [], ["artifacts.json is missing"])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return LoadedArtifacts([], [], [f"invalid artifacts.json: {exc}"])
    return LoadedArtifacts(
        created=[_artifact_entry(item) for item in data.get("created", [])],
        missing=[_artifact_entry(item) for item in data.get("missing", [])],
        warnings=[],
    )


def _summary_from_json(data: dict[str, Any]) -> InterfaceSummary:
    return InterfaceSummary(
        language=str(data["language"]),
        summary=str(data["summary"]),
        audience=[str(item) for item in data.get("audience", [])],
        not_for=[str(item) for item in data.get("not_for", [])],
        problems=[str(item) for item in data.get("problems", [])],
        fixes=[str(item) for item in data.get("fixes", [])],
        decisions=[
            SummaryDecision(
                name=str(item["name"]),
                value=str(item["value"]),
                reason=str(item.get("reason", "")),
            )
            for item in data.get("decisions", [])
        ],
        files=[
            SummaryFile(
                label=str(item["label"]),
                path=str(item["path"]),
            )
            for item in data.get("files", [])
        ],
        next_commands=[
            SummaryCommand(
                command=str(item["command"]),
                reason=str(item.get("reason", "")),
            )
            for item in data.get("next_commands", [])
        ],
    )


def _artifact_entry(data: dict[str, Any]) -> ArtifactEntry:
    return ArtifactEntry(
        label=str(data["label"]),
        path=str(data.get("path", "")),
        required=bool(data.get("required", False)),
    )
