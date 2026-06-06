"""Eazyreach API wrapper — LinkedIn URL to verified email resolution."""

import httpx

from models.schemas import EazyreachResponse
from models.settings import settings
from utils.retry import EazyreachAuthError, EazyreachCreditsError, make_retry_decorator

_BASE_URL = "https://api.eazyreach.com"
_ENDPOINT = "/api/v1/find-email"


def resolve_email(linkedin_url: str) -> EazyreachResponse:
    """
    Resolve a LinkedIn URL to a verified email via Eazyreach.
    Returns EazyreachResponse — check .is_resolved for outcome.
    Raises EazyreachCreditsError on insufficient credits.
    Raises EazyreachAuthError on 401.
    Never retries on email_status "not_found" — preserves credits.
    """
    headers = {"X-Api-Key": settings.eazyreach_api_key.get_secret_value()}

    # First attempt — undecorated so we can inspect the response before deciding to retry
    def _call_once() -> EazyreachResponse:
        resp = httpx.post(
            f"{_BASE_URL}{_ENDPOINT}",
            headers=headers,
            json={"linkedin_url": linkedin_url},
            timeout=settings.request_timeout_seconds,
        )

        if resp.status_code == 401:
            raise EazyreachAuthError("Eazyreach rejected the API key (401)")

        resp.raise_for_status()
        return EazyreachResponse.model_validate(resp.json())

    response = _call_once()

    # not_found is a data result, not a transient failure — never retry, don't waste credits
    if (
        response.data is not None
        and response.data.email_status == "not_found"
    ):
        return response

    # Credits exhausted — abort the whole stage
    if not response.success and response.error:
        error_code = response.error.get("code", "")
        if error_code == "INSUFFICIENT_CREDITS":
            raise EazyreachCreditsError("Eazyreach credits exhausted")

    # If the first call already resolved or produced a usable result, return it
    if response.is_resolved or response.success:
        return response

    # Transient failure path — apply retry decorator for 429/5xx
    retry = make_retry_decorator(
        max_attempts=settings.max_retry_attempts,
        backoff_factor=settings.retry_backoff_factor,
    )

    @retry
    def _call_with_retry() -> EazyreachResponse:
        resp = httpx.post(
            f"{_BASE_URL}{_ENDPOINT}",
            headers=headers,
            json={"linkedin_url": linkedin_url},
            timeout=settings.request_timeout_seconds,
        )

        if resp.status_code == 401:
            raise EazyreachAuthError("Eazyreach rejected the API key (401)")

        resp.raise_for_status()
        parsed = EazyreachResponse.model_validate(resp.json())

        if not parsed.success and parsed.error:
            code = parsed.error.get("code", "")
            if code == "INSUFFICIENT_CREDITS":
                raise EazyreachCreditsError("Eazyreach credits exhausted")

        return parsed

    return _call_with_retry()
