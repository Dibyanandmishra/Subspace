"""Stage 2 — Decision-maker identification via Prospeo."""

from integrations.prospeo import get_contacts_for_domain
from models.schemas import Contact, ContactResult, LookalikeResult
from utils.retry import ProspeoAuthError, ProspeoCreditsError
from utils.stage_display import log_sub, print_stage_done, print_stage_fail, print_stage_start, print_stage_warn


def run_stage2(lookalike_result: LookalikeResult) -> ContactResult:
    """
    Find C-suite/VP contacts for each company in lookalike_result.
    Returns ContactResult. Raises ProspeoAuthError or ProspeoCreditsError on run-level failures.
    """
    print_stage_start(2)

    all_contacts: list[Contact] = []  # Only contacts with LinkedIn URL (usable in Stage 3)
    skipped_domains: list[str] = []
    seen_linkedin_urls: set[str] = set()
    total_found = 0
    total_without_linkedin = 0

    for company in lookalike_result.companies:
        domain = company.domain

        try:
            raw_contacts = get_contacts_for_domain(domain)
        except (ProspeoAuthError, ProspeoCreditsError):
            print_stage_fail(2, "API error — run aborted")
            raise

        if not raw_contacts:
            skipped_domains.append(domain)
            log_sub(f"[cyan]{domain:<30}[/cyan] [dim red]◌[/dim red]  [dim]0 contacts — domain skipped[/dim]")
            continue

        domain_with = 0
        domain_without = 0

        for contact in raw_contacts:
            total_found += 1
            if contact.linkedin_url:
                if contact.linkedin_url in seen_linkedin_urls:
                    log_sub(
                        f"[bold magenta]{contact.name}[/bold magenta] "
                        f"([cyan]{domain}[/cyan]) "
                        f"[dim red]◌[/dim red]  [dim]duplicate LinkedIn — skipped[/dim]"
                    )
                    total_found -= 1  # Duplicate doesn't count as a new find
                    continue
                seen_linkedin_urls.add(contact.linkedin_url)
                all_contacts.append(contact)
                domain_with += 1
            else:
                # No LinkedIn URL — counted but cannot proceed to Stage 3
                total_without_linkedin += 1
                domain_without += 1

        total = domain_with + domain_without
        parts = [f"[bold blue]{total}[/bold blue] contact{'s' if total != 1 else ''}"]
        if domain_with:
            parts.append(f"[bold blue]{domain_with}[/bold blue] with LinkedIn")
        if domain_without:
            parts.append(f"[dim red]{domain_without} without (skipped)[/dim red]")

        log_sub(
            f"[cyan]{domain:<30}[/cyan] [bold green]✓[/bold green]  " + " · ".join(parts)
        )

    result = ContactResult(
        companies_searched=len(lookalike_result.companies),
        contacts_found=total_found,
        contacts_with_linkedin=len(all_contacts),
        contacts_without_linkedin=total_without_linkedin,
        contacts=all_contacts,
        skipped_domains=skipped_domains,
    )

    summary = f"{len(all_contacts)} contacts with LinkedIn"
    if skipped_domains:
        summary += f" · {len(skipped_domains)} domain{'s' if len(skipped_domains) != 1 else ''} skipped"
        print_stage_warn(2, summary)
    else:
        print_stage_done(2, summary)

    return result
