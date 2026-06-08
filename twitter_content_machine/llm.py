from __future__ import annotations

import shutil
import subprocess
import os
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .llm_parsing import ParsedLLMOutput, parse_llm_output


def resolve_codex_command(command: str = "codex") -> str | None:
    resolved = shutil.which(command)
    if not resolved:
        return None
    path = Path(resolved)
    if path.suffix.lower() in {".cmd", ".bat"}:
        native = (
            path.parent
            / "node_modules"
            / "@openai"
            / "codex"
            / "node_modules"
            / "@openai"
            / "codex-win32-x64"
            / "vendor"
            / "x86_64-pc-windows-msvc"
            / "bin"
            / "codex.exe"
        )
        if native.exists():
            return str(native)
    return resolved


def codex_available(command: str = "codex") -> bool:
    resolved = resolve_codex_command(command)
    if not resolved:
        return False
    try:
        completed = subprocess.run([resolved, "--help"], text=True, capture_output=True, timeout=4, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


@dataclass(frozen=True)
class CodexCapabilities:
    exec_available: bool
    supports_cd: bool
    supports_model: bool
    supports_config: bool
    supports_skip_git_repo_check: bool


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
    resolved = resolve_codex_command(command)
    if not resolved:
        return CodexCapabilities(False, False, False, False)
    top_code, top_help = _help_text([resolved, "--help"])
    exec_code, exec_help = _help_text([resolved, "exec", "--help"])
    combined = top_help + "\n" + exec_help
    exec_available = exec_code == 0 or "exec" in top_help
    return CodexCapabilities(
        exec_available=top_code == 0 and exec_available,
        supports_cd="--cd" in exec_help or "--cwd" in exec_help,
        supports_model="--model" in exec_help or " -m" in exec_help,
        supports_config="--config" in combined or " -c" in combined,
        supports_skip_git_repo_check="--skip-git-repo-check" in exec_help,
    )


def _capability(capabilities: CodexCapabilities | dict, canonical: str, legacy: str) -> bool:
    if isinstance(capabilities, dict):
        return bool(capabilities.get(canonical, capabilities.get(legacy, False)))
    return bool(getattr(capabilities, canonical))


def _isolated_codex_home_has_auth(codex_home: Path) -> bool:
    return (codex_home / "auth.json").exists() or (codex_home / "codex-auth.json").exists()


def build_codex_invocation_plan(request_text: str, draft_folder: Path, config: Config) -> CodexInvocationPlan:
    capabilities = detect_codex_capabilities(config.llm_codex_command)
    resolved = resolve_codex_command(config.llm_codex_command) or config.llm_codex_command
    env = os.environ.copy()
    isolated_home = draft_folder / ".codex_home"
    if config.llm_codex_isolate_home and _isolated_codex_home_has_auth(isolated_home):
        env["CODEX_HOME"] = str(isolated_home)
    command = [resolved, "exec"]
    supports_cd = _capability(capabilities, "supports_cd", "cd")
    supports_model = _capability(capabilities, "supports_model", "model")
    supports_skip_git_repo_check = _capability(capabilities, "supports_skip_git_repo_check", "skip_git_repo_check")
    if supports_cd:
        command.extend(["--cd", str(draft_folder)])
    if supports_skip_git_repo_check:
        command.append("--skip-git-repo-check")
    if supports_model:
        command.extend(["--model", config.llm_model])
    if _capability(capabilities, "supports_config", "config"):
        command.extend(["--config", f'model_reasoning_effort="{config.llm_reasoning_effort}"'])
        if config.llm_speed:
            command.extend(["--config", f'service_tier="{config.llm_speed}"'])
    command.append("-")
    return CodexInvocationPlan(command=command, cwd=draft_folder, env=env, capabilities=capabilities)


def resolve_llm_mode(requested: str | None, config: Config, no_llm: bool = False) -> str:
    if no_llm:
        return "manual"
    mode = requested or config.llm_mode
    if mode == "auto":
        return "codex"
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
    parsed = parse_llm_output("")
    return LLMRunResult(False, False, "", parsed, f"unknown llm mode: {mode}")


def _run_codex(request_path: Path, draft_folder: Path, config: Config, require_llm: bool) -> LLMRunResult:
    if not resolve_codex_command(config.llm_codex_command):
        parsed = parse_llm_output("")
        message = f"{config.llm_codex_command} not found"
        if require_llm:
            raise RuntimeError(message)
        return LLMRunResult(True, False, "", parsed, message)
    request_text = request_path.read_text(encoding="utf-8", errors="replace")
    plan = build_codex_invocation_plan(request_text, draft_folder, config)
    exec_available = _capability(plan.capabilities, "exec_available", "exec")
    if not exec_available:
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
            input=request_text,
            text=True,
            encoding="utf-8",
            errors="replace",
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
    if completed.returncode != 0:
        stderr = " ".join(completed.stderr.split()) if completed.stderr else ""
        message = f"codex exited with code {completed.returncode}"
        if stderr:
            message += f": {stderr[:500]}"
        parsed = ParsedLLMOutput(False, {}, f"Codex exited with code {completed.returncode}")
        if require_llm:
            raise RuntimeError(message)
        return LLMRunResult(True, False, raw, parsed, message)
    parsed = parse_llm_output(raw)
    ok = completed.returncode == 0 and parsed.ok
    if require_llm and not ok:
        raise RuntimeError(f"codex generation failed: {completed.returncode}; {parsed.error}")
    return LLMRunResult(True, ok, raw, parsed, "codex ok" if ok else f"codex failed: {parsed.error or completed.returncode}")


def mode_description(mode: str) -> str:
    if mode == "auto":
        return "auto mode; Codex CLI is required and no API fallback is used"
    if mode == "codex":
        return "codex CLI requested; support is detected at runtime before use"
    return "manual fallback is only used for --no-llm or --context-only"
