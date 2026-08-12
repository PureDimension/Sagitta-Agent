"""Compact context modal — /compact command."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class CompactModal(ModalScreen[tuple[str, str] | None]):
    """Options for compacting conversation context.

    Returns: ("llm", focus_text) or ("trim", "") or None if cancelled.
    """

    DEFAULT_CSS = """
    CompactModal {
        align: center middle;
    }
    CompactModal > #compact-container {
        width: 60;
        height: auto;
        border: tall $warning;
        background: $surface;
        padding: 1 2;
    }
    CompactModal > #compact-container > .compact-btn {
        margin: 1 0 0 0;
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="compact-container"):
            yield Static("[bold]Compact Context[/bold]\n")
            yield Static("Reduce context window usage by summarizing old messages.\n")
            yield Static("Focus (optional — what to prioritize in summary):")
            yield Input(placeholder="e.g. 'keep the test results'", id="focus-input")
            yield Button("Compact with LLM", variant="primary", id="btn-llm", classes="compact-btn")
            yield Button(
                "Quick trim (no LLM cost)", variant="default", id="btn-trim", classes="compact-btn"
            )
            yield Static("\n[dim]Esc cancel[/dim]")

    def on_mount(self) -> None:
        self.query_one("#focus-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        focus = self.query_one("#focus-input", Input).value.strip()
        if event.button.id == "btn-llm":
            self.dismiss(("llm", focus))
        elif event.button.id == "btn-trim":
            self.dismiss(("trim", ""))

    def action_cancel(self) -> None:
        self.dismiss(None)
