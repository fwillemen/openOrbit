"""Tests for the multi-source deduplication and merging pipeline."""

from __future__ import annotations

import time

import aiosqlite
import pytest

from openorbit.db import init_db_schema
from openorbit.pipeline.deduplicator import (
    _calculate_confidence,
    _events_are_duplicates,
    _normalize_location,
    _normalize_provider,
    deduplicate_and_merge,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_db() -> aiosqlite.Connection:
    """Return a fresh in-memory aiosqlite connection with the full schema."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db_schema(conn)
    return conn


async def _insert_source(conn: aiosqlite.Connection, name: str = "test-src") -> int:
    """Insert a minimal osint_sources row and return its id."""
    async with conn.execute(
        "INSERT INTO osint_sources (name, url, scraper_class) VALUES (?, ?, ?)",
        (name, "https://example.com", "FakeScraper"),
    ) as cur:
        assert cur.lastrowid is not None
        return cur.lastrowid


async def _insert_scrape_record(conn: aiosqlite.Connection, source_id: int) -> int:
    """Insert a minimal raw_scrape_records row and return its id."""
    async with conn.execute(
        "INSERT INTO raw_scrape_records (source_id, scraped_at, url, http_status) "
        "VALUES (?, ?, ?, ?)",
        (source_id, "2025-01-01T00:00:00", "https://example.com", 200),
    ) as cur:
        assert cur.lastrowid is not None
        return cur.lastrowid


async def _insert_event(
    conn: aiosqlite.Connection,
    slug: str,
    provider: str,
    launch_date: str,
    location: str | None = "Cape Canaveral",
    created_at: str = "2025-01-01T00:00:00",
    confidence_score: int = 50,
) -> None:
    """Insert a launch_events row."""
    now = "2025-01-01T00:00:00"
    await conn.execute(
        "INSERT INTO launch_events "
        "(slug, name, launch_date, launch_date_precision, provider, "
        " location, launch_type, status, confidence_score, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            slug,
            f"Mission {slug}",
            launch_date,
            "day",
            provider,
            location,
            "civilian",
            "scheduled",
            confidence_score,
            created_at,
            now,
        ),
    )


async def _insert_attribution(
    conn: aiosqlite.Connection, event_slug: str, scrape_record_id: int
) -> None:
    """Insert an event_attributions row."""
    await conn.execute(
        "INSERT INTO event_attributions (event_slug, scrape_record_id, attributed_at) "
        "VALUES (?, ?, ?)",
        (event_slug, scrape_record_id, "2025-01-01T00:00:00"),
    )


async def _count_events(conn: aiosqlite.Connection) -> int:
    async with conn.execute("SELECT COUNT(*) FROM launch_events") as cur:
        row = await cur.fetchone()
        return row[0] if row else 0


async def _count_attributions(conn: aiosqlite.Connection, slug: str) -> int:
    async with conn.execute(
        "SELECT COUNT(*) FROM event_attributions WHERE event_slug = ?", (slug,)
    ) as cur:
        row = await cur.fetchone()
        return row[0] if row else 0


# ---------------------------------------------------------------------------
# Unit tests — pure helper functions
# ---------------------------------------------------------------------------


def test_normalize_provider_alias() -> None:
    """Known alias resolves to canonical name."""
    assert _normalize_provider("space exploration technologies") == "SpaceX"


def test_normalize_provider_unknown() -> None:
    """Unknown provider returns stripped original."""
    assert _normalize_provider("  Acme Rockets  ") == "Acme Rockets"


def test_normalize_location_none() -> None:
    assert _normalize_location(None) == ""


def test_normalize_location_whitespace() -> None:
    assert _normalize_location("  Cape Canaveral  ") == "cape canaveral"


def test_calculate_confidence_single_source() -> None:
    """Single source → 0.3*1 + 0.4 = 0.7 → 70."""
    assert _calculate_confidence(1) == 70


def test_calculate_confidence_two_sources() -> None:
    """Two sources → 0.3*2 + 0.4 = 1.0 → 100."""
    assert _calculate_confidence(2) == 100


def test_calculate_confidence_capped_at_100() -> None:
    """Score is capped at 100 regardless of source count."""
    assert _calculate_confidence(100) == 100


def test_calculate_confidence_zero_sources() -> None:
    """Zero sources uses base_score only → 0.3*0 + 0.4 = 0.4 → 40."""
    assert _calculate_confidence(0) == 40


def test_events_are_duplicates_exact() -> None:
    e1 = {
        "provider": "SpaceX",
        "launch_date": "2025-06-01T00:00:00",
        "location": "Cape Canaveral",
    }
    e2 = {
        "provider": "SpaceX",
        "launch_date": "2025-06-01T00:00:00",
        "location": "Cape Canaveral",
    }
    assert _events_are_duplicates(e1, e2) is True


def test_events_are_duplicates_near_date() -> None:
    """±2 days within window → duplicate."""
    e1 = {
        "provider": "SpaceX",
        "launch_date": "2025-06-01T00:00:00",
        "location": "Cape Canaveral",
    }
    e2 = {
        "provider": "SpaceX",
        "launch_date": "2025-06-03T00:00:00",
        "location": "Cape Canaveral",
    }
    assert _events_are_duplicates(e1, e2) is True


def test_events_not_duplicates_date_boundary() -> None:
    """4 days apart → not a duplicate."""
    e1 = {
        "provider": "SpaceX",
        "launch_date": "2025-06-01T00:00:00",
        "location": "Cape Canaveral",
    }
    e2 = {
        "provider": "SpaceX",
        "launch_date": "2025-06-05T00:00:00",
        "location": "Cape Canaveral",
    }
    assert _events_are_duplicates(e1, e2) is False


def test_events_not_duplicates_different_provider() -> None:
    """Different providers → not a duplicate."""
    e1 = {
        "provider": "SpaceX",
        "launch_date": "2025-06-01T00:00:00",
        "location": "Cape Canaveral",
    }
    e2 = {
        "provider": "NASA",
        "launch_date": "2025-06-01T00:00:00",
        "location": "Cape Canaveral",
    }
    assert _events_are_duplicates(e1, e2) is False


def test_events_not_duplicates_different_location() -> None:
    """Different non-empty locations → not a duplicate."""
    e1 = {
        "provider": "SpaceX",
        "launch_date": "2025-06-01T00:00:00",
        "location": "Cape Canaveral",
    }
    e2 = {
        "provider": "SpaceX",
        "launch_date": "2025-06-01T00:00:00",
        "location": "Vandenberg SFB",
    }
    assert _events_are_duplicates(e1, e2) is False


def test_events_duplicates_alias_resolution() -> None:
    """Alias provider matches canonical → duplicate."""
    e1 = {
        "provider": "space exploration technologies",
        "launch_date": "2025-06-01T00:00:00",
        "location": "Starbase",
    }
    e2 = {
        "provider": "SpaceX",
        "launch_date": "2025-06-01T00:00:00",
        "location": "Starbase",
    }
    assert _events_are_duplicates(e1, e2) is True


def test_events_duplicates_both_location_empty() -> None:
    """Both locations None/empty → location check passes → duplicate."""
    e1 = {"provider": "SpaceX", "launch_date": "2025-06-01T00:00:00", "location": None}
    e2 = {"provider": "SpaceX", "launch_date": "2025-06-01T00:00:00", "location": None}
    assert _events_are_duplicates(e1, e2) is True


def test_events_not_duplicates_bad_date() -> None:
    """Malformed date → not a duplicate (safe fallback)."""
    e1 = {
        "provider": "SpaceX",
        "launch_date": "not-a-date",
        "location": "Cape Canaveral",
    }
    e2 = {
        "provider": "SpaceX",
        "launch_date": "2025-06-01T00:00:00",
        "location": "Cape Canaveral",
    }
    assert _events_are_duplicates(e1, e2) is False


# ---------------------------------------------------------------------------
# Integration tests — deduplicate_and_merge()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_duplicate_merged() -> None:
    """Exact duplicates → 1 event remains, merged_count=1."""
    conn = await _make_db()
    try:
        src = await _insert_source(conn)
        rec = await _insert_scrape_record(conn, src)
        await _insert_event(
            conn,
            "ev-a",
            "SpaceX",
            "2025-06-01T00:00:00",
            created_at="2025-01-01T00:00:00",
        )
        await _insert_event(
            conn,
            "ev-b",
            "SpaceX",
            "2025-06-01T00:00:00",
            created_at="2025-01-02T00:00:00",
        )
        await _insert_attribution(conn, "ev-b", rec)
        await conn.commit()

        result = await deduplicate_and_merge(conn)

        assert result["merged_count"] == 1
        assert await _count_events(conn) == 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_near_duplicate_merged() -> None:
    """Events 2 days apart with same provider/location → merged."""
    conn = await _make_db()
    try:
        src = await _insert_source(conn)
        rec = await _insert_scrape_record(conn, src)
        await _insert_event(
            conn,
            "ev-a",
            "SpaceX",
            "2025-06-01T00:00:00",
            created_at="2025-01-01T00:00:00",
        )
        await _insert_event(
            conn,
            "ev-b",
            "SpaceX",
            "2025-06-03T00:00:00",
            created_at="2025-01-02T00:00:00",
        )
        await _insert_attribution(conn, "ev-b", rec)
        await conn.commit()

        result = await deduplicate_and_merge(conn)

        assert result["merged_count"] == 1
        assert await _count_events(conn) == 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_date_boundary_not_merged() -> None:
    """Events 4 days apart → not merged."""
    conn = await _make_db()
    try:
        src = await _insert_source(conn)
        rec = await _insert_scrape_record(conn, src)
        await _insert_event(conn, "ev-a", "SpaceX", "2025-06-01T00:00:00")
        await _insert_event(conn, "ev-b", "SpaceX", "2025-06-05T00:00:00")
        await _insert_attribution(conn, "ev-b", rec)
        await conn.commit()

        result = await deduplicate_and_merge(conn)

        assert result["merged_count"] == 0
        assert await _count_events(conn) == 2
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_different_provider_not_merged() -> None:
    """Different providers on same date → not merged."""
    conn = await _make_db()
    try:
        src = await _insert_source(conn)
        rec = await _insert_scrape_record(conn, src)
        await _insert_event(conn, "ev-a", "SpaceX", "2025-06-01T00:00:00")
        await _insert_event(conn, "ev-b", "NASA", "2025-06-01T00:00:00")
        await _insert_attribution(conn, "ev-b", rec)
        await conn.commit()

        result = await deduplicate_and_merge(conn)

        assert result["merged_count"] == 0
        assert await _count_events(conn) == 2
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_different_location_not_merged() -> None:
    """Different locations → not merged."""
    conn = await _make_db()
    try:
        src = await _insert_source(conn)
        rec = await _insert_scrape_record(conn, src)
        await _insert_event(
            conn, "ev-a", "SpaceX", "2025-06-01T00:00:00", location="Cape Canaveral"
        )
        await _insert_event(
            conn, "ev-b", "SpaceX", "2025-06-01T00:00:00", location="Vandenberg SFB"
        )
        await _insert_attribution(conn, "ev-b", rec)
        await conn.commit()

        result = await deduplicate_and_merge(conn)

        assert result["merged_count"] == 0
        assert await _count_events(conn) == 2
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_alias_resolution_merged() -> None:
    """'space exploration technologies' and 'SpaceX' are the same → merged."""
    conn = await _make_db()
    try:
        src = await _insert_source(conn)
        rec = await _insert_scrape_record(conn, src)
        await _insert_event(
            conn,
            "ev-a",
            "space exploration technologies",
            "2025-06-01T00:00:00",
            created_at="2025-01-01T00:00:00",
        )
        await _insert_event(
            conn,
            "ev-b",
            "SpaceX",
            "2025-06-01T00:00:00",
            created_at="2025-01-02T00:00:00",
        )
        await _insert_attribution(conn, "ev-b", rec)
        await conn.commit()

        result = await deduplicate_and_merge(conn)

        assert result["merged_count"] == 1
        assert await _count_events(conn) == 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_idempotency() -> None:
    """Running deduplicate_and_merge twice gives the same final state."""
    conn = await _make_db()
    try:
        src = await _insert_source(conn)
        rec = await _insert_scrape_record(conn, src)
        await _insert_event(
            conn,
            "ev-a",
            "SpaceX",
            "2025-06-01T00:00:00",
            created_at="2025-01-01T00:00:00",
        )
        await _insert_event(
            conn,
            "ev-b",
            "SpaceX",
            "2025-06-01T00:00:00",
            created_at="2025-01-02T00:00:00",
        )
        await _insert_attribution(conn, "ev-b", rec)
        await conn.commit()

        result1 = await deduplicate_and_merge(conn)
        count_after_first = await _count_events(conn)

        result2 = await deduplicate_and_merge(conn)
        count_after_second = await _count_events(conn)

        assert result1["merged_count"] == 1
        assert result2["merged_count"] == 0
        assert count_after_first == count_after_second == 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_confidence_recalculation_two_sources() -> None:
    """After merging a 2-source event the confidence should be 100 (capped)."""
    conn = await _make_db()
    try:
        src1 = await _insert_source(conn, "src-1")
        src2 = await _insert_source(conn, "src-2")
        rec1 = await _insert_scrape_record(conn, src1)
        rec2 = await _insert_scrape_record(conn, src2)

        await _insert_event(
            conn,
            "ev-a",
            "SpaceX",
            "2025-06-01T00:00:00",
            created_at="2025-01-01T00:00:00",
        )
        await _insert_event(
            conn,
            "ev-b",
            "SpaceX",
            "2025-06-01T00:00:00",
            created_at="2025-01-02T00:00:00",
        )
        await _insert_attribution(conn, "ev-a", rec1)
        await _insert_attribution(conn, "ev-b", rec2)
        await conn.commit()

        await deduplicate_and_merge(conn)

        async with conn.execute(
            "SELECT confidence_score FROM launch_events WHERE slug = 'ev-a'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        # 0.3 * 2 + 0.4 = 1.0 → scaled to 100
        assert row[0] == 100
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_attribution_transfer() -> None:
    """After merge, duplicate's attributions belong to the canonical event."""
    conn = await _make_db()
    try:
        src = await _insert_source(conn)
        rec1 = await _insert_scrape_record(conn, src)
        rec2 = await _insert_scrape_record(conn, src)

        await _insert_event(
            conn,
            "ev-a",
            "SpaceX",
            "2025-06-01T00:00:00",
            created_at="2025-01-01T00:00:00",
        )
        await _insert_event(
            conn,
            "ev-b",
            "SpaceX",
            "2025-06-01T00:00:00",
            created_at="2025-01-02T00:00:00",
        )
        await _insert_attribution(conn, "ev-a", rec1)
        await _insert_attribution(conn, "ev-b", rec2)
        await conn.commit()

        await deduplicate_and_merge(conn)

        assert await _count_attributions(conn, "ev-a") == 2
        assert await _count_attributions(conn, "ev-b") == 0
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_performance_100_events() -> None:
    """100 non-duplicate events processed in < 500 ms."""
    conn = await _make_db()
    try:
        for i in range(100):
            # Distinct providers — no merging, pure throughput test.
            await _insert_event(
                conn,
                f"ev-{i:03d}",
                f"Provider-{i}",
                f"2025-{(i % 12) + 1:02d}-01T00:00:00",
                location=f"Site-{i}",
                created_at=f"2025-01-{(i % 28) + 1:02d}T00:00:00",
            )
        await conn.commit()

        start = time.monotonic()
        result = await deduplicate_and_merge(conn)
        elapsed = (time.monotonic() - start) * 1000

        assert elapsed < 500, f"Deduplication took {elapsed:.0f} ms (limit: 500 ms)"
        assert result["merged_count"] == 0
        assert await _count_events(conn) == 100
    finally:
        await conn.close()
