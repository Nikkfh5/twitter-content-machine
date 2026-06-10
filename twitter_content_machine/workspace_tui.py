from __future__ import annotations

from pathlib import Path

from .workspace_service import ContentWorkspaceService


def run_workspace_app(cwd: Path | None = None) -> int:
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Vertical
        from textual.widgets import Footer, Header, Input, Static
    except Exception as exc:
        print("Textual workspace failed to start.")
        print(f"error: {exc}")
        print("Hints:")
        print("- install dependencies: pip install -e .")
        print("- existing CLI still works: tw draft --no-llm \"idea\"")
        return 1

    class WorkspaceApp(App):
        CSS = """
        Screen {
            layout: vertical;
        }
        #body {
            height: 1fr;
            padding: 1 2;
        }
        #summary {
            height: 1fr;
            overflow-y: auto;
        }
        #command {
            dock: bottom;
        }
        """
        BINDINGS = [("ctrl+c", "quit", "Exit")]

        def __init__(self, cwd: Path | None = None) -> None:
            super().__init__()
            self.service = ContentWorkspaceService(cwd=cwd)

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Vertical(id="body"):
                yield Static(self.service.render_summary(), id="summary")
            yield Input(placeholder="/draft ...", id="command")
            yield Footer()

        def on_mount(self) -> None:
            self.title = "Content Workspace"

        def on_input_submitted(self, event: Input.Submitted) -> None:
            result = self.service.handle(event.value)
            summary = self.query_one("#summary", Static)
            summary.update(result.message + "\n\n" + self.service.render_summary())
            event.input.value = ""
            if result.exit_requested:
                self.exit()

    WorkspaceApp(cwd=cwd).run()
    return 0
