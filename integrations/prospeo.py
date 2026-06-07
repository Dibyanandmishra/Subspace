"""Prospeo API wrapper — decision-maker contact search."""

import httpx

from models.schemas import Contact, ProspeoContactRaw, ProspeoResponseData
from models.settings import settings
from utils.retry import ProspeoAuthError, ProspeoCreditsError, make_retry_decorator
from utils.stage_display import log_sub

_BASE_URL = "https://api.prospeo.io"
_ENDPOINT = "/domain-search"

_LOW_CREDIT_THRESHOLD = 10


def get_contacts_for_domain(domain: str) -> list[Contact]:
    """
    Return C-suite/VP contacts for one domain.
    Returns empty list if domain has no contacts — not an error.
    Raises ProspeoAuthError on 401, ProspeoCreditsError on 402.
    """
    retry = make_retry_decorator(
        max_attempts=settings.max_retry_attempts,
        backoff_factor=settings.retry_backoff_factor,
    )

    headers = {"X-KEY": settings.prospeo_api_key.get_secret_value()}

    @retry
    def _call() -> dict:  # type: ignore[type-arg]
        resp = httpx.post(
            f"{_BASE_URL}{_ENDPOINT}",
            headers=headers,
            json={
                "domain": domain,
                "limit": 10,
                "required_fields": ["linkedin", "job_title"],
                "seniority": settings.seniority_list,
            },
            timeout=settings.request_timeout_seconds,
        )

        if resp.status_code == 401:
            raise ProspeoAuthError("Prospeo rejected the API key (401)")
        if resp.status_code == 402:
            raise ProspeoCreditsError("Prospeo credits exhausted (402)")

        resp.raise_for_status()
        return resp.json()

    raw_json = _call()

    # Response envelope: {"response": {"status": bool, "data": {"contact_list": [...], "total": N}}}
    inner = raw_json.get("response", {})
    data_dict = inner.get("data", {})
    response_data = ProspeoResponseData.model_validate(data_dict)

    contacts: list[Contact] = []
    for raw in response_data.contact_list:
        contact = _to_contact(raw, domain)
        if contact:
            contacts.append(contact)

    # Warn when credits are running low (best-effort — field may not always be present)
    credits_remaining = inner.get("credits_remaining")
    if credits_remaining is not None and credits_remaining < _LOW_CREDIT_THRESHOLD:
        log_sub(f"⚠ Prospeo credits low: {credits_remaining} remaining", style="yellow")

    return contacts


def _to_contact(raw: ProspeoContactRaw, company_domain: str) -> Contact | None:
    name = raw.display_name
    title = raw.job_title or ""
    company = raw.company or ""
    if not name or not title:
        return None
    return Contact(
        name=name,
        title=title,
        company=company,
        company_domain=company_domain,
        linkedin_url=raw.linkedin_url,
        seniority=raw.seniority,
    )
