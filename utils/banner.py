"""Application startup banner component."""

import datetime

from rich import box
from rich.align import Align
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from utils.console import console


def print_banner(seed_domain: str, run_id: str) -> None:
    """Print the startup banner with run identity metadata."""
    title = Text()
    title.append("⚡  SUBSPACE OUTREACH PIPELINE\n", style="bold cyan")
    title.append("    Automated Cold-Outreach · Zero Manual Steps", style="dim")

    console.print(
        Panel(
            Align.center(title),
            border_style="bold cyan",
            box=box.DOUBLE,
            padding=(1, 4),
        )
    )
    console.print()
    console.print(f"  [bold]Seed domain[/bold]   [cyan]{seed_domain}[/cyan]")
    console.print(f"  [bold]Run ID[/bold]        [dim]{run_id}[/dim]")
    console.print(
        f"  [bold]Started[/bold]       "
        f"[dim]{datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}[/dim]"
    )
    console.print()
    console.print(Rule(style="bold cyan"))
