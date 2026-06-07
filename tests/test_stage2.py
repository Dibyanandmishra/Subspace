"""Tests for Prospeo wrapper and Stage 2 pipeline."""

from unittest.mock import patch

import httpx
import pytest
import respx

from integrations.prospeo import get_contacts_for_domain
from models.schemas import Company, Contact, LookalikeResult
from utils.retry import ProspeoAuthError, ProspeoCreditsError

PROSPEO_URL = "https://api.prospeo.io/domain-search"


def _prospeo_resp(contacts, status=200, credits_remaining=None):
    inner: dict = {
        "status": True,
        "data": {"contact_list": contacts, "total": len(contacts)},
    }
    if credits_remaining is not None:
        inner["credits_remaining"] = credits_remaining
    return httpx.Response(status, json={"response": inner})


def _raw_contact(name="Jane Doe", title="CTO", linkedin="https://linkedin.com/in/jane"):
    return {
        "full_name": name,
        "job_title": title,
        "seniority": "c_suite",
        "company": "Brex",
        "domain": "brex.com",
        "linkedin_url": linkedin,
    }


# ── Integration wrapper tests ─────────────────────────────────────────────────

@respx.mock
def test_get_contacts_200_three_contacts():
    respx.post(PROSPEO_URL).mock(return_value=_prospeo_resp([
        _raw_contact("Jane Doe", "CEO", "https://linkedin.com/in/jane"),
        _raw_contact("John Smith", "CTO", "https://linkedin.com/in/john"),
        _raw_contact("Wei Zhang", "VP Sales", "https://linkedin.com/in/wei"),
    ]))
    contacts = get_contacts_for_domain("brex.com")
    assert len(contacts) == 3
    assert all(isinstance(c, Contact) for c in contacts)


@respx.mock
def test_get_contacts_200_empty_list_returns_empty():
    respx.post(PROSPEO_URL).mock(return_value=_prospeo_resp([]))
    contacts = get_contacts_for_domain("startup.io")
    assert contacts == []


@respx.mock
def test_get_contacts_401_raises_auth_error():
    respx.post(PROSPEO_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(ProspeoAuthError):
        get_contacts_for_domain("brex.com")


@respx.mock
def test_get_contacts_402_raises_credits_error():
    respx.post(PROSPEO_URL).mock(return_value=httpx.Response(402))
    with pytest.raises(ProspeoCreditsError):
        get_contacts_for_domain("brex.com")


@respx.mock
def test_get_contacts_linkedin_url_cleaned():
    """LinkedIn URLs must have query params stripped."""
    respx.post(PROSPEO_URL).mock(return_value=_prospeo_resp([
        _raw_contact(linkedin="https://linkedin.com/in/jane?param=123"),
    ]))
    contacts = get_contacts_for_domain("brex.com")
    assert contacts[0].linkedin_url == "https://linkedin.com/in/jane"


@respx.mock
def test_get_contacts_low_credits_warning(capsys):
    """Credit warning sub-log appears when credits_remaining < 10."""
    respx.post(PROSPEO_URL).mock(return_value=_prospeo_resp(
        [_raw_contact()], credits_remaining=5
    ))
    with patch("integrations.prospeo.log_sub") as mock_log:
        get_contacts_for_domain("brex.com")
    mock_log.assert_called_once()
    args, kwargs = mock_log.call_args
    assert "5" in args[0]
    assert kwargs.get("style") == "yellow"


# ── Stage 2 pipeline tests ────────────────────────────────────────────────────

def _make_lookalike(*domains) -> LookalikeResult:
    companies = [Company(domain=d, source_domain="stripe.com") for d in domains]
    return LookalikeResult(seed_domain="stripe.com", companies=companies, companies_found=len(companies))


def _make_contact(name="Jane Doe", linkedin="https://linkedin.com/in/jane", domain="brex.com"):
    return Contact(
        name=name,
        title="CTO",
        company="Brex",
        company_domain=domain,
        linkedin_url=linkedin,
    )


def test_run_stage2_returns_contact_result():
    from pipeline.stage2_contacts import run_stage2

    contacts = [_make_contact("Jane"), _make_contact("John", linkedin="https://linkedin.com/in/john")]
    lookalike = _make_lookalike("brex.com")

    with patch("pipeline.stage2_contacts.get_contacts_for_domain", return_value=contacts):
        result = run_stage2(lookalike)

    assert result.contacts_found == 2
    assert result.contacts_with_linkedin == 2


def test_run_stage2_zero_contacts_adds_to_skipped():
    from pipeline.stage2_contacts import run_stage2

    lookalike = _make_lookalike("startup.io")

    with patch("pipeline.stage2_contacts.get_contacts_for_domain", return_value=[]):
        result = run_stage2(lookalike)

    assert "startup.io" in result.skipped_domains
    assert result.contacts_found == 0


def test_run_stage2_zero_contacts_does_not_abort():
    from pipeline.stage2_contacts import run_stage2

    lookalike = _make_lookalike("a.com", "b.com")
    good_contact = _make_contact(linkedin="https://linkedin.com/in/good", domain="b.com")

    def fake_search(domain):
        return [] if domain == "a.com" else [good_contact]

    with patch("pipeline.stage2_contacts.get_contacts_for_domain", side_effect=fake_search):
        result = run_stage2(lookalike)

    assert "a.com" in result.skipped_domains
    assert result.contacts_with_linkedin == 1


def test_run_stage2_prospeo_auth_error_propagates():
    from pipeline.stage2_contacts import run_stage2

    lookalike = _make_lookalike("brex.com")

    with patch("pipeline.stage2_contacts.get_contacts_for_domain", side_effect=ProspeoAuthError("401")):
        with pytest.raises(ProspeoAuthError):
            run_stage2(lookalike)


def test_run_stage2_prospeo_credits_error_propagates():
    from pipeline.stage2_contacts import run_stage2

    lookalike = _make_lookalike("brex.com")

    with patch("pipeline.stage2_contacts.get_contacts_for_domain", side_effect=ProspeoCreditsError("402")):
        with pytest.raises(ProspeoCreditsError):
            run_stage2(lookalike)


def test_run_stage2_deduplicates_linkedin_url():
    """Same LinkedIn URL across two domains keeps only the first occurrence."""
    from pipeline.stage2_contacts import run_stage2

    same_linkedin = "https://linkedin.com/in/jane"
    contact_a = _make_contact("Jane A", linkedin=same_linkedin, domain="brex.com")
    contact_b = _make_contact("Jane B", linkedin=same_linkedin, domain="ramp.com")

    lookalike = _make_lookalike("brex.com", "ramp.com")

    def fake_search(domain):
        return [contact_a] if domain == "brex.com" else [contact_b]

    with patch("pipeline.stage2_contacts.get_contacts_for_domain", side_effect=fake_search):
        result = run_stage2(lookalike)

    assert result.contacts_with_linkedin == 1


def test_run_stage2_contacts_without_linkedin_not_in_contacts_list():
    from pipeline.stage2_contacts import run_stage2

    no_li = Contact(name="Anonymous", title="CTO", company="Brex",
                    company_domain="brex.com", linkedin_url=None)
    with_li = _make_contact()
    lookalike = _make_lookalike("brex.com")

    with patch("pipeline.stage2_contacts.get_contacts_for_domain", return_value=[no_li, with_li]):
        result = run_stage2(lookalike)

    assert result.contacts_without_linkedin == 1
    assert all(c.linkedin_url is not None for c in result.contacts)
