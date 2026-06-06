"""Run artifact assembly and persistence — saves output/run_<run_id>.json."""

from datetime import datetime, timezone
from pathlib import Path

from models.schemas import (
    ContactResult,
    EmailResolutionResult,
    LookalikeResult,
    RunArtifact,
    SendResult,
)


def save_run_artifact(
    run_id: str,
    seed_domain: str,
    lookalike_result: LookalikeResult | None = None,
    contact_result: ContactResult | None = None,
    email_result: EmailResolutionResult | None = None,
    send_results: list[SendResult] | None = None,
    user_confirmed_send: bool = False,
    run_aborted_at_checkpoint: bool = False,
) -> RunArtifact:
    """
    Assemble a RunArtifact from whatever pipeline data is available and
    write it to output/run_<run_id>.json. Safe to call after a partial run.
    Returns the assembled RunArtifact.
    """
    sr = send_results or []

    artifact = RunArtifact(
        run_id=run_id,
        seed_domain=seed_domain,
        timestamp=datetime.now(timezone.utc).isoformat(),

        companies_found=lookalike_result.companies_found if lookalike_result else 0,
        contacts_found=contact_result.contacts_found if contact_result else 0,
        contacts_with_linkedin=contact_result.contacts_with_linkedin if contact_result else 0,
        emails_verified=email_result.emails_verified if email_result else 0,
        emails_unresolved=email_result.emails_unresolved if email_result else 0,
        emails_sent=sum(1 for r in sr if r.status == "sent"),
        emails_failed=sum(1 for r in sr if r.status == "failed"),

        companies=lookalike_result.companies if lookalike_result else [],
        contacts=contact_result.contacts if contact_result else [],
        verified_contacts=email_result.verified_contacts if email_result else [],
        unresolved_contacts=email_result.unresolved_contacts if email_result else [],
        send_results=sr,

        user_confirmed_send=user_confirmed_send,
        run_aborted_at_checkpoint=run_aborted_at_checkpoint,
    )

    Path("output").mkdir(exist_ok=True)
    path = Path("output") / f"{run_id}.json"
    path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")

    return artifact
