"""Stage 3 — Email resolution via Eazyreach."""

from integrations.eazyreach import resolve_email
from models.schemas import Contact, ContactResult, EmailResolutionResult, VerifiedContact
from utils.retry import EazyreachAuthError, EazyreachCreditsError
from utils.stage_display import log_sub, print_stage_done, print_stage_fail, print_stage_start, print_stage_warn


def run_stage3(contact_result: ContactResult) -> EmailResolutionResult:
    """
    Resolve a verified work email for each contact that has a LinkedIn URL.
    Returns EmailResolutionResult. Raises EazyreachAuthError or EazyreachCreditsError
    on run-level failures.
    """
    print_stage_start(3)

    candidates = [c for c in contact_result.contacts if c.linkedin_url]
    verified_contacts: list[VerifiedContact] = []
    unresolved_contacts: list[VerifiedContact] = []
    seen_emails: set[str] = set()

    for contact in candidates:
        label = f"[bold magenta]{contact.name}[/bold magenta] ([cyan]{contact.company_domain}[/cyan])"

        try:
            response = resolve_email(contact.linkedin_url)  # type: ignore[arg-type]
        except EazyreachAuthError:
            print_stage_fail(3, "API key rejected (401) — run aborted")
            raise
        except EazyreachCreditsError:
            print_stage_fail(3, "Eazyreach credits exhausted — run aborted")
            raise
        except Exception:
            # Retries exhausted — mark as error, continue to next contact
            vc = _make_unresolved(contact, "error", "all retries exhausted — marked as error")
            unresolved_contacts.append(vc)
            log_sub(f"{label}  [bold red]✗[/bold red]  [bold red]all retries exhausted — skipped[/bold red]")
            continue

        if response.is_personal_email:
            vc = _make_unresolved(contact, "personal_email", "personal email returned — skipped")
            unresolved_contacts.append(vc)
            log_sub(f"{label}  [dim red]◌[/dim red]  [dim red]personal email returned — skipped[/dim red]")
            continue

        if not response.is_resolved:
            vc = _make_unresolved(contact, "unresolved", "unresolved — not in Eazyreach database")
            unresolved_contacts.append(vc)
            log_sub(f"{label}  [dim red]◌[/dim red]  [dim]unresolved — not in Eazyreach database[/dim]")
            continue

        email = response.data.email  # type: ignore[union-attr]

        # Deduplicate by resolved email address
        if email in seen_emails:
            vc = _make_unresolved(contact, "duplicate", f"duplicate email — {email} already queued")
            unresolved_contacts.append(vc)
            log_sub(f"{label}  [dim red]◌[/dim red]  [dim]duplicate — {email} already queued[/dim]")
            continue

        seen_emails.add(email)
        vc = VerifiedContact(
            name=contact.name,
            title=contact.title,
            company=contact.company,
            company_domain=contact.company_domain,
            linkedin_url=contact.linkedin_url or "",
            email=email,
            email_verified=True,
            resolution_status="verified",
        )
        verified_contacts.append(vc)
        log_sub(
            f"{label}  [bold green]✓[/bold green]  [bold green]{email}[/bold green]"
        )

    emails_verified = len(verified_contacts)
    emails_unresolved = len(unresolved_contacts)

    result = EmailResolutionResult(
        contacts_attempted=len(candidates),
        emails_verified=emails_verified,
        emails_unresolved=emails_unresolved,
        verified_contacts=verified_contacts,
        unresolved_contacts=unresolved_contacts,
    )

    summary = f"{emails_verified} verified"
    if emails_unresolved:
        summary += f" · {emails_unresolved} unresolved"
        print_stage_warn(3, summary)
    else:
        print_stage_done(3, summary)

    return result


def _make_unresolved(contact: Contact, status: str, reason: str) -> VerifiedContact:
    return VerifiedContact(
        name=contact.name,
        title=contact.title,
        company=contact.company,
        company_domain=contact.company_domain,
        linkedin_url=contact.linkedin_url or "",
        email=None,
        email_verified=False,
        resolution_status=status,
        skip_reason=reason,
    )
