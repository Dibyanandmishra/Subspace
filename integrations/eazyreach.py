"""Eazyreach API wrapper — LinkedIn URL to verified email resolution."""

import httpx

from models.schemas import EazyreachResponse
from models.settings import settings
from utils.retry import EazyreachAuthError, EazyreachCreditsError, make_retry_decorator
from utils.stage_display import log_sub

_BASE_URL = "https://api.eazyreach.com"
_ENDPOINT = "/api/v1/find-email"

_LOW_CREDIT_THRESHOLD = 10


def resolve_email(linkedin_url: str) -> EazyreachResponse:
    """
    Resolve a LinkedIn URL to a verified email via Eazyreach.
    Returns EazyreachResponse — check .is_resolved for outcome.
    Raises EazyreachAuthError on 401.
    Raises EazyreachCreditsError on insufficient credits.
    Retries on 429/5xx but never retries on email_status "not_found".
    """
    headers = {"X-Api-Key": settings.eazyreach_api_key.get_secret_value()}

    retry = make_retry_decorator(
        max_attempts=settings.max_retry_attempts,
        backoff_factor=settings.retry_backoff_factor,
    )

    @retry
    def _call() -> EazyreachResponse:
        resp = httpx.post(
            f"{_BASE_URL}{_ENDPOINT}",
            headers=headers,
            json={"linkedin_url": linkedin_url},
            timeout=settings.request_timeout_seconds,
        )

        if resp.status_code == 401:
            raise EazyreachAuthError("Eazyreach rejected the API key (401)")

        resp.raise_for_status()  # 429/5xx → HTTPStatusError → retried by tenacity

        parsed = EazyreachResponse.model_validate(resp.json())

        # not_found is a data outcome, not a transient failure — return immediately, no retry
        if parsed.data and parsed.data.email_status == "not_found":
            return parsed

        # Credits exhausted is a run-level abort — PipelineError, not retried
        if not parsed.success and parsed.error:
            if parsed.error.get("code") == "INSUFFICIENT_CREDITS":
                raise EazyreachCreditsError("Eazyreach credits exhausted")

        # Credit balance warning
        if parsed.data and parsed.data.credits_remaining is not None:
            if parsed.data.credits_remaining < _LOW_CREDIT_THRESHOLD:
                log_sub(
                    f"⚠ Eazyreach credits low: {parsed.data.credits_remaining} remaining"
                    " — contact Subspace to top up",
                    style="yellow",
                )

        return parsed

    return _call()
