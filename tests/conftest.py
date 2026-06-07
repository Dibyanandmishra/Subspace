"""Shared pytest fixtures for all test modules."""

import os

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_none


def pytest_configure(config):
    """Set env vars before the settings singleton is instantiated."""
    os.environ.setdefault("OCEAN_API_KEY", "test-ocean-key")
    os.environ.setdefault("PROSPEO_API_KEY", "test-prospeo-key")
    os.environ.setdefault("EAZYREACH_API_KEY", "test-eazyreach-key")
    os.environ.setdefault("BREVO_API_KEY", "test-brevo-key")
    os.environ.setdefault("SENDER_EMAIL", "test@test.com")
    os.environ.setdefault("SENDER_NAME", "Test Sender")


def _make_fast_retry(max_attempts=3, backoff_factor=0.0):
    """Instant retry decorator with no wait — prevents slow tests."""
    from utils.retry import is_retryable_error

    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_none(),
        retry=retry_if_exception(is_retryable_error),
        reraise=True,
    )


import pytest


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch):
    """Replace tenacity retry in all integrations with an instant no-wait version."""
    monkeypatch.setattr("integrations.ocean.make_retry_decorator", _make_fast_retry)
    monkeypatch.setattr("integrations.prospeo.make_retry_decorator", _make_fast_retry)
    monkeypatch.setattr("integrations.eazyreach.make_retry_decorator", _make_fast_retry)
    monkeypatch.setattr("integrations.brevo.make_retry_decorator", _make_fast_retry)
