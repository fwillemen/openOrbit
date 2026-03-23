"""Tests for the InferenceEngine pipeline module."""

from __future__ import annotations

import json

import aiosqlite
import pytest

from openorbit.db import init_db_schema
from openorbit.pipeline.inference import InferenceEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_db() -> aiosqlite.Connection:
    """Create an in-memory SQLite DB with schema and return connection."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db_schema(conn)
    return conn


async def _insert_source(conn: aiosqlite.Connection, name: str) -> int:
    """Insert an OSINT source and return its ID."""
    cur = await conn.execute(
        "INSERT INTO osint_sources (name, url, scraper_class, enabled) VALUES (?, ?, ?, 1)",
        (name, f"http://example.com/{name}", "openorbit.scrapers.Dummy"),
    )
    await conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


async def _insert_event(
    conn: aiosqlite.Connection,
    slug: str,
    pad: str | None = None,
    launch_date: str = "2024-06-01T12:00:00",
    confidence: float = 40.0,
) -> None:
    """Insert a minimal launch event."""
    await conn.execute(
        """INSERT INTO launch_events
           (slug, name, launch_date, launch_date_precision, provider, launch_type, status,
            confidence_score, created_at, updated_at)
           VALUES (?, ?, ?, 'day', 'TestCo', 'civilian', 'scheduled', ?,
                   '2024-01-01T00:00:00', '2024-01-01T00:00:00')""",
        (slug, slug.replace("-", " ").title(), launch_date, confidence),
    )
    if pad:
        await conn.execute("UPDATE launch_events SET pad = ? WHERE slug = ?", (pad, slug))
    await conn.commit()


async def _insert_scrape_record(
    conn: aiosqlite.Connection, source_id: int, slug: str
) -> int:
    """Insert a raw_scrape_records row and attribute it to slug."""
    cur = await conn.execute(
        """INSERT INTO raw_scrape_records (source_id, url, scraped_at)
           VALUES (?, 'http://x', '2024-01-01T00:00:00')""",
        (source_id,),
    )
    await conn.commit()
    record_id: int = cur.lastrowid  # type: ignore[assignment]

    await conn.execute(
        """INSERT INTO event_attributions (event_slug, scrape_record_id, attributed_at)
           VALUES (?, ?, '2024-01-01T00:00:00')""",
        (slug, record_id),
    )
    await conn.commit()
    return record_id


# ---------------------------------------------------------------------------
# Rule 1 — multi_source_corroboration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_source_corroboration_positive() -> None:
    """Event with ≥2 distinct sources gets the flag and +0.2 confidence."""
    conn = await _make_db()
    try:
        src_a = await _insert_source(conn, "NASA")
        src_b = await _insert_source(conn, "SpaceTrack")
        await _insert_event(conn, "event-multi", confidence=40.0)
        await _insert_scrape_record(conn, src_a, "event-multi")
        await _insert_scrape_record(conn, src_b, "event-multi")

        engine = InferenceEngine()
        result = await engine.run(conn)

        assert result["rules_applied"] >= 1
        async with conn.execute(
            "SELECT inference_flags, confidence_score FROM launch_events WHERE slug = 'event-multi'"
        ) as cur:
            row = await cur.fetchone()
        flags = json.loads(row["inference_flags"] or "[]")
        assert "multi_source_corroboration" in flags
        assert float(row["confidence_score"]) == pytest.approx(60.0, abs=0.01)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_multi_source_corroboration_negative() -> None:
    """Event with only 1 source does NOT get the multi_source_corroboration flag."""
    conn = await _make_db()
    try:
        src_a = await _insert_source(conn, "NASA-only")
        await _insert_event(conn, "event-single", confidence=40.0)
        await _insert_scrape_record(conn, src_a, "event-single")

        engine = InferenceEngine()
        await engine.run(conn)

        async with conn.execute(
            "SELECT inference_flags FROM launch_events WHERE slug = 'event-single'"
        ) as cur:
            row = await cur.fetchone()
        flags = json.loads(row["inference_flags"] or "[]")
        assert "multi_source_corroboration" not in flags
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Rule 2 — pad_reuse_pattern
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pad_reuse_pattern_positive() -> None:
    """Event from same pad within 30 days gets pad_reuse_pattern flag."""
    conn = await _make_db()
    try:
        await _insert_event(conn, "event-new", pad="LC-39A", launch_date="2024-06-15T12:00:00")
        # Previous event on same pad, 14 days earlier — within 30-day window.
        await _insert_event(conn, "event-prev", pad="LC-39A", launch_date="2024-06-01T12:00:00")

        engine = InferenceEngine()
        await engine.run(conn)

        async with conn.execute(
            "SELECT inference_flags FROM launch_events WHERE slug = 'event-new'"
        ) as cur:
            row = await cur.fetchone()
        flags = json.loads(row["inference_flags"] or "[]")
        assert "pad_reuse_pattern" in flags
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_pad_reuse_pattern_negative() -> None:
    """Event from same pad 60+ days ago does NOT get pad_reuse_pattern flag."""
    conn = await _make_db()
    try:
        await _insert_event(conn, "event-new2", pad="LC-39B", launch_date="2024-06-15T12:00:00")
        # Previous event on same pad, 60 days earlier — outside 30-day window.
        await _insert_event(conn, "event-old", pad="LC-39B", launch_date="2024-04-15T12:00:00")

        engine = InferenceEngine()
        await engine.run(conn)

        async with conn.execute(
            "SELECT inference_flags FROM launch_events WHERE slug = 'event-new2'"
        ) as cur:
            row = await cur.fetchone()
        flags = json.loads(row["inference_flags"] or "[]")
        assert "pad_reuse_pattern" not in flags
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Rule 3 — notam_cluster
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notam_cluster_positive() -> None:
    """Event with ≥2 NOTAM-sourced events in same week gets notam_cluster flag."""
    conn = await _make_db()
    try:
        notam_src = await _insert_source(conn, "FAA NOTAM Feed")
        await _insert_event(conn, "target-event", launch_date="2024-06-05T12:00:00")
        await _insert_event(conn, "notam-ev-1", launch_date="2024-06-04T12:00:00")
        await _insert_event(conn, "notam-ev-2", launch_date="2024-06-06T12:00:00")
        await _insert_scrape_record(conn, notam_src, "notam-ev-1")
        await _insert_scrape_record(conn, notam_src, "notam-ev-2")

        engine = InferenceEngine()
        await engine.run(conn)

        async with conn.execute(
            "SELECT inference_flags FROM launch_events WHERE slug = 'target-event'"
        ) as cur:
            row = await cur.fetchone()
        flags = json.loads(row["inference_flags"] or "[]")
        assert "notam_cluster" in flags
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_notam_cluster_negative() -> None:
    """Event with only 1 nearby NOTAM-sourced event does NOT get notam_cluster flag."""
    conn = await _make_db()
    try:
        notam_src = await _insert_source(conn, "FAA NOTAM Feed Single")
        await _insert_event(conn, "target-event-no-cluster", launch_date="2024-07-05T12:00:00")
        await _insert_event(conn, "lone-notam", launch_date="2024-07-04T12:00:00")
        await _insert_scrape_record(conn, notam_src, "lone-notam")

        engine = InferenceEngine()
        await engine.run(conn)

        async with conn.execute(
            "SELECT inference_flags FROM launch_events WHERE slug = 'target-event-no-cluster'"
        ) as cur:
            row = await cur.fetchone()
        flags = json.loads(row["inference_flags"] or "[]")
        assert "notam_cluster" not in flags
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inference_engine_idempotent() -> None:
    """Running the engine twice does not duplicate flags or alter confidence."""
    conn = await _make_db()
    try:
        src_a = await _insert_source(conn, "NASA-idem")
        src_b = await _insert_source(conn, "ESA-idem")
        await _insert_event(conn, "idem-event", confidence=40.0)
        await _insert_scrape_record(conn, src_a, "idem-event")
        await _insert_scrape_record(conn, src_b, "idem-event")

        engine = InferenceEngine()
        await engine.run(conn)
        await engine.run(conn)  # Second run — must be idempotent.

        async with conn.execute(
            "SELECT inference_flags, confidence_score FROM launch_events WHERE slug = 'idem-event'"
        ) as cur:
            row = await cur.fetchone()
        flags = json.loads(row["inference_flags"] or "[]")
        # Flag should appear exactly once.
        assert flags.count("multi_source_corroboration") == 1
        # Confidence should not exceed 60 (40 + 20 from one application only).
        assert float(row["confidence_score"]) == pytest.approx(60.0, abs=0.01)
    finally:
        await conn.close()
