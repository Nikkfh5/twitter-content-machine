from __future__ import annotations

import shutil
import subprocess
import os
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .llm_parsing import ParsedLLMOutput, parse_llm_output


def codex_available(command: str = "codex") -> bool:
    if not shutil.which(command):
        return False
    try:
        completed = subprocess.run([command, "--help"], text=True, capture_output=True, timeout=4, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


@dataclass(frozen=True)
class CodexCapabilities:
    exec_available: bool
    supports_cd: bool
    supports_model: bool
    supports_config: bool


@dataclass(frozen=True)
class CodexInvocationPlan:
    command: list[str]
    cwd: Path
    env: dict[str, str]
    capabilities: CodexCapabilities


@dataclass(frozen=True)
class LLMRunResult:
    attempted: bool
    ok: bool
    raw_output: str
    parsed: ParsedLLMOutput
    message: str


def _help_text(command: list[str]) -> tuple[int, str]:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=4, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return completed.returncode, completed.stdout + "\n" + completed.stderr


def detect_codex_capabilities(command: str = "codex") -> CodexCapabilities:
    if not shutil.which(command):
        return CodexCapabilities(False, False, False, False)
    top_code, top_help = _help_text([command, "--help"])
    exec_code, exec_help = _help_text([command, "exec", "--help"])
    combined = top_help + "\n" + exec_help
    exec_available = exec_code == 0 or "exec" in top_help
    return CodexCapabilities(
        exec_available=top_code == 0 and exec_available,
        supports_cd="--cd" in exec_help or "--cwd" in exec_help,
        supports_model="--model" in exec_help or " -m" in exec_help,
        supports_config="--config" in combined or " -c" in combined,
    )


def build_codex_invocation_plan(request_text: str, draft_folder: Path, config: Config) -> CodexInvocationPlan:
    capabilities = detect_codex_capabilities(config.llm_codex_command)
    env = os.environ.copy()
    if config.llm_codex_isolate_home:
        env["CODEX_HOME"] = str(draft_folder / ".codex_home")
    command = [config.llm_codex_command, "exec"]
    if capabilities.supports_cd:
        command.extend(["--cd", str(draft_folder)])
    if capabilities.supports_model:
        command.extend(["--model", config.llm_model])
    command.append(request_text)
    return CodexInvocationPlan(command=command, cwd=draft_folder, env=env, capabilities=capabilities)


def resolve_llm_mode(requested: str | None, config: Config, no_llm: bool = False) -> str:
    if no_llm:
        return "manual"
    mode = requested or config.llm_mode
    if mode == "auto":
        if config.llm_mode != "manual":
            return config.llm_mode
        if codex_available(config.llm_codex_command):
            return "codex"
        return "manual"
    return mode


def run_llm(
    mode: str,
    request_path: Path,
    draft_folder: Path,
    config: Config,
    require_llm: bool = False,
) -> LLMRunResult:
    if mode == "manual":
        parsed = parse_llm_output("")
        return LLMRunResult(False, False, "", parsed, "manual mode; no LLM attempted")
    if mode == "codex":
        return _run_codex(request_path, draft_folder, config, require_llm)
    if mode == "openai-api":
        return _run_openai_api(request_path, config, require_llm)
    parsed = parse_llm_output("")
    return LLMRunResult(False, False, "", parsed, f"unknown llm mode: {mode}")


def _run_codex(request_path: Path, draft_folder: Path, config: Config, require_llm: bool) -> LLMRunResult:
    if not shutil.which(config.llm_codex_command):
        parsed = parse_llm_output("")
        message = f"{config.llm_codex_command} not found"
        if require_llm:
            raise RuntimeError(message)
        return LLMRunResult(True, False, "", parsed, message)
    request_text = request_path.read_text(encoding="utf-8", errors="replace")
    plan = build_codex_invocation_plan(request_text, draft_folder, config)
    if not plan.capabilities.exec_available:
        parsed = parse_llm_output("")
        message = f"{config.llm_codex_command} exec is not available"
        if require_llm:
            raise RuntimeError(message)
        return LLMRunResult(True, False, "", parsed, message)
    try:
        completed = subprocess.run(
            plan.command,
            cwd=plan.cwd,
            env=plan.env,
            text=True,
            capture_output=True,
            timeout=config.llm_codex_timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        parsed = parse_llm_output("")
        if require_llm:
            raise RuntimeError(str(exc)) from exc
        return LLMRunResult(True, False, "", parsed, str(exc))
    raw = completed.stdout + ("\n\nSTDERR:\n" + completed.stderr if completed.stderr else "")
    parsed = parse_llm_output(raw)
    ok = completed.returncode == 0 and parsed.ok
    if require_llm and not ok:
        raise RuntimeError(f"codex generation failed: {completed.returncode}; {parsed.error}")
    return LLMRunResult(True, ok, raw, parsed, "codex ok" if ok else f"codex failed: {parsed.error or completed.returncode}")


def _run_openai_api(request_path: Path, config: Config, require_llm: bool) -> LLMRunResult:
    if not os.environ.get("OPENAI_API_KEY"):
        parsed = parse_llm_output("")
        message = "OPENAI_API_KEY missing"
        if require_llm:
            raise RuntimeError(message)
        return LLMRunResult(True, False, "", parsed, message)
    parsed = parse_llm_output("")
    return LLMRunResult(True, False, "", parsed, "openai-api mode configured but SDK/HTTP adapter is not installed in MVP")


def mode_description(mode: str) -> str:
    if mode == "codex":
        return "codex CLI requested; support is detected at runtime before use"
    if mode == "openai-api":
        return "OpenAI API requested; requires explicit environment/config"
    return "manual mode; prompt_to_codex.md is generated for paste/run workflow"
