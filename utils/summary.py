"""Final run summary TUI component."""

from models.schemas import RunArtifact
from utils.console import console


def print_final_summary(artifact: RunArtifact) -> None:
    """Print the end-of-run summary panel with the correct variant for the run outcome."""
    console.print()
    console.rule(style="dim")
    console.print()

    if artifact.run_aborted_at_checkpoint:
        console.print(" [dim]◌[/dim]  [bold]RUN ABORTED[/bold] [dim]— No emails were sent.[/dim]")
        console.print()
        console.print(f"     [bold]Seed domain[/bold]      [cyan]{artifact.seed_domain}[/cyan]")
        console.print(
            f"     [bold]Emails verified[/bold]  [bold blue]{artifact.emails_verified}[/bold blue]"
            f"   [dim](queued but not sent — operator cancelled)[/dim]"
        )
    elif artifact.emails_failed > 0:
        console.print(" [yellow]⚠[/yellow]  [bold]RUN COMPLETE[/bold] [dim]— WITH WARNINGS[/dim]")
        _print_summary_rows(artifact)
    else:
        console.print(" [bold green]✓[/bold green]  [bold green]RUN COMPLETE[/bold green]")
        _print_summary_rows(artifact)

    console.print()
    console.print(
        f"  [dim]Run artifact[/dim] [dim cyan]→[/dim cyan] [cyan]output/{artifact.run_id}.json[/cyan]"
    )
    console.print()
    console.rule(style="dim")


def _print_summary_rows(artifact: RunArtifact) -> None:
    console.print()
    rows = [
        ("Seed domain",     f"[cyan]{artifact.seed_domain}[/cyan]",                     ""),
        ("Companies",       f"[bold blue]{artifact.companies_found}[/bold blue]",        "found"),
        ("Contacts",        f"[bold blue]{artifact.contacts_found}[/bold blue]",         "identified"),
        ("Emails verified", f"[bold blue]{artifact.emails_verified}[/bold blue]",        "ready"),
        ("Emails sent",
         f"[bold green]{artifact.emails_sent}[/bold green]",
         "[bold green]✓ delivered[/bold green]"),
        ("Emails failed",
         f"[bold red]{artifact.emails_failed}[/bold red]" if artifact.emails_failed else "0",
         "[bold red]✗ — see artifact[/bold red]" if artifact.emails_failed else ""),
        ("Emails skipped",
         f"[dim red]{artifact.emails_unresolved}[/dim red]",
         "[dim](unresolved — not sent)[/dim]"),
    ]
    for label, value, note in rows:
        console.print(f"     [bold]{label:<17}[/bold] {value:<6} {note}")
