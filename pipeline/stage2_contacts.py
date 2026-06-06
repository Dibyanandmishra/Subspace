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

    all_contacts: list[Contact] = []
    skipped_domains: list[str] = []
    seen_linkedin_urls: set[str] = set()

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
            if contact.linkedin_url:
                if contact.linkedin_url in seen_linkedin_urls:
                    continue
                seen_linkedin_urls.add(contact.linkedin_url)
                all_contacts.append(contact)
                domain_with += 1
            else:
                all_contacts.append(contact)
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

    contacts_with_linkedin = sum(1 for c in all_contacts if c.linkedin_url)
    contacts_without_linkedin = len(all_contacts) - contacts_with_linkedin

    result = ContactResult(
        companies_searched=len(lookalike_result.companies),
        contacts_found=len(all_contacts),
        contacts_with_linkedin=contacts_with_linkedin,
        contacts_without_linkedin=contacts_without_linkedin,
        contacts=all_contacts,
        skipped_domains=skipped_domains,
    )

    summary = f"{len(all_contacts)} contacts"
    if skipped_domains:
        summary += f" · {len(skipped_domains)} domain{'s' if len(skipped_domains) != 1 else ''} skipped"
        print_stage_warn(2, summary)
    else:
        print_stage_done(2, summary)

    return result
