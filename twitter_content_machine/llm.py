from __future__ import annotations

import shutil
import subprocess


def codex_available() -> bool:
    if not shutil.which("codex"):
        return False
    try:
        completed = subprocess.run(["codex", "--help"], text=True, capture_output=True, timeout=4, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def mode_description(mode: str) -> str:
    if mode == "codex":
        return "codex CLI requested; support is detected at runtime before use"
    if mode == "openai-api":
        return "OpenAI API requested; requires explicit environment/config"
    return "manual mode; prompt_to_codex.md is generated for paste/run workflow"
