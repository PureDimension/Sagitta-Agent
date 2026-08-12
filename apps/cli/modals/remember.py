"""Remember modal — /remember command."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class RememberModal(ModalScreen[str | None]):
    """Input modal for adding a note to persistent memory."""

    DEFAULT_CSS = """
    RememberModal {
        align: center middle;
    }
    RememberModal > #remember-container {
        width: 60;
        height: auto;
        border: tall $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, initial_text: str = "") -> None:
        super().__init__()
        self._initial_text = initial_text

    def compose(self) -> ComposeResult:
        with Vertical(id="remember-container"):
            yield Static("[bold]Remember[/bold]")
            yield Static("Add a note to your persistent memory (MEMORY.md):\n")
            yield Input(
                value=self._initial_text,
                placeholder="Type your note...",
                id="remember-input",
            )
            yield Static("\n[dim]Enter to save  ·  Esc to cancel[/dim]")

    def on_mount(self) -> None:
        self.query_one("#remember-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self.dismiss(text)
            self.app.notify("Saved to memory", severity="information")
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
