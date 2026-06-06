"""Stage 4 — Outreach send via Brevo."""

from integrations.brevo import send_email
from models.schemas import EmailResolutionResult, SendResult
from utils.checkpoint import render_checkpoint
from utils.retry import BrevoAuthError, BrevoLimitError, BrevoSenderError
from utils.stage_display import log_sub, print_stage_done, print_stage_fail, print_stage_start, print_stage_warn


def run_stage4(
    email_result: EmailResolutionResult,
    seed_domain: str,
    run_id: str,
    companies_found: int,
    contacts_found: int,
    sender_email: str,
) -> tuple[list[SendResult], bool]:
    """
    Show checkpoint, get confirmation, then send emails via Brevo.
    Returns (send_results, user_confirmed_send).
    send_results is empty and user_confirmed_send is False if checkpoint aborted.
    Raises BrevoAuthError, BrevoSenderError, or BrevoLimitError on run-level failures.
    """
    confirmed = render_checkpoint(
        seed_domain=seed_domain,
        run_id=run_id,
        companies_found=companies_found,
        contacts_found=contacts_found,
        result=email_result,
        sender_email=sender_email,
    )

    if confirmed != "y":
        return [], False

    print_stage_start(4)

    send_results: list[SendResult] = []

    for contact in email_result.verified_contacts:
        label = f"[bold magenta]{contact.name:<20}[/bold magenta] [dim]{contact.email}[/dim]"

        try:
            result = send_email(contact, seed_domain)
        except (BrevoAuthError, BrevoSenderError, BrevoLimitError):
            print_stage_fail(4, "Brevo error — stopping send")
            raise

        send_results.append(result)

        if result.status == "sent":
            msg_id = f"  [dim]msg:{result.brevo_message_id}[/dim]" if result.brevo_message_id else ""
            log_sub(f"{label}  [bold green]✓[/bold green]  sent{msg_id}")
        else:
            log_sub(
                f"{label}  [bold red]✗[/bold red]  [bold red]failed[/bold red]"
                f"  [dim]— {result.error_message or 'unknown error'}[/dim]"
            )

    failures = sum(1 for r in send_results if r.status == "failed")
    sent = sum(1 for r in send_results if r.status == "sent")

    summary = f"{sent} sent"
    if failures:
        summary += f" · {failures} failed"
        print_stage_warn(4, summary)
    else:
        print_stage_done(4, summary)

    return send_results, True
