from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import load_config
from .db import search_memory
from .llm import build_codex_invocation_plan, resolve_codex_command
from .project_context import detect_project
from .utils import get_now, short_hash
from .workspace import ensure_workspace


@dataclass(frozen=True)
class SmartSearchResult:
    output: str
    folder: Path


def run_smart_search(query: str, limit: int = 10, cwd: Path | None = None) -> SmartSearchResult | None:
    workspace = ensure_workspace()
    project = detect_project(cwd)
    candidates = search_memory(query, limit=max(limit * 3, 12), project_id=project.id, include_global=True)
    if not candidates:
        return None

    now = get_now()
    folder = workspace.root / "searches" / f"{now:%Y%m%d-%H%M%S}-{short_hash(query, 8)}"
    folder.mkdir(parents=True, exist_ok=False)
    (folder / ".codex_home").mkdir(exist_ok=True)
    (folder / ".codex_home" / "AGENTS.md").write_text(
        "# Smart Search Instructions\n\nRead-only search over provided memory candidates. Do not modify files. Do not publish.\n",
        encoding="utf-8",
    )

    candidates_md = _format_candidates(candidates)
    request = _build_request(query, candidates_md, limit)
    (folder / "01_candidates.md").write_text(candidates_md, encoding="utf-8")
    (folder / "02_codex_request.md").write_text(request, encoding="utf-8")

    config = load_config(workspace.root)
    if not resolve_codex_command(config.llm_codex_command):
        raise RuntimeError(f"{config.llm_codex_command} not found")
    plan = build_codex_invocation_plan(request, folder, config)
    if hasattr(plan.capabilities, "exec_available") and not plan.capabilities.exec_available:
        raise RuntimeError(f"{config.llm_codex_command} exec is not available")

    completed = subprocess.run(
        plan.command,
        cwd=plan.cwd,
        env=plan.env,
        text=True,
        capture_output=True,
        timeout=config.llm_codex_timeout_seconds,
        check=False,
    )
    raw = completed.stdout + ("\n\nSTDERR:\n" + completed.stderr if completed.stderr else "")
    (folder / "03_codex_raw_output.md").write_text(raw, encoding="utf-8")
    if completed.returncode != 0:
        (folder / "04_search_report.md").write_text(
            f"# Smart Search Report\n\n- ok: false\n- returncode: {completed.returncode}\n",
            encoding="utf-8",
        )
        raise RuntimeError("Codex smart search failed")
    (folder / "04_search_report.md").write_text("# Smart Search Report\n\n- ok: true\n", encoding="utf-8")
    return SmartSearchResult(raw.strip(), folder)


def _format_candidates(candidates: list[dict[str, str]]) -> str:
    parts = ["# Memory Candidates\n"]
    for index, item in enumerate(candidates, start=1):
        text = " ".join((item.get("text") or "").split())
        parts.append(
            f"## {index}. {item.get('type', item.get('kind', 'item'))}: {item.get('id', '')}\n"
            f"- project_id: {item.get('project_id', '')}\n"
            f"- source_role: {item.get('source_role', '')}\n"
            f"- reason: {item.get('reason', '')}\n\n"
            f"{text[:1200]}\n"
        )
    return "\n".join(parts)


def _build_request(query: str, candidates_md: str, limit: int) -> str:
    return f"""You are doing read-only smart search for a local X/Twitter draft workspace.

Query:
{query}

Rank the most useful candidates. Prefer exact conceptual match over keyword match.
Do not write posts. Do not imitate peer/source content. Do not publish.

Return a concise answer in Russian:
- best matches, with candidate id/kind
- why each match is useful
- where to look next if the query is underspecified

Show at most {limit} matches.

Candidates:
{candidates_md}
"""
