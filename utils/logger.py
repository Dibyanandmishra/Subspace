"""Structured stage-prefixed logger — writes to console and logs/ directory."""

import logging
from datetime import datetime
from pathlib import Path

from rich.logging import RichHandler

from utils.console import console


def setup_logging(verbose: bool = False) -> None:
    """Configure root logger. Call once at startup from main.py."""
    level = logging.DEBUG if verbose else logging.INFO

    Path("logs").mkdir(exist_ok=True)
    log_file = Path("logs") / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # Rich console handler — pretty output, respects verbose flag
    rich_handler = RichHandler(
        console=console,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
    )
    rich_handler.setLevel(level)
    root.addHandler(rich_handler)

    # Plain file handler — always full DEBUG regardless of verbose flag
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Use module __name__ as the name."""
    return logging.getLogger(name)
