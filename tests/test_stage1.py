"""Tests for Ocean.io wrapper and Stage 1 pipeline."""

from unittest.mock import patch

import httpx
import pytest
import respx

from integrations.ocean import get_lookalike_companies
from models.schemas import Company, LookalikeResult
from utils.retry import OceanAuthError

OCEAN_URL = "https://api.ocean.io/v4/companies/find_similar"


def _ocean_resp(companies, has_more=False, next_cursor=None, status=200):
    return httpx.Response(
        status,
        json={
            "status": "ok",
            "data": {
                "companies": companies,
                "total": len(companies),
                "has_more": has_more,
                "next_cursor": next_cursor,
            },
        },
    )


# ── Integration wrapper tests ─────────────────────────────────────────────────

@respx.mock
def test_get_lookalike_200_two_companies():
    respx.post(OCEAN_URL).mock(return_value=_ocean_resp([
        {"domain": "brex.com", "name": "Brex"},
        {"domain": "ramp.com", "name": "Ramp"},
    ]))
    result = get_lookalike_companies("stripe.com")
    assert result.companies_found == 2
    assert len(result.companies) == 2


@respx.mock
def test_get_lookalike_200_empty_list():
    respx.post(OCEAN_URL).mock(return_value=_ocean_resp([]))
    result = get_lookalike_companies("stripe.com")
    assert result.companies_found == 0
    assert result.companies == []


@respx.mock
def test_get_lookalike_401_raises_ocean_auth_error():
    respx.post(OCEAN_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(OceanAuthError):
        get_lookalike_companies("stripe.com")


@respx.mock
def test_get_lookalike_429_then_200_retries():
    respx.post(OCEAN_URL).mock(side_effect=[
        httpx.Response(429),
        _ocean_resp([{"domain": "brex.com", "name": "Brex"}]),
    ])
    result = get_lookalike_companies("stripe.com")
    assert result.companies_found == 1


@respx.mock
def test_get_lookalike_seed_domain_filtered():
    respx.post(OCEAN_URL).mock(return_value=_ocean_resp([
        {"domain": "stripe.com", "name": "Stripe"},  # seed — must be excluded
        {"domain": "brex.com", "name": "Brex"},
    ]))
    result = get_lookalike_companies("stripe.com")
    domains = [c.domain for c in result.companies]
    assert "stripe.com" not in domains
    assert "brex.com" in domains


@respx.mock
def test_get_lookalike_domain_normalization():
    respx.post(OCEAN_URL).mock(return_value=_ocean_resp([
        {"domain": "HTTPS://WWW.Brex.com/", "name": "Brex"},
    ]))
    result = get_lookalike_companies("stripe.com")
    assert result.companies[0].domain == "brex.com"


@respx.mock
def test_get_lookalike_pagination():
    respx.post(OCEAN_URL).mock(side_effect=[
        _ocean_resp([{"domain": "brex.com"}], has_more=True, next_cursor="cursor1"),
        _ocean_resp([{"domain": "ramp.com"}], has_more=False),
    ])
    result = get_lookalike_companies("stripe.com")
    assert result.companies_found == 2
    assert result.pages_fetched == 2


# ── Stage 1 pipeline tests ────────────────────────────────────────────────────

def _make_lookalike(n: int = 2) -> LookalikeResult:
    return LookalikeResult(
        seed_domain="stripe.com",
        companies=[Company(domain=f"co{i}.com", source_domain="stripe.com") for i in range(n)],
        companies_found=n,
    )


def test_run_stage1_returns_lookalike_result():
    from pipeline.stage1_lookalikes import run_stage1

    mock_result = _make_lookalike(3)
    with patch("pipeline.stage1_lookalikes.get_lookalike_companies", return_value=mock_result):
        result = run_stage1("stripe.com")

    assert result.companies_found == 3


def test_run_stage1_zero_companies_no_exception():
    from pipeline.stage1_lookalikes import run_stage1

    mock_result = LookalikeResult(seed_domain="stripe.com", companies=[], companies_found=0)
    with patch("pipeline.stage1_lookalikes.get_lookalike_companies", return_value=mock_result):
        result = run_stage1("stripe.com")

    assert result.companies_found == 0


def test_run_stage1_propagates_ocean_auth_error():
    from pipeline.stage1_lookalikes import run_stage1

    with patch("pipeline.stage1_lookalikes.get_lookalike_companies", side_effect=OceanAuthError("401")):
        with pytest.raises(OceanAuthError):
            run_stage1("stripe.com")


def test_run_stage1_exclude_domains_filters_results(monkeypatch):
    """EXCLUDE_DOMAINS blocklist removes matching companies from Stage 1 result."""
    from pipeline.stage1_lookalikes import run_stage1

    monkeypatch.setattr(
        "pipeline.stage1_lookalikes.settings",
        type("S", (), {"exclude_domains_list": ["competitor.com"]})(),
    )

    mock_result = LookalikeResult(
        seed_domain="stripe.com",
        companies=[
            Company(domain="brex.com", source_domain="stripe.com"),
            Company(domain="competitor.com", source_domain="stripe.com"),
        ],
        companies_found=2,
    )

    with patch("pipeline.stage1_lookalikes.get_lookalike_companies", return_value=mock_result):
        result = run_stage1("stripe.com")

    domains = [c.domain for c in result.companies]
    assert "competitor.com" not in domains
    assert "brex.com" in domains
    assert result.companies_found == 1
