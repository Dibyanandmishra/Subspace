"""Tests for Brevo wrapper and Stage 4 pipeline."""

import os
from unittest.mock import MagicMock, call, patch

import httpx
import pytest
import respx

from models.schemas import (
    EmailResolutionResult,
    SendResult,
    VerifiedContact,
)
from utils.retry import BrevoAuthError, BrevoLimitError, BrevoSenderError

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _make_verified_contact(name="Jane Doe", email="jane@brex.com", linkedin="https://linkedin.com/in/jane"):
    return VerifiedContact(
        name=name,
        title="CTO",
        company="Brex",
        company_domain="brex.com",
        linkedin_url=linkedin,
        email=email,
        email_verified=True,
        resolution_status="verified",
    )


def _make_email_result(*contacts):
    verified = list(contacts)
    return EmailResolutionResult(
        contacts_attempted=len(verified),
        emails_verified=len(verified),
        emails_unresolved=0,
        verified_contacts=verified,
        unresolved_contacts=[],
    )


# ── render_email_body tests ───────────────────────────────────────────────────

def test_render_email_body_substitutes_placeholders():
    from integrations.brevo import render_email_body

    contact = _make_verified_contact("Jane Doe", "jane@brex.com")
    subject, body = render_email_body(contact, sender_name="Test Sender")

    assert "Jane" in body or "Jane" in subject
    assert "Brex" in body or "Brex" in subject
    assert "{name}" not in body
    assert "{first_name}" not in body
    assert "{company}" not in body
    assert "{title}" not in body
    assert "{sender_name}" not in body


def test_render_email_body_returns_subject_separately():
    from integrations.brevo import render_email_body

    contact = _make_verified_contact("Jane Doe")
    subject, body = render_email_body(contact, sender_name="Test Sender")

    assert isinstance(subject, str)
    assert isinstance(body, str)
    assert len(subject) > 0
    assert "Subject:" not in subject  # Subject line prefix stripped


def test_render_email_body_first_name_extraction():
    """first_name should be the first word of the full name."""
    from integrations.brevo import render_email_body

    contact = _make_verified_contact("Jane Marie Doe")
    subject, body = render_email_body(contact, sender_name="Test Sender")

    # first_name = "Jane" — used in subject/body
    assert "Jane" in (subject + body)


def test_render_email_body_unknown_placeholder_raises():
    """Template with unknown {variable} should raise ValueError."""
    from integrations.brevo import render_email_body

    contact = _make_verified_contact()

    with patch("integrations.brevo._DEFAULT_TEMPLATE_PATH") as mock_path:
        mock_path.read_text.return_value = (
            "Subject: Hi {first_name}\n\nHello {unknown_var}"
        )
        with pytest.raises(ValueError, match="unknown variable"):
            render_email_body(contact, sender_name="Test Sender")


# ── Brevo wrapper tests ────────────────────────────────────────────────────────

@respx.mock
def test_send_email_201_returns_sent():
    from integrations.brevo import send_email

    contact = _make_verified_contact()
    respx.post(BREVO_URL).mock(return_value=httpx.Response(201, json={"messageId": "<test@msg.id>"}))

    with patch("integrations.brevo.render_email_body", return_value=("Subject", "Body")):
        result = send_email(contact, "stripe.com")

    assert result.status == "sent"
    assert result.brevo_message_id == "<test@msg.id>"


@respx.mock
def test_send_email_400_bad_recipient_returns_failed():
    from integrations.brevo import send_email

    contact = _make_verified_contact()
    respx.post(BREVO_URL).mock(return_value=httpx.Response(
        400, json={"code": "invalid_parameter", "message": "Invalid email"}
    ))

    with patch("integrations.brevo.render_email_body", return_value=("Subject", "Body")):
        result = send_email(contact, "stripe.com")

    assert result.status == "failed"


@respx.mock
def test_send_email_401_raises_auth_error():
    from integrations.brevo import send_email

    contact = _make_verified_contact()
    respx.post(BREVO_URL).mock(return_value=httpx.Response(401, json={}))

    with patch("integrations.brevo.render_email_body", return_value=("Subject", "Body")):
        with pytest.raises(BrevoAuthError):
            send_email(contact, "stripe.com")


@respx.mock
def test_send_email_402_raises_limit_error():
    from integrations.brevo import send_email

    contact = _make_verified_contact()
    respx.post(BREVO_URL).mock(return_value=httpx.Response(402, json={}))

    with patch("integrations.brevo.render_email_body", return_value=("Subject", "Body")):
        with pytest.raises(BrevoLimitError):
            send_email(contact, "stripe.com")


@respx.mock
def test_send_email_400_sender_not_verified_raises():
    from integrations.brevo import send_email

    contact = _make_verified_contact()
    respx.post(BREVO_URL).mock(return_value=httpx.Response(
        400, json={"code": "sender_not_verified", "message": "sender not verified"}
    ))

    with patch("integrations.brevo.render_email_body", return_value=("Subject", "Body")):
        with pytest.raises(BrevoSenderError):
            send_email(contact, "stripe.com")


@respx.mock
def test_send_email_network_error_returns_failed():
    from integrations.brevo import send_email

    contact = _make_verified_contact()
    respx.post(BREVO_URL).mock(side_effect=httpx.NetworkError("connection refused"))

    with patch("integrations.brevo.render_email_body", return_value=("Subject", "Body")):
        result = send_email(contact, "stripe.com")

    assert result.status == "failed"
    assert result.error_message is not None


@respx.mock
def test_send_email_unexpected_status_returns_failed():
    from integrations.brevo import send_email

    contact = _make_verified_contact()
    respx.post(BREVO_URL).mock(return_value=httpx.Response(503, json={}))

    with patch("integrations.brevo.render_email_body", return_value=("Subject", "Body")):
        result = send_email(contact, "stripe.com")

    assert result.status == "failed"


@respx.mock
def test_send_email_tags_include_seed_domain():
    from integrations.brevo import send_email

    contact = _make_verified_contact()
    route = respx.post(BREVO_URL).mock(return_value=httpx.Response(201, json={"messageId": "<x>"}))

    with patch("integrations.brevo.render_email_body", return_value=("Subject", "Body")):
        send_email(contact, "stripe.com")

    payload = route.calls[0].request.content
    import json
    parsed = json.loads(payload)
    assert "stripe.com" in parsed["tags"]


# ── Stage 4 pipeline tests ────────────────────────────────────────────────────

def test_run_stage4_checkpoint_aborted_no_sends():
    from pipeline.stage4_send import run_stage4

    email_result = _make_email_result(_make_verified_contact())

    with patch("pipeline.stage4_send.render_checkpoint", return_value=None):
        with patch("pipeline.stage4_send.send_email") as mock_send:
            results, confirmed = run_stage4(
                email_result=email_result,
                seed_domain="stripe.com",
                run_id="run_test",
                companies_found=5,
                contacts_found=10,
                sender_email="test@test.com",
            )

    mock_send.assert_not_called()
    assert results == []
    assert confirmed is False


def test_run_stage4_confirmed_calls_send_per_contact():
    from pipeline.stage4_send import run_stage4

    c1 = _make_verified_contact("Jane", "jane@brex.com", "https://li/jane")
    c2 = _make_verified_contact("John", "john@ramp.com", "https://li/john")
    email_result = _make_email_result(c1, c2)

    mock_result = SendResult(
        contact_name="Jane", contact_email="jane@brex.com",
        company="Brex", status="sent", brevo_message_id="<msg>"
    )

    with patch("pipeline.stage4_send.render_checkpoint", return_value="y"):
        with patch("pipeline.stage4_send.send_email", return_value=mock_result) as mock_send:
            results, confirmed = run_stage4(
                email_result=email_result,
                seed_domain="stripe.com",
                run_id="run_test",
                companies_found=5,
                contacts_found=10,
                sender_email="test@test.com",
            )

    assert mock_send.call_count == 2
    assert confirmed is True


def test_run_stage4_failed_send_continues_loop():
    from pipeline.stage4_send import run_stage4

    c1 = _make_verified_contact("Jane", "jane@brex.com", "https://li/jane")
    c2 = _make_verified_contact("John", "john@ramp.com", "https://li/john")
    email_result = _make_email_result(c1, c2)

    sent = SendResult(contact_name="John", contact_email="john@ramp.com",
                      company="Ramp", status="sent")
    failed = SendResult(contact_name="Jane", contact_email="jane@brex.com",
                        company="Brex", status="failed", error_message="bad recipient")

    def fake_send(contact, seed_domain, **kwargs):
        return failed if contact.name == "Jane" else sent

    with patch("pipeline.stage4_send.render_checkpoint", return_value="y"):
        with patch("pipeline.stage4_send.send_email", side_effect=fake_send):
            results, confirmed = run_stage4(
                email_result=email_result,
                seed_domain="stripe.com",
                run_id="run_test",
                companies_found=5,
                contacts_found=10,
                sender_email="test@test.com",
            )

    assert len(results) == 2
    assert any(r.status == "sent" for r in results)
    assert any(r.status == "failed" for r in results)


def test_run_stage4_brevo_auth_error_propagates():
    from pipeline.stage4_send import run_stage4

    email_result = _make_email_result(_make_verified_contact())

    with patch("pipeline.stage4_send.render_checkpoint", return_value="y"):
        with patch("pipeline.stage4_send.send_email", side_effect=BrevoAuthError("401")):
            with pytest.raises(BrevoAuthError):
                run_stage4(
                    email_result=email_result,
                    seed_domain="stripe.com",
                    run_id="run_test",
                    companies_found=5,
                    contacts_found=10,
                    sender_email="test@test.com",
                )


def test_run_stage4_brevo_limit_error_propagates():
    from pipeline.stage4_send import run_stage4

    c1 = _make_verified_contact("Jane", "jane@brex.com", "https://li/jane")
    c2 = _make_verified_contact("John", "john@ramp.com", "https://li/john")
    email_result = _make_email_result(c1, c2)

    sent = SendResult(contact_name="Jane", contact_email="jane@brex.com",
                      company="Brex", status="sent")

    call_count = 0

    def fake_send(contact, seed_domain, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return sent
        raise BrevoLimitError("daily limit")

    with patch("pipeline.stage4_send.render_checkpoint", return_value="y"):
        with patch("pipeline.stage4_send.send_email", side_effect=fake_send):
            with pytest.raises(BrevoLimitError):
                run_stage4(
                    email_result=email_result,
                    seed_domain="stripe.com",
                    run_id="run_test",
                    companies_found=5,
                    contacts_found=10,
                    sender_email="test@test.com",
                )
