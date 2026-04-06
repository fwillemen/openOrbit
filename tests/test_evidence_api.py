"""Integration tests for the v1 evidence chain API endpoint."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

import openorbit.config
import openorbit.db as db_module
from openorbit.db import (
    add_attribution,
    close_db,
    get_db,
    init_db,
    log_scrape_run,
    register_osint_source,
    upsert_launch_event,
)
from openorbit.main import create_app
from openorbit.models.db import LaunchEventCreate


@pytest.fixture
async def client() -> AsyncClient:  # type: ignore[return]
    """Create async HTTP client wired to a fresh database.

    Yields:
        AsyncClient configured with ASGITransport for the test app.
    """
    db_file = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
    openorbit.config._settings = None
    db_module._db_connection = None

    await init_db()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    await close_db()
    if os.path.exists(db_file):
        os.unlink(db_file)
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
    openorbit.config._settings = None


async def _seed_launch_with_attributions(
    slug: str,
    *,
    attributions: list[dict],  # type: ignore[type-arg]
) -> None:
    """Seed a launch event with attributions into the DB.

    Args:
        slug: Slug to use (overrides auto-generated).
        attributions: List of dicts with keys: source_name, source_tier,
            evidence_type, source_url, observed_at, confidence_score, confidence_rationale.
    """
    async with get_db() as conn:
        await upsert_launch_event(
            conn,
            LaunchEventCreate(
                name="Test Launch",
                launch_date=datetime(2025, 3, 15, 10, 0, 0, tzinfo=UTC),
                launch_date_precision="minute",
                provider="TestProvider",
                vehicle="TestRocket",
                launch_type="civilian",
                status="scheduled",
                slug=slug,
                claim_lifecycle="corroborated",
                event_kind="observed",
            ),
        )

        for i, attr in enumerate(attributions):
            source_name = attr.get("source_name", f"Source{i}")
            source_tier = attr.get("source_tier", 1)
            source_id = await register_osint_source(
                conn,
                name=source_name,
                url=f"https://example.com/source{i}",
                scraper_class=f"openorbit.scrapers.test.Scraper{i}",
                source_tier=source_tier,
            )
            scrape_id = await log_scrape_run(
                conn,
                source_id=source_id,
                url=f"https://example.com/launch{i}",
                http_status=200,
                content_type="application/json",
                payload="{}",
            )
            await add_attribution(
                conn,
                event_slug=slug,
                scrape_record_id=scrape_id,
                source_url=attr.get("source_url"),
                observed_at=attr.get("observed_at"),
                evidence_type=attr.get("evidence_type"),
                source_tier=source_tier,
                confidence_score=attr.get("confidence_score"),
                confidence_rationale=attr.get("confidence_rationale"),
            )


@pytest.mark.asyncio
async def test_evidence_full_chain(client: AsyncClient) -> None:
    """Full chain: launch with 3 attributions returns correct evidence response."""
    slug = "test-rocket-2025-03-15-10-00"
    await _seed_launch_with_attributions(
        slug,
        attributions=[
            {
                "source_name": "SpaceX Official",
                "source_tier": 1,
                "evidence_type": "official_schedule",
                "source_url": "https://spacex.com/launch",
                "observed_at": "2025-03-14T10:00:00+00:00",
                "confidence_score": 90,
                "confidence_rationale": "Tier 1 official schedule",
            },
            {
                "source_name": "FAA NOTAM",
                "source_tier": 2,
                "evidence_type": "notam",
                "source_url": "https://notams.aim.faa.gov/",
                "observed_at": "2025-03-13T08:00:00+00:00",
                "confidence_score": 75,
                "confidence_rationale": "NOTAM issued for launch window",
            },
            {
                "source_name": "SpaceNews",
                "source_tier": 3,
                "evidence_type": "media",
                "source_url": "https://spacenews.com/article",
                "observed_at": "2025-03-12T06:00:00+00:00",
                "confidence_score": 55,
                "confidence_rationale": "Media report corroborating schedule",
            },
        ],
    )

    response = await client.get(f"/v1/launches/{slug}/evidence")
    assert response.status_code == 200
    data = response.json()

    assert data["launch_id"] == slug
    assert data["claim_lifecycle"] == "corroborated"
    assert data["event_kind"] == "observed"
    assert data["evidence_count"] == 3
    assert data["tier_coverage"] == [1, 2, 3]
    assert len(data["attributions"]) == 3

    # Check ordering: observed_at descending
    observed_dates = [a["observed_at"] for a in data["attributions"]]
    assert observed_dates[0] > observed_dates[1] > observed_dates[2]

    # Check first attribution fields
    first = data["attributions"][0]
    assert first["source_name"] == "SpaceX Official"
    assert first["source_tier"] == 1
    assert first["evidence_type"] == "official_schedule"
    assert first["confidence_score"] == 90


@pytest.mark.asyncio
async def test_evidence_empty_attributions(client: AsyncClient) -> None:
    """Launch with no attributions returns empty evidence chain."""
    slug = "empty-launch-2025-03-15"
    async with get_db() as conn:
        await upsert_launch_event(
            conn,
            LaunchEventCreate(
                name="Empty Launch",
                launch_date=datetime(2025, 3, 15, tzinfo=UTC),
                launch_date_precision="day",
                provider="NoProvider",
                launch_type="unknown",
                status="scheduled",
                slug=slug,
                claim_lifecycle="indicated",
                event_kind="inferred",
            ),
        )

    response = await client.get(f"/v1/launches/{slug}/evidence")
    assert response.status_code == 200
    data = response.json()

    assert data["launch_id"] == slug
    assert data["evidence_count"] == 0
    assert data["tier_coverage"] == []
    assert data["attributions"] == []


@pytest.mark.asyncio
async def test_evidence_not_found(client: AsyncClient) -> None:
    """Unknown slug returns 404."""
    response = await client.get("/v1/launches/nonexistent-slug-xyz/evidence")
    assert response.status_code == 404
    assert response.json()["detail"] == "Launch not found"


@pytest.mark.asyncio
async def test_launch_detail_includes_evidence_url(client: AsyncClient) -> None:
    """GET /v1/launches/{slug} response includes evidence_url field."""
    slug = "evidence-url-test-2025-03-15-10-00"
    async with get_db() as conn:
        await upsert_launch_event(
            conn,
            LaunchEventCreate(
                name="Evidence URL Test",
                launch_date=datetime(2025, 3, 15, 10, 0, 0, tzinfo=UTC),
                launch_date_precision="minute",
                provider="TestCo",
                vehicle="TestV",
                launch_type="civilian",
                status="scheduled",
                slug=slug,
            ),
        )

    response = await client.get(f"/v1/launches/{slug}")
    assert response.status_code == 200
    data = response.json()

    assert "evidence_url" in data
    assert data["evidence_url"] == f"/v1/launches/{slug}/evidence"
