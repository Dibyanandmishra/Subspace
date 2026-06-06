"""Tenacity retry decorator and custom pipeline exception hierarchy."""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception


# ─── EXCEPTION HIERARCHY ──────────────────────────────────────────────────────

class PipelineError(Exception):
    """Base class for all run-level errors that abort the pipeline."""


class OceanAuthError(PipelineError):
    """Ocean.io rejected the API key (401)."""


class ProspeoAuthError(PipelineError):
    """Prospeo rejected the API key (401)."""


class ProspeoCreditsError(PipelineError):
    """Prospeo account has insufficient credits (402)."""


class EazyreachAuthError(PipelineError):
    """Eazyreach rejected the API key (401)."""


class EazyreachCreditsError(PipelineError):
    """Eazyreach account has insufficient credits."""


class BrevoAuthError(PipelineError):
    """Brevo rejected the API key (401)."""


class BrevoSenderError(PipelineError):
    """Brevo sender address is not verified (400 sender not verified)."""


class BrevoLimitError(PipelineError):
    """Brevo daily send limit reached (402)."""


class ConnectivityError(PipelineError):
    """No internet connectivity detected at pre-flight check."""


# ─── RETRY CLASSIFIER ─────────────────────────────────────────────────────────

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def is_retryable_error(exc: BaseException) -> bool:
    """Return True for transient failures that should be retried with backoff."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.NetworkError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return False


# ─── RETRY DECORATOR FACTORY ──────────────────────────────────────────────────

def make_retry_decorator(
    max_attempts: int = 3,
    backoff_factor: float = 2.0,
) -> retry:
    """Return a tenacity @retry decorator configured for transient HTTP failures."""
    return retry(
        retry=retry_if_exception(is_retryable_error),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=backoff_factor, min=1, max=60),
        reraise=True,
    )
