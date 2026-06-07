"""Tests for Eazyreach wrapper and Stage 3 pipeline."""

from unittest.mock import patch

import httpx
import pytest
import respx

from integrations.eazyreach import resolve_email
from models.schemas import (
    Contact,
    ContactResult,
    EazyreachResponse,
    EazyreachResultData,
)
from utils.retry import EazyreachAuthError, EazyreachCreditsError

EAZYREACH_URL = "https://api.eazyreach.com/api/v1/find-email"


def _ez_resp(email=None, verified=True, status="valid", success=True, error=None, credits=None):
    data = None
    if email is not None or success:
        data_dict = {"email_verified": verified, "email_status": status}
        if email:
            data_dict["email"] = email
        if credits is not None:
            data_dict["credits_remaining"] = credits
        data = data_dict
    payload = {"success": success}
    if data:
        payload["data"] = data
    if error:
        payload["error"] = error
    return httpx.Response(200, json=payload)


def _make_contact(linkedin="https://linkedin.com/in/jane"):
    return Contact(
        name="Jane Doe",
        title="CTO",
        company="Brex",
        company_domain="brex.com",
        linkedin_url=linkedin,
    )


def _make_contact_result(*contacts):
    return ContactResult(
        companies_searched=1,
        contacts_found=len(contacts),
        contacts_with_linkedin=len(contacts),
        contacts_without_linkedin=0,
        contacts=list(contacts),
        skipped_domains=[],
    )


# ── Integration wrapper tests ─────────────────────────────────────────────────

@respx.mock
def test_resolve_email_verified_work_email():
    respx.post(EAZYREACH_URL).mock(return_value=_ez_resp("jane@brex.com", verified=True))
    result = resolve_email("https://linkedin.com/in/jane")
    assert result.is_resolved is True
    assert result.data.email == "jane@brex.com"


@respx.mock
def test_resolve_email_not_found_returns_unresolved():
    respx.post(EAZYREACH_URL).mock(return_value=_ez_resp(
        email=None, verified=False, status="not_found", success=True
    ))
    result = resolve_email("https://linkedin.com/in/ghost")
    assert result.is_resolved is False


@respx.mock
def test_resolve_email_not_found_does_not_retry():
    """not_found must be returned after exactly one HTTP call."""
    route = respx.post(EAZYREACH_URL).mock(return_value=_ez_resp(
        email=None, verified=False, status="not_found", success=True
    ))
    resolve_email("https://linkedin.com/in/ghost")
    assert route.call_count == 1


@respx.mock
def test_resolve_email_personal_email_is_personal():
    respx.post(EAZYREACH_URL).mock(return_value=_ez_resp("jane@gmail.com", verified=True))
    result = resolve_email("https://linkedin.com/in/jane")
    assert result.is_personal_email is True


@respx.mock
def test_resolve_email_401_raises_auth_error():
    respx.post(EAZYREACH_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(EazyreachAuthError):
        resolve_email("https://linkedin.com/in/jane")


@respx.mock
def test_resolve_email_insufficient_credits_raises():
    respx.post(EAZYREACH_URL).mock(return_value=_ez_resp(
        email=None, verified=False, success=False,
        error={"code": "INSUFFICIENT_CREDITS", "message": "out of credits"}
    ))
    with pytest.raises(EazyreachCreditsError):
        resolve_email("https://linkedin.com/in/jane")


@respx.mock
def test_resolve_email_5xx_then_200_retries():
    respx.post(EAZYREACH_URL).mock(side_effect=[
        httpx.Response(500, json={"success": False}),
        _ez_resp("jane@brex.com", verified=True),
    ])
    result = resolve_email("https://linkedin.com/in/jane")
    assert result.is_resolved is True


@respx.mock
def test_resolve_email_low_credits_logs_warning():
    respx.post(EAZYREACH_URL).mock(return_value=_ez_resp(
        "jane@brex.com", verified=True, credits=3
    ))
    with patch("integrations.eazyreach.log_sub") as mock_log:
        resolve_email("https://linkedin.com/in/jane")
    mock_log.assert_called_once()
    args, kwargs = mock_log.call_args
    assert "3" in args[0]
    assert kwargs.get("style") == "yellow"


# ── Stage 3 pipeline tests ────────────────────────────────────────────────────

def _resolved_mock(email="jane@brex.com"):
    return EazyreachResponse(
        success=True,
        data=EazyreachResultData(email=email, email_verified=True, email_status="valid"),
    )


def _unresolved_mock():
    return EazyreachResponse(
        success=True,
        data=EazyreachResultData(email=None, email_verified=False, email_status="not_found"),
    )


def _personal_mock():
    return EazyreachResponse(
        success=True,
        data=EazyreachResultData(email="jane@gmail.com", email_verified=True, email_status="valid"),
    )


def test_run_stage3_resolved_contact_in_verified():
    from pipeline.stage3_emails import run_stage3

    contact = _make_contact()
    cr = _make_contact_result(contact)

    with patch("pipeline.stage3_emails.resolve_email", return_value=_resolved_mock()):
        result = run_stage3(cr)

    assert len(result.verified_contacts) == 1
    assert result.verified_contacts[0].email == "jane@brex.com"
    assert result.verified_contacts[0].resolution_status == "verified"


def test_run_stage3_not_found_in_unresolved():
    from pipeline.stage3_emails import run_stage3

    contact = _make_contact()
    cr = _make_contact_result(contact)

    with patch("pipeline.stage3_emails.resolve_email", return_value=_unresolved_mock()):
        result = run_stage3(cr)

    assert len(result.unresolved_contacts) == 1
    assert result.unresolved_contacts[0].resolution_status == "unresolved"


def test_run_stage3_personal_email_tagged_correctly():
    from pipeline.stage3_emails import run_stage3

    contact = _make_contact()
    cr = _make_contact_result(contact)

    with patch("pipeline.stage3_emails.resolve_email", return_value=_personal_mock()):
        result = run_stage3(cr)

    assert len(result.unresolved_contacts) == 1
    assert result.unresolved_contacts[0].resolution_status == "personal_email"


def test_run_stage3_retries_exhausted_marks_error():
    from pipeline.stage3_emails import run_stage3

    contact = _make_contact()
    cr = _make_contact_result(contact)

    with patch("pipeline.stage3_emails.resolve_email", side_effect=Exception("retry exhausted")):
        result = run_stage3(cr)

    assert len(result.unresolved_contacts) == 1
    assert result.unresolved_contacts[0].resolution_status == "error"


def test_run_stage3_credits_error_propagates():
    from pipeline.stage3_emails import run_stage3

    contact = _make_contact()
    cr = _make_contact_result(contact)

    with patch("pipeline.stage3_emails.resolve_email", side_effect=EazyreachCreditsError("exhausted")):
        with pytest.raises(EazyreachCreditsError):
            run_stage3(cr)


def test_run_stage3_deduplicates_emails():
    """Two contacts resolving to the same email — second tagged duplicate."""
    from pipeline.stage3_emails import run_stage3

    c1 = _make_contact("https://linkedin.com/in/jane")
    c2 = _make_contact("https://linkedin.com/in/jane2")
    cr = _make_contact_result(c1, c2)

    with patch("pipeline.stage3_emails.resolve_email", return_value=_resolved_mock("jane@brex.com")):
        result = run_stage3(cr)

    assert len(result.verified_contacts) == 1
    assert result.unresolved_contacts[0].resolution_status == "duplicate"
