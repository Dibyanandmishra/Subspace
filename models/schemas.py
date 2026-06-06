"""Pipeline data contracts — Pydantic v2 models for all four stages."""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, field_validator


# ─── STAGE 1 MODELS (Ocean.io) ────────────────────────────────────────────────

class OceanCompanyRaw(BaseModel):
    """Maps directly to one item in Ocean.io's response array."""
    domain: str
    name: Optional[str] = None
    employee_count: Optional[int] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    similarity_score: Optional[float] = None

    @field_validator("domain", mode="before")
    @classmethod
    def normalize_domain(cls, v: str) -> str:
        """Strip protocol and www prefix — always return bare lowercase domain."""
        v = re.sub(r"^https?://", "", str(v).strip().lower())
        v = re.sub(r"^www\.", "", v)
        return v.rstrip("/")


class OceanResponseData(BaseModel):
    companies: list[OceanCompanyRaw]
    total: int
    has_more: bool = False
    next_cursor: Optional[str] = None


class OceanResponse(BaseModel):
    status: str
    data: OceanResponseData


class Company(BaseModel):
    """Internal pipeline model — Stage 1 output, Stage 2 input."""
    domain: str
    name: Optional[str] = None
    source_domain: str
    employee_count: Optional[int] = None

    @field_validator("domain", mode="before")
    @classmethod
    def normalize_domain(cls, v: str) -> str:
        """Strip protocol and www prefix — always return bare lowercase domain."""
        v = re.sub(r"^https?://", "", str(v).strip().lower())
        v = re.sub(r"^www\.", "", v)
        return v.rstrip("/")


class LookalikeResult(BaseModel):
    """Full Stage 1 output passed to Stage 2."""
    seed_domain: str
    companies: list[Company]
    companies_found: int
    pages_fetched: int = 1


# ─── STAGE 2 MODELS (Prospeo) ─────────────────────────────────────────────────

class ProspeoContactRaw(BaseModel):
    """Maps directly to one contact in Prospeo's contact_list array."""
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    job_title: Optional[str] = None
    seniority: Optional[str] = None
    company: Optional[str] = None
    domain: Optional[str] = None
    linkedin_url: Optional[str] = None

    @field_validator("linkedin_url", mode="before")
    @classmethod
    def clean_linkedin_url(cls, v: Optional[str]) -> Optional[str]:
        """Normalize LinkedIn URLs — strip query params, ensure https:// prefix."""
        if not v:
            return None
        v = str(v).strip().split("?")[0]
        if not v.startswith("http"):
            v = f"https://{v}"
        return v

    @property
    def display_name(self) -> str:
        if self.full_name:
            return self.full_name
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or "Unknown"


class ProspeoResponseData(BaseModel):
    contact_list: list[ProspeoContactRaw] = []
    total: int = 0


class ProspeoResponse(BaseModel):
    """Prospeo envelope — the API wraps data inside a 'response' key."""
    response: dict  # type: ignore[type-arg]


class Contact(BaseModel):
    """Internal pipeline model — Stage 2 output, Stage 3 input."""
    name: str
    title: str
    company: str
    company_domain: str
    linkedin_url: Optional[str] = None
    seniority: Optional[str] = None


class ContactResult(BaseModel):
    """Full Stage 2 output passed to Stage 3."""
    companies_searched: int
    contacts_found: int
    contacts_with_linkedin: int
    contacts_without_linkedin: int
    contacts: list[Contact]
    skipped_domains: list[str]


# ─── STAGE 3 MODELS (Eazyreach) ───────────────────────────────────────────────

class EazyreachResultData(BaseModel):
    email: Optional[str] = None
    email_verified: bool = False
    email_status: str = "unknown"  # "valid" | "not_found" | "invalid" | "unknown"
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    linkedin_url: Optional[str] = None
    credits_used: Optional[int] = None
    credits_remaining: Optional[int] = None


_FREE_PROVIDERS = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com",
    "outlook.com", "icloud.com", "proton.me",
})


class EazyreachResponse(BaseModel):
    success: bool
    data: Optional[EazyreachResultData] = None
    error: Optional[dict] = None  # type: ignore[type-arg]

    @property
    def is_resolved(self) -> bool:
        return (
            self.success
            and self.data is not None
            and self.data.email_verified
            and self.data.email is not None
        )

    @property
    def is_personal_email(self) -> bool:
        """True if the resolved email is from a free provider — should be skipped."""
        if not self.data or not self.data.email:
            return False
        domain = self.data.email.split("@")[-1].lower()
        return domain in _FREE_PROVIDERS


class VerifiedContact(BaseModel):
    """Internal pipeline model — Stage 3 output, Stage 4 input."""
    name: str
    title: str
    company: str
    company_domain: str
    linkedin_url: str
    email: Optional[str] = None
    email_verified: bool = False
    resolution_status: str  # "verified" | "unresolved" | "personal_email" | "error" | "duplicate"
    skip_reason: Optional[str] = None

    def is_sendable(self) -> bool:
        """All template fields must be non-empty and email must be verified."""
        return (
            self.email_verified
            and bool(self.email)
            and bool(self.name.strip())
            and bool(self.title.strip())
            and bool(self.company.strip())
        )


class EmailResolutionResult(BaseModel):
    """Full Stage 3 output passed to Stage 4."""
    contacts_attempted: int
    emails_verified: int
    emails_unresolved: int
    verified_contacts: list[VerifiedContact]
    unresolved_contacts: list[VerifiedContact]


# ─── STAGE 4 MODELS (Brevo) ───────────────────────────────────────────────────

class BrevoSender(BaseModel):
    name: str
    email: str


class BrevoRecipient(BaseModel):
    name: str
    email: str


class BrevoEmailRequest(BaseModel):
    """The exact payload sent to Brevo POST /v3/smtp/email."""
    sender: BrevoSender
    to: list[BrevoRecipient]
    subject: str
    htmlContent: str
    textContent: str
    tags: list[str] = []


class BrevoEmailResponse(BaseModel):
    messageId: Optional[str] = None
    code: Optional[str] = None
    message: Optional[str] = None


class SendResult(BaseModel):
    """Stage 4 output per contact."""
    contact_name: str
    contact_email: str
    company: str
    status: str  # "sent" | "failed" | "skipped"
    brevo_message_id: Optional[str] = None
    error_message: Optional[str] = None


# ─── RUN ARTIFACT (saved to output/ after every run) ──────────────────────────

class RunArtifact(BaseModel):
    """Complete run record serialized to output/run_<run_id>.json."""
    run_id: str
    seed_domain: str
    timestamp: str  # ISO 8601

    companies_found: int
    contacts_found: int
    contacts_with_linkedin: int
    emails_verified: int
    emails_unresolved: int
    emails_sent: int
    emails_failed: int

    companies: list[Company]
    contacts: list[Contact]
    verified_contacts: list[VerifiedContact]
    unresolved_contacts: list[VerifiedContact]
    send_results: list[SendResult]

    user_confirmed_send: bool
    run_aborted_at_checkpoint: bool = False
