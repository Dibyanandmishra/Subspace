"""Stage 1 — Lookalike company discovery via Ocean.io."""

from integrations.ocean import get_lookalike_companies
from models.schemas import LookalikeResult
from models.settings import settings
from utils.retry import OceanAuthError
from utils.stage_display import log_sub, print_stage_done, print_stage_fail, print_stage_start


def run_stage1(
    seed_domain: str,
    min_size: int | None = None,
    max_size: int | None = None,
) -> LookalikeResult:
    """
    Discover companies similar to seed_domain via Ocean.io.
    Returns LookalikeResult. Raises OceanAuthError on auth failure.
    """
    print_stage_start(1)
    log_sub(f"Querying Ocean.io for companies similar to [cyan]{seed_domain}[/cyan]...")

    try:
        result = get_lookalike_companies(seed_domain)
    except OceanAuthError:
        print_stage_fail(1, "API key rejected (401) — run aborted")
        raise

    # Apply EXCLUDE_DOMAINS blocklist filter
    excluded = settings.exclude_domains_list
    if excluded:
        before = len(result.companies)
        result.companies = [c for c in result.companies if c.domain not in excluded]
        removed = before - len(result.companies)
        if removed:
            log_sub(
                f"[bold blue]{removed}[/bold blue] domain(s) removed by EXCLUDE_DOMAINS blocklist",
                style="dim",
            )
        result = result.model_copy(update={"companies_found": len(result.companies)})

    # Apply company size filter
    if min_size is not None or max_size is not None:
        before = len(result.companies)
        result.companies = [
            c for c in result.companies
            if c.employee_count is not None
            and (min_size is None or c.employee_count >= min_size)
            and (max_size is None or c.employee_count <= max_size)
        ]
        kept = len(result.companies)
        log_sub(f"Size filter applied: [bold blue]{kept}[/bold blue] of [bold blue]{before}[/bold blue] companies kept")
        result = result.model_copy(update={"companies_found": kept})

    if result.companies_found == 0:
        print_stage_done(1, "0 companies found")
        return result

    log_sub(
        f"[bold blue]{result.companies_found}[/bold blue] companies found"
        f" across [bold blue]{result.pages_fetched}[/bold blue] page(s)"
    )
    print_stage_done(1, f"{result.companies_found} companies found")
    return result
