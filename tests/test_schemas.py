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
    from utils.artifact import save_run_artifact

    monkeypatch.chdir(tmp_path)
    save_run_artifact(run_id="run_test123", seed_domain="stripe.com")

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


# ── TUI component smoke tests ─────────────────────────────────────────────────

def _capturing_console():
    import io
    from rich.console import Console

    buf = io.StringIO()
    return Console(file=buf, width=120, markup=True, emoji=True), buf


def _verified_contact(name="Jane Doe", email="jane@brex.com"):
    from models.schemas import VerifiedContact

    return VerifiedContact(
        name=name,
        title="CTO",
        company="Brex",
        company_domain="brex.com",
        linkedin_url="https://linkedin.com/in/jane",
        email=email,
        email_verified=True,
        resolution_status="verified",
    )


def _artifact_with_verified(tmp_path, monkeypatch, n_verified=1, send_results=None, **overrides):
    from models.schemas import EmailResolutionResult
    from utils.artifact import save_run_artifact

    monkeypatch.chdir(tmp_path)
    verified = [_verified_contact(name=f"Person {i}", email=f"p{i}@brex.com") for i in range(n_verified)]
    email_result = EmailResolutionResult(
        contacts_attempted=n_verified,
        emails_verified=n_verified,
        emails_unresolved=0,
        verified_contacts=verified,
        unresolved_contacts=[],
    )
    return save_run_artifact(
        run_id="run_csv", seed_domain="stripe.com",
        email_result=email_result, send_results=send_results, **overrides,
    )


def test_export_contacts_csv_writes_rows(tmp_path, monkeypatch):
    from utils.csv_export import export_contacts_csv

    artifact = _artifact_with_verified(tmp_path, monkeypatch, n_verified=2)
    path = export_contacts_csv(artifact, run_id="run_csv")

    import csv as csv_module
    with open(path, encoding="utf-8") as fh:
        rows = list(csv_module.DictReader(fh))

    assert len(rows) == 2
    assert rows[0]["email"] == "p0@brex.com"
    assert rows[0]["send_status"] == "not_sent"


def test_export_contacts_csv_reflects_send_status(tmp_path, monkeypatch):
    from models.schemas import SendResult
    from utils.csv_export import export_contacts_csv

    sr = [SendResult(contact_name="Person 0", contact_email="p0@brex.com", company="Brex", status="sent")]
    artifact = _artifact_with_verified(tmp_path, monkeypatch, n_verified=1, send_results=sr)
    path = export_contacts_csv(artifact, run_id="run_csv")

    import csv as csv_module
    with open(path, encoding="utf-8") as fh:
        rows = list(csv_module.DictReader(fh))

    assert rows[0]["send_status"] == "sent"


def test_export_contacts_csv_dry_run_status(tmp_path, monkeypatch):
    from utils.csv_export import export_contacts_csv

    artifact = _artifact_with_verified(tmp_path, monkeypatch, n_verified=1)
    path = export_contacts_csv(artifact, run_id="run_csv", dry_run=True)

    import csv as csv_module
    with open(path, encoding="utf-8") as fh:
        rows = list(csv_module.DictReader(fh))

    assert rows[0]["send_status"] == "dry_run"


def test_print_final_summary_complete(tmp_path, monkeypatch):
    from utils import summary

    test_console, buf = _capturing_console()
    monkeypatch.setattr(summary, "console", test_console)

    artifact = _artifact_with_verified(tmp_path, monkeypatch, n_verified=1)
    summary.print_final_summary(artifact)

    output = buf.getvalue()
    assert "RUN COMPLETE" in output
    assert "stripe.com" in output


def test_print_final_summary_with_failures(tmp_path, monkeypatch):
    from models.schemas import SendResult
    from utils import summary

    test_console, buf = _capturing_console()
    monkeypatch.setattr(summary, "console", test_console)

    sr = [SendResult(contact_name="Person 0", contact_email="p0@brex.com", company="Brex", status="failed")]
    artifact = _artifact_with_verified(tmp_path, monkeypatch, n_verified=1, send_results=sr)
    summary.print_final_summary(artifact)

    assert "WITH WARNINGS" in buf.getvalue()


def test_print_final_summary_aborted(tmp_path, monkeypatch):
    from utils import summary
    from utils.artifact import save_run_artifact

    test_console, buf = _capturing_console()
    monkeypatch.setattr(summary, "console", test_console)

    monkeypatch.chdir(tmp_path)
    artifact = save_run_artifact(run_id="run_abort", seed_domain="stripe.com", run_aborted_at_checkpoint=True)
    summary.print_final_summary(artifact)

    assert "RUN ABORTED" in buf.getvalue()


def test_print_banner_includes_domain_and_run_id(monkeypatch):
    from utils import banner

    test_console, buf = _capturing_console()
    monkeypatch.setattr(banner, "console", test_console)

    banner.print_banner("stripe.com", "run_20260101_000000")

    output = buf.getvalue()
    assert "stripe.com" in output
    assert "run_20260101_000000" in output
    assert "SUBSPACE OUTREACH PIPELINE" in output


def test_setup_logging_creates_log_file_and_handlers(tmp_path, monkeypatch):
    import logging

    from utils.logger import get_logger, setup_logging

    monkeypatch.chdir(tmp_path)
    setup_logging(verbose=True)

    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 2
    assert (tmp_path / "logs").is_dir()
    assert any((tmp_path / "logs").glob("run_*.log"))

    logger = get_logger("subspace.test")
    assert logger.name == "subspace.test"


# ── render_checkpoint tests ───────────────────────────────────────────────────

def _email_result(verified, unresolved=None):
    from models.schemas import EmailResolutionResult

    unresolved = unresolved or []
    return EmailResolutionResult(
        contacts_attempted=len(verified) + len(unresolved),
        emails_verified=len(verified),
        emails_unresolved=len(unresolved),
        verified_contacts=verified,
        unresolved_contacts=unresolved,
    )


def test_render_checkpoint_zero_verified_returns_none(monkeypatch):
    from utils import checkpoint

    test_console, buf = _capturing_console()
    monkeypatch.setattr(checkpoint, "console", test_console)

    result = checkpoint.render_checkpoint(
        seed_domain="stripe.com", run_id="run_001", companies_found=5, contacts_found=10,
        result=_email_result(verified=[]), sender_email="me@stripe.com",
    )

    assert result is None
    assert "Nothing to send" in buf.getvalue()


def test_render_checkpoint_dry_run_skips_prompt(monkeypatch):
    from utils import checkpoint

    test_console, buf = _capturing_console()
    monkeypatch.setattr(checkpoint, "console", test_console)
    monkeypatch.setattr(test_console, "input", lambda *a, **k: pytest.fail("input() should not be called in dry-run"))

    result = checkpoint.render_checkpoint(
        seed_domain="stripe.com", run_id="run_001", companies_found=5, contacts_found=10,
        result=_email_result(verified=[_verified_contact()]), sender_email="me@stripe.com",
        dry_run=True,
    )

    assert result is None
    assert "THIS WILL SEND" in buf.getvalue()


def test_render_checkpoint_confirmed_returns_y(monkeypatch):
    from utils import checkpoint

    test_console, buf = _capturing_console()
    monkeypatch.setattr(checkpoint, "console", test_console)
    monkeypatch.setattr(test_console, "input", lambda *a, **k: "y")

    verified = [_verified_contact(name=f"Person {i}", email=f"p{i}@brex.com") for i in range(4)]
    result = checkpoint.render_checkpoint(
        seed_domain="stripe.com", run_id="run_001", companies_found=5, contacts_found=10,
        result=_email_result(verified=verified, unresolved=[_verified_contact(name="Skip", email="skip@gmail.com")]),
        sender_email="me@stripe.com",
    )

    assert result == "y"
    assert "and 1 more contact" in buf.getvalue()


def test_render_checkpoint_aborted_returns_none(monkeypatch):
    from utils import checkpoint

    test_console, buf = _capturing_console()
    monkeypatch.setattr(checkpoint, "console", test_console)
    monkeypatch.setattr(test_console, "input", lambda *a, **k: "n")

    result = checkpoint.render_checkpoint(
        seed_domain="stripe.com", run_id="run_001", companies_found=5, contacts_found=10,
        result=_email_result(verified=[_verified_contact()]), sender_email="me@stripe.com",
    )

    assert result is None
