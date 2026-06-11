from __future__ import annotations

from pathlib import Path


def run_workspace_app(cwd: Path | None = None) -> int:
    try:
        from .workspace_tui_app import WorkspaceApp
    except Exception as exc:
        print("Textual workspace failed to start.")
        print(f"error: {exc}")
        print("Hints:")
        print("- install dependencies: pip install -e .")
        print("- existing CLI still works: tw draft --no-llm \"idea\"")
        return 1

    WorkspaceApp(cwd=cwd).run()
    return 0
