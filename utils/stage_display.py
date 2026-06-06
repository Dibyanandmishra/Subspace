"""TUI stage progress tracker — start, done, warn, fail, and sub-log functions."""

from rich.rule import Rule

from utils.console import console


STAGE_LABELS: dict[int, tuple[str, str, str]] = {
    1: ("STAGE 1", "LOOKALIKE DISCOVERY",           "Ocean.io"),
    2: ("STAGE 2", "DECISION-MAKER IDENTIFICATION", "Prospeo"),
    3: ("STAGE 3", "EMAIL RESOLUTION",              "Eazyreach"),
    4: ("STAGE 4", "OUTREACH SEND",                 "Brevo"),
}


def print_stage_start(stage_num: int) -> None:
    """Print the running-state stage header (yellow spinner icon)."""
    num, name, service = STAGE_LABELS[stage_num]
    console.print()
    console.print(Rule(style="dim"))
    console.print(
        f" [yellow]⠿[/yellow]  [bold cyan]{num}[/bold cyan]  "
        f"[bold]{name}[/bold]"
        f"[dim]          {service}[/dim]"
    )


def print_stage_done(stage_num: int, summary: str) -> None:
    """Print the completed-state stage header (green check icon)."""
    num, name, _ = STAGE_LABELS[stage_num]
    console.print(
        f" [bold green]✓[/bold green]  [bold cyan]{num}[/bold cyan]  "
        f"[bold]{name}[/bold]"
        f"[dim]          [/dim][bold green]{summary}[/bold green]"
    )
    console.print()


def print_stage_warn(stage_num: int, summary: str) -> None:
    """Print the warning-state stage header (yellow warning icon)."""
    num, name, _ = STAGE_LABELS[stage_num]
    console.print(
        f" [yellow]⚠[/yellow]  [bold cyan]{num}[/bold cyan]  "
        f"[bold]{name}[/bold]"
        f"[dim]          [/dim][yellow]{summary}[/yellow]"
    )
    console.print()


def print_stage_fail(stage_num: int, reason: str) -> None:
    """Print the failed-state stage header (red cross icon)."""
    num, name, _ = STAGE_LABELS[stage_num]
    console.print(
        f" [bold red]✗[/bold red]  [bold cyan]{num}[/bold cyan]  "
        f"[bold]{name}[/bold]"
        f"[dim]          [/dim][bold red]{reason}[/bold red]"
    )
    console.print()


def log_sub(message: str, style: str = "dim") -> None:
    """Print an indented sub-item log line inside a stage block."""
    console.print(f"  [dim]›[/dim] [{style}]{message}[/{style}]")
