from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import load_config
from .drafting import get_draft
from .llm import resolve_codex_command
from .state import resolve_active_draft_id
from .utils import get_now, short_hash, slugify
from .workspace import ensure_workspace, read_profile


@dataclass(frozen=True)
class CodexSessionResult:
    session_dir: Path
    command: list[str]
    ran: bool
    returncode: int | None


def prepare_codex_session(
    draft_id: str | None = None,
    source_file: str | Path | None = None,
    output_mode: str = "final-post",
    instruction: str = "",
    cwd: Path | None = None,
) -> CodexSessionResult:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    input_title, input_text, resolved_draft_id = _resolve_input(draft_id, source_file)
    now = get_now()
    slug_source = input_title or resolved_draft_id or "content-session"
    session_dir = workspace.root / "codex_sessions" / f"{now:%Y%m%d-%H%M%S}-{slugify(slug_source)[:60]}-{short_hash(slug_source, 6)}"
    session_dir.mkdir(parents=True, exist_ok=False)
    (session_dir / "output").mkdir()
    (session_dir / ".codex_home").mkdir()

    _write_agents(session_dir, config)
    (session_dir / "TASK.md").write_text(
        _task_text(output_mode, instruction, resolved_draft_id, source_file, cwd),
        encoding="utf-8",
    )
    (session_dir / "INPUT.md").write_text(input_text, encoding="utf-8")
    (session_dir / "CONTEXT_BUNDLE.md").write_text(_context_bundle(workspace.root, resolved_draft_id), encoding="utf-8")
    (session_dir / "OUTPUT_SCHEMA.md").write_text(_output_schema(output_mode), encoding="utf-8")
    (session_dir / "README.md").write_text(_readme_text(), encoding="utf-8")
    (workspace.root / "state" / "current_codex_session.txt").write_text(str(session_dir) + "\n", encoding="utf-8")

    command = _codex_command(config)
    return CodexSessionResult(session_dir=session_dir, command=command, ran=False, returncode=None)


def run_codex_session(session: CodexSessionResult) -> CodexSessionResult:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    resolved = resolve_codex_command(config.llm_codex_command)
    if not resolved:
        raise RuntimeError(f"{config.llm_codex_command} not found")
    env = os.environ.copy()
    if config.llm_codex_isolate_home:
        env["CODEX_HOME"] = str(session.session_dir / ".codex_home")
    completed = subprocess.run([resolved], cwd=session.session_dir, env=env, check=False)
    return CodexSessionResult(session.session_dir, [resolved], True, completed.returncode)


def _resolve_input(draft_id: str | None, source_file: str | Path | None) -> tuple[str, str, str | None]:
    if source_file:
        source = Path(source_file).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"source file not found: {source}")
        if source.name.lower().startswith(".env"):
            raise ValueError("refusing to use .env-like file as content input")
        return source.stem, _limit(source.read_text(encoding="utf-8", errors="replace"), 80_000), None
    resolved = resolve_active_draft_id(draft_id)
    draft = get_draft(resolved)
    folder = Path(draft["folder_path"])
    final = draft.get("final_text") or (folder / "06_final_candidate.md").read_text(encoding="utf-8", errors="replace")
    parts = [
        f"# Draft {resolved}",
        "",
        "## Final Candidate",
        final.strip(),
    ]
    for name in ["07_algorithm_review.md", "08_media_plan.md", "09_distribution_plan.md", "10_identity_style_review.md", "11_examples_used.md", "12_risk_flags.md"]:
        path = folder / name
        if path.exists():
            parts.extend(["", f"## {name}", _limit(path.read_text(encoding="utf-8", errors="replace"), 10_000)])
    return resolved, "\n".join(parts) + "\n", resolved


def _write_agents(session_dir: Path, config) -> None:
    agents = """# Content Codex Session

You are finalizing X/Twitter content for Nikita.

Hard rules:
- Draft/finalization only. Never publish.
- Never call X write APIs.
- Do not inspect parent repositories.
- Do not modify files outside this session folder.
- Use `INPUT.md`, `CONTEXT_BUNDLE.md`, `TASK.md`, and `OUTPUT_SCHEMA.md`.
- Write outputs only under `output/`.
- If something is missing, write the question or blocker into `output/notes.md`.

Style rules:
- Preserve concrete thinking, uncertainty, rough but readable rhythm.
- Do not imitate old crypto shilling or trading advice.
- Transfer structure from gold examples, not old market claims.
- Avoid influencer, LinkedIn, fake contrarian, and engagement-bait tone.
"""
    session_dir.joinpath("AGENTS.md").write_text(agents, encoding="utf-8")
    session_dir.joinpath(".codex_home", "AGENTS.md").write_text(agents, encoding="utf-8")
    session_dir.joinpath(".codex_home", "config.toml").write_text(
        f'model = "{config.llm_model}"\nreasoning_effort = "{config.llm_reasoning_effort}"\n',
        encoding="utf-8",
    )


def _task_text(output_mode: str, instruction: str, draft_id: str | None, source_file: str | Path | None, cwd: Path | None) -> str:
    return f"""# Task

Mode: {output_mode}
Draft id: {draft_id or ""}
Source file: {source_file or ""}
Invocation cwd: {cwd or ""}

User instruction:
{instruction or "Create final publish-ready candidates from the provided input. Keep draft-only safety."}

Goal:
- produce final text variants, not code
- preserve the real point
- make the result usable as a human-reviewed final candidate
- do not publish
"""


def _context_bundle(root: Path, draft_id: str | None) -> str:
    profile = read_profile(root)
    sections = ["# Context Bundle\n"]
    for name in ["persona", "style", "safety", "forbidden_phrases", "x_algorithm_principles", "x_fit_rubric", "style_gold", "content_gold"]:
        text = profile.get(name, "")
        if text:
            budget = 25_000 if name == "content_gold" else 15_000
            sections.append(f"## {name}\n{_limit(text, budget)}\n")
    if draft_id:
        sections.append(f"## active_draft\n{draft_id}\n")
    return "\n".join(sections)


def _output_schema(output_mode: str) -> str:
    if output_mode == "thread":
        return """# Output Schema

Write:
- `output/final_thread.md`
- `output/variants.md`
- `output/critique.md`
- `output/notes.md` if needed

The first post of the thread must stand alone. Each next post must add independent value.
"""
    return """# Output Schema

Write:
- `output/final_post.md`
- `output/variants.md`
- `output/critique.md`
- `output/notes.md` if needed

The final post must be concise, concrete, and safe for manual review.
"""


def _readme_text() -> str:
    return """# Codex Content Session

Run from this folder:

```powershell
codex
```

Read `TASK.md`, `INPUT.md`, `CONTEXT_BUNDLE.md`, and `OUTPUT_SCHEMA.md`.
Write final files under `output/`.
"""


def _codex_command(config) -> list[str]:
    resolved = resolve_codex_command(config.llm_codex_command) or config.llm_codex_command
    return [resolved]


def _limit(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[TRUNCATED: original {len(text)} chars, included {limit} chars]\n"
