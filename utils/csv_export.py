"""CSV export utility — writes verified contacts to output/contacts_<run_id>.csv."""

import csv
from pathlib import Path

from models.schemas import RunArtifact


def export_contacts_csv(artifact: RunArtifact, run_id: str, dry_run: bool = False) -> str:
    """
    Write verified contacts and their send status to output/contacts_<run_id>.csv.
    Returns the file path string.
    """
    Path("output").mkdir(exist_ok=True)
    path = Path("output") / f"contacts_{run_id}.csv"

    send_status_map = {r.contact_email: r.status for r in artifact.send_results}
    default_status = "dry_run" if dry_run else "not_sent"

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["name", "title", "company", "company_domain",
                        "email", "linkedin_url", "send_status"],
        )
        writer.writeheader()
        for contact in artifact.verified_contacts:
            email = contact.email or ""
            status = send_status_map.get(email, default_status)
            writer.writerow({
                "name": contact.name,
                "title": contact.title,
                "company": contact.company,
                "company_domain": contact.company_domain,
                "email": email,
                "linkedin_url": contact.linkedin_url,
                "send_status": status,
            })

    return str(path)
