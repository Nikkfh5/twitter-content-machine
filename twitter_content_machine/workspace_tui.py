from __future__ import annotations

from pathlib import Path

from .workspace_service import ContentWorkspaceService
from .workspace_tui_sections import split_screen


def run_workspace_app(cwd: Path | None = None) -> int:
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
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
            background: #0f1115;
        }
        #workspace {
            height: 1fr;
            padding: 1;
        }
        #left {
            width: 30%;
            min-width: 28;
        }
        #center {
            width: 1fr;
            min-width: 44;
        }
        #right {
            width: 32%;
            min-width: 34;
        }
        .column {
            height: 1fr;
        }
        .panel {
            border: solid #343b46;
            padding: 1 2;
            margin: 0 1 1 0;
            background: #151922;
            color: #d6dde8;
        }
        .panel-title {
            color: #9fb7d9;
            text-style: bold;
        }
        #state {
            height: 10;
        }
        #progress {
            height: 1fr;
        }
        #preview {
            height: 1fr;
            min-height: 14;
            border: heavy #4d7cfe;
            background: #10151f;
        }
        #summary {
            height: 11;
            overflow-y: auto;
        }
        #problems {
            height: 13;
        }
        #next {
            height: 9;
            border: heavy #d79a3b;
            background: #201a10;
        }
        #activity {
            height: 1fr;
        }
        #command {
            dock: bottom;
            margin: 0 1 0 1;
        }
        """
        BINDINGS = [("ctrl+c", "quit", "Exit")]

        def __init__(self, cwd: Path | None = None) -> None:
            super().__init__()
            self.service = ContentWorkspaceService(cwd=cwd)

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal(id="workspace"):
                with Vertical(id="left", classes="column"):
                    yield Static("", id="state", classes="panel")
                    yield Static("", id="progress", classes="panel")
                with Vertical(id="center", classes="column"):
                    yield Static("", id="preview", classes="panel")
                    yield Static("", id="summary", classes="panel")
                    yield Static("", id="problems", classes="panel")
                with Vertical(id="right", classes="column"):
                    yield Static("", id="next", classes="panel")
                    yield Static("", id="activity", classes="panel")
            yield Input(placeholder="/draft ...", id="command")
            yield Footer()

        def on_mount(self) -> None:
            self.title = "Content Workspace"
            self._refresh()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            result = self.service.handle(event.value)
            self._refresh(result.message)
            event.input.value = ""
            if result.exit_requested:
                self.exit()

        def _refresh(self, message: str = "") -> None:
            sections = split_screen(self.service.render_summary())
            self.query_one("#state", Static).update(_panel("Session", sections["state"]))
            self.query_one("#progress", Static).update(_panel("Progress", sections["progress"]))
            self.query_one("#preview", Static).update(_panel("Draft preview", sections["Draft preview"]))
            self.query_one("#summary", Static).update(_panel("Summary", sections["Summary"]))
            self.query_one("#problems", Static).update(_panel("Problems / Decisions", sections["Problems"] + "\n\n" + sections["Decisions"]))
            next_text = sections["next"]
            if message:
                next_text = message + "\n\n" + next_text
            self.query_one("#next", Static).update(_panel("Next action", next_text))
            self.query_one("#activity", Static).update(_panel("Activity / Files", sections["Recent activity"] + "\n\n" + sections["Files"]))

    WorkspaceApp(cwd=cwd).run()
    return 0


def _panel(title: str, body: str) -> str:
    body = body.strip() or "none"
    return f"{title}\n\n{body}"

