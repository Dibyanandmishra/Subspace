"""Stage 1 — Lookalike company discovery via Ocean.io."""

from integrations.ocean import get_lookalike_companies
from models.schemas import LookalikeResult
from utils.retry import OceanAuthError
from utils.stage_display import log_sub, print_stage_done, print_stage_fail, print_stage_start


def run_stage1(seed_domain: str) -> LookalikeResult:
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

    if result.companies_found == 0:
        print_stage_done(1, "0 companies found")
        return result

    log_sub(
        f"[bold blue]{result.companies_found}[/bold blue] companies found"
        f" across [bold blue]{result.pages_fetched}[/bold blue] page(s)"
    )
    print_stage_done(1, f"{result.companies_found} companies found")
    return result
