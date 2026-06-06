"""Brevo API wrapper — transactional email send."""

from pathlib import Path

import httpx

from models.schemas import (
    BrevoEmailRequest,
    BrevoEmailResponse,
    BrevoRecipient,
    BrevoSender,
    SendResult,
    VerifiedContact,
)
from models.settings import settings
from utils.retry import BrevoAuthError, BrevoLimitError, BrevoSenderError, make_retry_decorator

_BASE_URL = "https://api.brevo.com/v3"
_ENDPOINT = "/smtp/email"

_TEMPLATE_PATH = Path("email_templates/outreach.txt")


def render_email_body(contact: VerifiedContact, sender_name: str) -> tuple[str, str]:
    """
    Read the template file and inject contact variables.
    Returns (subject, body_text).
    Raises ValueError if the template references an unknown {variable}.
    """
    raw = _TEMPLATE_PATH.read_text(encoding="utf-8")
    first_name = contact.name.split()[0] if contact.name else contact.name

    try:
        rendered = raw.format(
            name=contact.name,
            first_name=first_name,
            title=contact.title,
            company=contact.company,
            sender_name=sender_name,
        )
    except KeyError as exc:
        raise ValueError(f"Email template references unknown variable: {exc}") from exc

    lines = rendered.strip().split("\n")
    subject = lines[0].replace("Subject: ", "", 1).strip()
    body = "\n".join(lines[2:]).strip()
    return subject, body


def send_email(contact: VerifiedContact, seed_domain: str) -> SendResult:
    """
    Send one personalized email to contact via Brevo.
    Returns SendResult(status='sent') on success or SendResult(status='failed') on
    per-contact errors — never raises for bad recipients.
    Raises BrevoAuthError, BrevoSenderError, BrevoLimitError on run-level failures.
    """
    retry = make_retry_decorator(
        max_attempts=settings.max_retry_attempts,
        backoff_factor=settings.retry_backoff_factor,
    )

    subject, body = render_email_body(contact, settings.sender_name)

    request = BrevoEmailRequest(
        sender=BrevoSender(name=settings.sender_name, email=settings.sender_email),
        to=[BrevoRecipient(name=contact.name, email=contact.email or "")],
        subject=subject,
        htmlContent=f"<p>{'</p><p>'.join(body.splitlines())}</p>",
        textContent=body,
        tags=["outreach", "subspace-pipeline", seed_domain],
    )

    headers = {
        "api-key": settings.brevo_api_key.get_secret_value(),
        "Content-Type": "application/json",
    }

    @retry
    def _call() -> httpx.Response:
        resp = httpx.post(
            f"{_BASE_URL}{_ENDPOINT}",
            headers=headers,
            content=request.model_dump_json(),
            timeout=settings.request_timeout_seconds,
        )
        # Only retry on 429/5xx — handled by make_retry_decorator
        return resp

    try:
        resp = _call()
    except Exception as exc:
        return SendResult(
            contact_name=contact.name,
            contact_email=contact.email or "",
            company=contact.company,
            status="failed",
            error_message=str(exc),
        )

    parsed = BrevoEmailResponse.model_validate(resp.json()) if resp.content else BrevoEmailResponse()

    if resp.status_code == 201:
        return SendResult(
            contact_name=contact.name,
            contact_email=contact.email or "",
            company=contact.company,
            status="sent",
            brevo_message_id=parsed.messageId,
        )

    if resp.status_code == 401:
        raise BrevoAuthError("Brevo rejected the API key (401)")

    if resp.status_code == 402:
        raise BrevoLimitError("Brevo daily send limit reached (402)")

    if resp.status_code == 400:
        # Distinguish sender-not-verified (run-level) from bad recipient (per-contact)
        msg = (parsed.message or "").lower()
        if "sender" in msg and "verif" in msg:
            raise BrevoSenderError(f"Brevo sender not verified: {parsed.message}")
        # Any other 400 = bad recipient data — log and continue
        return SendResult(
            contact_name=contact.name,
            contact_email=contact.email or "",
            company=contact.company,
            status="failed",
            error_message=parsed.message or f"HTTP 400: {resp.text[:200]}",
        )

    # Unexpected status — treat as per-contact failure, don't abort the run
    return SendResult(
        contact_name=contact.name,
        contact_email=contact.email or "",
        company=contact.company,
        status="failed",
        error_message=f"Unexpected HTTP {resp.status_code}: {resp.text[:200]}",
    )
