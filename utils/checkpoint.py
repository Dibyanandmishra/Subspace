"""Safety checkpoint dashboard and y/N confirmation gate."""

from typing import Optional

from rich import box
from rich.panel import Panel

from models.schemas import EmailResolutionResult
from utils.console import console

_SAMPLE_CONTACT_LIMIT = 3


def render_checkpoint(
    seed_domain: str,
    run_id: str,
    companies_found: int,
    contacts_found: int,
    result: EmailResolutionResult,
    sender_email: str,
    dry_run: bool = False,
) -> Optional[str]:
    """
    Render the safety checkpoint panel.
    Returns "y" if operator confirms send, None if they abort or verified_count == 0.
    When dry_run=True, renders the panel but skips the y/N prompt and returns None.
    """
    verified = result.verified_contacts
    unresolved_count = result.emails_unresolved
    verified_count = result.emails_verified

    lines = [
        f"  [bold]Seed domain[/bold]    [cyan]{seed_domain}[/cyan]",
        f"  [bold]Run ID[/bold]         [dim]{run_id}[/dim]",
        "",
        f"  [bold green]✓[/bold green]  [bold]Lookalike companies[/bold]   [bold blue]{companies_found}[/bold blue]  found",
        f"  [bold green]✓[/bold green]  [bold]Decision-makers[/bold]       [bold blue]{contacts_found}[/bold blue]  identified",
    ]

    if verified_count > 0:
        lines.append(
            f"  [bold green]✓[/bold green]  [bold]Emails verified[/bold]       [bold blue]{verified_count}[/bold blue]  ready to send"
        )
    else:
        lines.append(
            f"  [bold red]✗[/bold red]  [bold]Emails verified[/bold]       [bold red]0[/bold red]  — all contacts were unresolvable"
        )

    if unresolved_count > 0:
        lines.append(
            f"  [dim red]◌[/dim red]  [bold]Emails skipped[/bold]        [dim red]{unresolved_count}[/dim red]  unresolved — excluded"
        )

    body = "\n".join(lines)

    # Zero-email case — show summary panel, no prompt
    if verified_count == 0:
        body += (
            "\n\n  Nothing to send. No emails were queued."
            "\n  Run artifact saved. Try a different seed domain."
        )
        console.print()
        console.print()
        console.print(
            Panel(
                body,
                title="[bold white]OUTREACH SUMMARY[/bold white]",
                subtitle="[dim]Review carefully before sending[/dim]",
                border_style="bold cyan",
                box=box.DOUBLE,
                padding=(1, 2),
            )
        )
        return None

    # Contacts section
    contacts_section = "\n  [bold dim]CONTACTS QUEUED FOR OUTREACH[/bold dim]\n"
    for i, contact in enumerate(verified[:_SAMPLE_CONTACT_LIMIT], 1):
        contacts_section += (
            f"\n  {i}   [bold magenta]{contact.name}[/bold magenta]"
            f"     {contact.title}     [cyan]{contact.company_domain}[/cyan]"
            f"\n      [dim]{contact.email}[/dim]\n"
        )
    if verified_count > _SAMPLE_CONTACT_LIMIT:
        contacts_section += (
            f"\n  [dim]...and {verified_count - _SAMPLE_CONTACT_LIMIT} more contact"
            f"{'s' if verified_count - _SAMPLE_CONTACT_LIMIT != 1 else ''}[/dim]\n"
        )

    # Warning section
    warning_section = (
        f"\n  [bold yellow]⚠[/bold yellow]   "
        f"[bold yellow]THIS WILL SEND  {verified_count}  LIVE EMAILS  VIA BREVO[/bold yellow]\n"
        f"  [dim]    Sender: {sender_email}[/dim]\n"
        f"  [dim red]    Emails cannot be unsent once confirmed.[/dim red]\n\n"
        f"  [bold green]    Type  y  to send[/bold green]"
        f"   [dim]  Any other key to abort safely[/dim]"
    )

    body = body + "\n" + contacts_section + warning_section

    console.print()
    console.print()
    console.print(
        Panel(
            body,
            title="[bold white]OUTREACH SUMMARY[/bold white]",
            subtitle="[dim]Review carefully before sending[/dim]",
            border_style="bold cyan",
            box=box.DOUBLE,
            padding=(1, 2),
        )
    )
    console.print()

    if dry_run:
        return None

    response = console.input("  [bold white]Proceed? [y/N]:[/bold white]  ").strip().lower()
    return "y" if response == "y" else None
