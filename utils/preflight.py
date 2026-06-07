"""Pre-flight validation — domain format check and connectivity check."""

import re

import httpx
import typer

from utils.retry import ConnectivityError

DOMAIN_REGEX = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$')

_CONNECTIVITY_URL = "https://www.google.com"


def validate_domain(domain: str) -> str:
    """
    Validate and normalize the domain format.
    Strips protocol (https://, http://) and www. prefix.
    Raises typer.BadParameter on invalid format.
    Returns the normalized bare domain.
    """
    domain = re.sub(r'^https?://', '', domain.strip().lower())
    domain = re.sub(r'^www\.', '', domain)

    if not DOMAIN_REGEX.match(domain):
        raise typer.BadParameter(
            f"'{domain}' is not a valid domain. "
            "Expected format: example.com (no paths, ports, or protocols)"
        )

    return domain


def check_connectivity() -> None:
    """
    Make a lightweight HEAD request to verify internet access.
    Raises ConnectivityError with a user-friendly message if offline.
    """
    try:
        httpx.head(_CONNECTIVITY_URL, timeout=5, follow_redirects=True)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as exc:
        raise ConnectivityError(
            "No internet connectivity detected. "
            "Check your network connection and try again."
        ) from exc
