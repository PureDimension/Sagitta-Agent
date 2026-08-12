"""Textual-based TUI for pydantic-deep CLI."""

__all__ = ["DeepApp"]


def __getattr__(name: str) -> object:
    if name == "DeepApp":
        from apps.cli.app import DeepApp

        return DeepApp
    raise AttributeError(name)
