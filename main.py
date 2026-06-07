"""Subspace automated cold-outreach pipeline CLI entry point."""

from typing import Optional

import typer

app = typer.Typer(add_completion=False)

TONE_TEMPLATES = {
    "friendly": "email_templates/outreach_friendly.txt",
    "formal":   "email_templates/outreach_formal.txt",
    "direct":   "email_templates/outreach_direct.txt",
}


@app.command()
def main(
    domain: str = typer.Option(..., "--domain", help="Seed company domain (e.g. stripe.com)"),
    verbose: bool = typer.Option(False, "--verbose", help="Show debug API payloads in logs"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run Stages 1–3 only. Do not send emails."),
    export_csv: bool = typer.Option(False, "--export-csv", help="Export verified contacts to CSV after run."),
    min_size: Optional[int] = typer.Option(None, "--min-size", help="Minimum employee count filter."),
    max_size: Optional[int] = typer.Option(None, "--max-size", help="Maximum employee count filter."),
    tone: str = typer.Option("friendly", "--tone", help="Email tone: friendly | formal | direct"),
) -> None:
    """Automated cold-outreach pipeline: one seed domain in, personalized emails out."""

    # Lazy imports — deferred so that `--help` works without a .env file.
    from datetime import datetime

    from models.schemas import ContactResult, EmailResolutionResult, LookalikeResult, SendResult
    from models.settings import settings
    from pipeline.stage1_lookalikes import run_stage1
    from pipeline.stage2_contacts import run_stage2
    from pipeline.stage3_emails import run_stage3
    from pipeline.stage4_send import run_stage4
    from utils.artifact import save_run_artifact
    from utils.banner import print_banner
    from utils.console import console
    from utils.logger import setup_logging
    from utils.preflight import check_connectivity, validate_domain
    from utils.retry import (
        BrevoAuthError, BrevoLimitError, BrevoSenderError,
        ConnectivityError,
        EazyreachAuthError, EazyreachCreditsError,
        OceanAuthError, ProspeoAuthError, ProspeoCreditsError,
    )
    from utils.summary import print_final_summary

    setup_logging(verbose)

    # Validate and normalize domain before using it anywhere
    domain = validate_domain(domain)

    # Validate tone
    if tone not in TONE_TEMPLATES:
        raise typer.BadParameter(
            f"Invalid tone '{tone}'. Valid options: {', '.join(TONE_TEMPLATES)}"
        )
    template_path = TONE_TEMPLATES[tone]

    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print_banner(domain, run_id)

    # Stage data — accumulated as stages complete so partial artifacts can always be saved
    lookalike_result: Optional[LookalikeResult] = None
    contact_result: Optional[ContactResult] = None
    email_result: Optional[EmailResolutionResult] = None
    send_results: list[SendResult] = []
    user_confirmed = False
    aborted = False

    try:
        # ── Pre-flight ────────────────────────────────────────────────────────
        check_connectivity()

        # ── Stage 1 ───────────────────────────────────────────────────────────
        lookalike_result = run_stage1(domain, min_size=min_size, max_size=max_size)

        if lookalike_result.companies_found == 0:
            artifact = save_run_artifact(run_id=run_id, seed_domain=domain,
                                         lookalike_result=lookalike_result)
            print_final_summary(artifact)
            raise typer.Exit(0)

        # ── Stage 2 ───────────────────────────────────────────────────────────
        contact_result = run_stage2(lookalike_result)

        # ── Stage 3 ───────────────────────────────────────────────────────────
        email_result = run_stage3(contact_result)

        # ── Dry-run exit ──────────────────────────────────────────────────────
        if dry_run:
            from utils.checkpoint import render_checkpoint
            render_checkpoint(
                seed_domain=domain,
                run_id=run_id,
                companies_found=lookalike_result.companies_found,
                contacts_found=contact_result.contacts_found,
                result=email_result,
                sender_email=settings.sender_email,
                dry_run=True,
            )
            console.print()
            console.print(
                "[yellow]DRY RUN MODE[/yellow] [dim]— Stage 4 skipped. No emails were sent.[/dim]"
            )
            artifact = save_run_artifact(
                run_id=run_id, seed_domain=domain,
                lookalike_result=lookalike_result, contact_result=contact_result,
                email_result=email_result, send_results=[],
                user_confirmed_send=False,
            )
            if export_csv:
                from utils.csv_export import export_contacts_csv
                csv_path = export_contacts_csv(artifact, run_id, dry_run=True)
                console.print(
                    f"  [dim]CSV export[/dim] [dim cyan]→[/dim cyan] [cyan]{csv_path}[/cyan]"
                )
            print_final_summary(artifact)
            raise typer.Exit(0)

        # ── Stage 4 + checkpoint ──────────────────────────────────────────────
        send_results, user_confirmed = run_stage4(
            email_result=email_result,
            seed_domain=domain,
            run_id=run_id,
            companies_found=lookalike_result.companies_found,
            contacts_found=contact_result.contacts_found,
            sender_email=settings.sender_email,
            template_path=template_path,
        )
        aborted = not user_confirmed

    except ConnectivityError as e:
        _fail(
            "No internet connectivity.",
            str(e),
            run_id, domain, lookalike_result, contact_result, email_result,
            send_results, user_confirmed,
        )

    except OceanAuthError:
        _fail(
            "Ocean.io authentication failed.",
            "OCEAN_API_KEY in .env is incorrect or expired.\n"
            "     Check your Ocean.io dashboard and rotate the key if needed.",
            run_id, domain, lookalike_result, contact_result, email_result,
            send_results, user_confirmed,
        )

    except ProspeoAuthError:
        _fail(
            "Prospeo authentication failed.",
            "PROSPEO_API_KEY in .env is incorrect or expired.",
            run_id, domain, lookalike_result, contact_result, email_result,
            send_results, user_confirmed,
        )

    except ProspeoCreditsError:
        _fail(
            "Prospeo credits exhausted.",
            "Top up your Prospeo account before running again.",
            run_id, domain, lookalike_result, contact_result, email_result,
            send_results, user_confirmed,
        )

    except EazyreachAuthError:
        _fail(
            "Eazyreach authentication failed.",
            "EAZYREACH_API_KEY in .env is incorrect or expired.",
            run_id, domain, lookalike_result, contact_result, email_result,
            send_results, user_confirmed,
        )

    except EazyreachCreditsError:
        _fail(
            "Eazyreach credits exhausted.",
            "Contact Subspace to top up your Eazyreach credit balance.",
            run_id, domain, lookalike_result, contact_result, email_result,
            send_results, user_confirmed,
        )

    except BrevoAuthError:
        _fail(
            "Brevo authentication failed.",
            "BREVO_API_KEY in .env is incorrect or expired.",
            run_id, domain, lookalike_result, contact_result, email_result,
            send_results, user_confirmed,
        )

    except BrevoSenderError:
        _fail(
            "Brevo sender not verified.",
            "SENDER_EMAIL domain DNS records must be configured in Brevo.\n"
            "     See: Brevo dashboard → Senders & IPs → Verify a domain.",
            run_id, domain, lookalike_result, contact_result, email_result,
            send_results, user_confirmed,
        )

    except BrevoLimitError:
        _fail(
            "Brevo daily send limit reached.",
            "Free tier allows 300 emails/day. Upgrade your Brevo plan or try tomorrow.",
            run_id, domain, lookalike_result, contact_result, email_result,
            send_results, user_confirmed,
        )

    # ── Normal exit ───────────────────────────────────────────────────────────
    artifact = save_run_artifact(
        run_id=run_id, seed_domain=domain,
        lookalike_result=lookalike_result, contact_result=contact_result,
        email_result=email_result, send_results=send_results,
        user_confirmed_send=user_confirmed, run_aborted_at_checkpoint=aborted,
    )

    if export_csv:
        from utils.csv_export import export_contacts_csv
        csv_path = export_contacts_csv(artifact, run_id)
        from utils.console import console as _console
        _console.print(
            f"  [dim]CSV export[/dim] [dim cyan]→[/dim cyan] [cyan]{csv_path}[/cyan]"
        )

    print_final_summary(artifact)


def _fail(
    headline: str,
    detail: str,
    run_id: str,
    seed_domain: str,
    lookalike_result,
    contact_result,
    email_result,
    send_results,
    user_confirmed: bool,
) -> None:
    """Print a run-level error, save the partial artifact, and exit 1."""
    from utils.artifact import save_run_artifact
    from utils.console import console

    console.print(
        f"\n [bold red]✗[/bold red]  [bold red]{headline}[/bold red]\n"
        f"     [dim]{detail}[/dim]"
    )
    artifact = save_run_artifact(
        run_id=run_id, seed_domain=seed_domain,
        lookalike_result=lookalike_result, contact_result=contact_result,
        email_result=email_result, send_results=send_results,
        user_confirmed_send=user_confirmed,
    )
    console.print(
        f"\n  [dim]Run artifact[/dim] [dim cyan]→[/dim cyan] [cyan]output/{artifact.run_id}.json[/cyan]"
    )
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
