"""Shared FilterInput widget — delegates ↑/↓ to sibling OptionList."""

from __future__ import annotations

from typing import Any

from textual.widgets import Input, OptionList


class FilterInput(Input):
    """Input that delegates ↑/↓ to a sibling OptionList.

    Args:
        list_id: ID of the OptionList to control.
        enter_selects: If True, Enter always selects from OptionList.
            If False (default), Enter only selects when input is empty,
            otherwise it submits the input text normally.
    """

    def __init__(
        self,
        *args: Any,
        list_id: str = "",
        enter_selects: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._list_id = list_id
        self._enter_selects = enter_selects

    def _get_option_list(self) -> OptionList | None:
        try:
            if self._list_id:
                return self.screen.query_one(f"#{self._list_id}", OptionList)
            lists = self.screen.query(OptionList)
            return lists.first() if lists else None
        except Exception:
            return None

    def on_key(self, event: Any) -> None:
        ol = self._get_option_list()
        if ol is None:
            return

        if event.key == "down":
            ol.action_cursor_down()
            event.prevent_default()
            event.stop()
        elif event.key == "up":
            ol.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            if self._enter_selects:
                # Always select from list (for command/file pickers)
                if ol.option_count > 0:
                    ol.action_select()
                event.prevent_default()
                event.stop()
            else:
                # Select from list only when input is empty (for model picker)
                if not self.value.strip() and ol.option_count > 0:
                    ol.action_select()
                    event.prevent_default()
                    event.stop()
                # Otherwise let Input.Submitted fire normally
