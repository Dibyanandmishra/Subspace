"""Shared rich.Console singleton — all TUI output goes through this."""

from rich.console import Console

console = Console(
    highlight=False,  # We control all colors explicitly via markup
    markup=True,      # Enable [bold], [green], etc.
    emoji=True,       # Enable ⚡ ✓ ✗ ⚠ ◌ icons
    width=None,       # Auto-detect terminal width
)
