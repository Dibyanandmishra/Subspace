"""Tests for Pydantic data model validation."""

import json
import pytest

from models.schemas import (
    EazyreachResponse,
    EazyreachResultData,
    OceanCompanyRaw,
    VerifiedContact,
)


def test_ocean_company_normalizes_domain_https_www():
    raw = OceanCompanyRaw(domain="HTTPS://WWW.Brex.com/")
    assert raw.domain == "brex.com"


def test_ocean_company_normalizes_domain_already_clean():
    raw = OceanCompanyRaw(domain="stripe.com")
    assert raw.domain == "stripe.com"


def test_ocean_company_normalizes_domain_uppercase():
    raw = OceanCompanyRaw(domain="RAMP.COM")
    assert raw.domain == "ramp.com"


def test_eazyreach_response_personal_email_gmail():
    resp = EazyreachResponse(
        success=True,
        data=EazyreachResultData(email="jane@gmail.com", email_verified=True),
    )
    assert resp.is_personal_email is True


def test_eazyreach_response_personal_email_yahoo():
    resp = EazyreachResponse(
        success=True,
        data=EazyreachResultData(email="john@yahoo.com", email_verified=True),
    )
    assert resp.is_personal_email is True


def test_eazyreach_response_work_email_not_personal():
    resp = EazyreachResponse(
        success=True,
        data=EazyreachResultData(email="jane@brex.com", email_verified=True),
    )
    assert resp.is_personal_email is False


def test_eazyreach_response_no_email_not_personal():
    resp = EazyreachResponse(success=False, data=None)
    assert resp.is_personal_email is False


def test_verified_contact_not_sendable_empty_name():
    vc = VerifiedContact(
        name="",
        title="VP Engineering",
        company="Brex",
        company_domain="brex.com",
        linkedin_url="https://linkedin.com/in/jane",
        email="jane@brex.com",
        email_verified=True,
        resolution_status="verified",
    )
    assert vc.is_sendable() is False


def test_verified_contact_not_sendable_empty_title():
    vc = VerifiedContact(
        name="Jane Doe",
        title="",
        company="Brex",
        company_domain="brex.com",
        linkedin_url="https://linkedin.com/in/jane",
        email="jane@brex.com",
        email_verified=True,
        resolution_status="verified",
    )
    assert vc.is_sendable() is False


def test_verified_contact_not_sendable_no_email():
    vc = VerifiedContact(
        name="Jane Doe",
        title="VP",
        company="Brex",
        company_domain="brex.com",
        linkedin_url="https://linkedin.com/in/jane",
        email=None,
        email_verified=False,
        resolution_status="unresolved",
    )
    assert vc.is_sendable() is False


def test_verified_contact_sendable():
    vc = VerifiedContact(
        name="Jane Doe",
        title="VP Engineering",
        company="Brex",
        company_domain="brex.com",
        linkedin_url="https://linkedin.com/in/jane",
        email="jane@brex.com",
        email_verified=True,
        resolution_status="verified",
    )
    assert vc.is_sendable() is True


def test_eazyreach_is_resolved_true():
    resp = EazyreachResponse(
        success=True,
        data=EazyreachResultData(email="jane@brex.com", email_verified=True),
    )
    assert resp.is_resolved is True


def test_eazyreach_is_resolved_false_unverified():
    resp = EazyreachResponse(
        success=True,
        data=EazyreachResultData(email="jane@brex.com", email_verified=False),
    )
    assert resp.is_resolved is False


# ── validate_domain tests ─────────────────────────────────────────────────────

def test_validate_domain_clean():
    from utils.preflight import validate_domain
    assert validate_domain("stripe.com") == "stripe.com"


def test_validate_domain_strips_https_www():
    from utils.preflight import validate_domain
    assert validate_domain("https://www.stripe.com") == "stripe.com"


def test_validate_domain_strips_http():
    from utils.preflight import validate_domain
    assert validate_domain("http://stripe.com") == "stripe.com"


def test_validate_domain_strips_www_only():
    from utils.preflight import validate_domain
    assert validate_domain("www.stripe.com") == "stripe.com"


def test_validate_domain_lowercases():
    from utils.preflight import validate_domain
    assert validate_domain("STRIPE.COM") == "stripe.com"


def test_validate_domain_localhost_raises():
    import typer
    from utils.preflight import validate_domain
    with pytest.raises(typer.BadParameter):
        validate_domain("localhost")


def test_validate_domain_no_tld_raises():
    import typer
    from utils.preflight import validate_domain
    with pytest.raises(typer.BadParameter):
        validate_domain("not-a-domain")


def test_validate_domain_path_raises():
    import typer
    from utils.preflight import validate_domain
    with pytest.raises(typer.BadParameter):
        validate_domain("stripe.com/path")


def test_check_connectivity_raises_on_network_error():
    import httpx as _httpx
    from unittest.mock import patch

    from utils.preflight import check_connectivity
    from utils.retry import ConnectivityError

    with patch("utils.preflight.httpx.head", side_effect=_httpx.NetworkError("offline")):
        with pytest.raises(ConnectivityError):
            check_connectivity()


def test_check_connectivity_raises_on_timeout():
    import httpx as _httpx
    from unittest.mock import patch

    from utils.preflight import check_connectivity
    from utils.retry import ConnectivityError

    with patch("utils.preflight.httpx.head", side_effect=_httpx.TimeoutException("timeout")):
        with pytest.raises(ConnectivityError):
            check_connectivity()


# ── save_run_artifact tests ───────────────────────────────────────────────────

def test_save_run_artifact_creates_file(tmp_path, monkeypatch):
    from models.schemas import LookalikeResult
    from utils.artifact import save_run_artifact

    monkeypatch.chdir(tmp_path)
    result = save_run_artifact(run_id="run_test123", seed_domain="stripe.com")

    artifact_path = tmp_path / "output" / "run_test123.json"
    assert artifact_path.exists()
    data = json.loads(artifact_path.read_text())
    assert data["run_id"] == "run_test123"
    assert data["seed_domain"] == "stripe.com"


def test_save_run_artifact_emails_sent_count(tmp_path, monkeypatch):
    from models.schemas import SendResult
    from utils.artifact import save_run_artifact

    monkeypatch.chdir(tmp_path)
    sr = [
        SendResult(contact_name="A", contact_email="a@b.com", company="X", status="sent"),
        SendResult(contact_name="B", contact_email="b@b.com", company="Y", status="failed"),
    ]
    artifact = save_run_artifact(run_id="run_001", seed_domain="stripe.com", send_results=sr)
    assert artifact.emails_sent == 1
    assert artifact.emails_failed == 1


def test_save_run_artifact_aborted_flag(tmp_path, monkeypatch):
    from utils.artifact import save_run_artifact

    monkeypatch.chdir(tmp_path)
    artifact = save_run_artifact(
        run_id="run_002", seed_domain="stripe.com", run_aborted_at_checkpoint=True
    )
    assert artifact.run_aborted_at_checkpoint is True
