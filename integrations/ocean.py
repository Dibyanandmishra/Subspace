"""Ocean.io API wrapper — lookalike company discovery."""

import httpx

from models.schemas import Company, LookalikeResult, OceanResponse
from models.settings import settings
from utils.retry import OceanAuthError, make_retry_decorator

_BASE_URL = "https://api.ocean.io"
_ENDPOINT = "/v4/companies/find_similar"


def get_lookalike_companies(seed_domain: str) -> LookalikeResult:
    """
    Query Ocean.io for companies similar to seed_domain.
    Returns a LookalikeResult with deduplicated, normalized domains.
    Raises OceanAuthError on 401. Returns empty LookalikeResult on 404.
    """
    retry = make_retry_decorator(
        max_attempts=settings.max_retry_attempts,
        backoff_factor=settings.retry_backoff_factor,
    )

    headers = {"Authorization": f"Bearer {settings.ocean_api_key.get_secret_value()}"}
    seen_domains: set[str] = set()
    companies: list[Company] = []
    pages_fetched = 0
    cursor: str | None = None

    @retry
    def _fetch_page(cursor: str | None) -> OceanResponse:
        payload: dict = {
            "domain": seed_domain,
            "limit": settings.ocean_max_results,
            "filters": {"exclude_domains": [seed_domain]},
        }
        if cursor:
            payload["cursor"] = cursor

        resp = httpx.post(
            f"{_BASE_URL}{_ENDPOINT}",
            headers=headers,
            json=payload,
            timeout=settings.request_timeout_seconds,
        )

        if resp.status_code == 401:
            raise OceanAuthError("Ocean.io rejected the API key (401)")
        if resp.status_code == 404:
            return None  # type: ignore[return-value]

        resp.raise_for_status()
        return OceanResponse.model_validate(resp.json())

    while True:
        response = _fetch_page(cursor)

        # 404 treated as empty result
        if response is None:
            break

        pages_fetched += 1

        for raw in response.data.companies:
            if raw.domain and raw.domain not in seen_domains and raw.domain != seed_domain:
                seen_domains.add(raw.domain)
                companies.append(
                    Company(
                        domain=raw.domain,
                        name=raw.name,
                        source_domain=seed_domain,
                        employee_count=raw.employee_count,
                    )
                )

        if not response.data.has_more or len(companies) >= settings.ocean_max_results:
            break

        cursor = response.data.next_cursor

    return LookalikeResult(
        seed_domain=seed_domain,
        companies=companies,
        companies_found=len(companies),
        pages_fetched=max(pages_fetched, 1),
    )
