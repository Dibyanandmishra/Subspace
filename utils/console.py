"""Shared rich.Console singleton — all TUI output goes through this."""

import sys

# Force UTF-8 on Windows so emoji and Unicode box-drawing characters render correctly.
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from rich.console import Console

console = Console(
    highlight=False,  # We control all colors explicitly via markup
    markup=True,      # Enable [bold], [green], etc.
    emoji=True,       # Enable icons
    width=None,       # Auto-detect terminal width
)
