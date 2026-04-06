"""Admin endpoints for source monitoring and health stats.

All endpoints require X-API-Key authentication (admin key).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from openorbit.auth import require_admin
from openorbit.db import get_db
from openorbit.models.api import (
    AdminRefreshResponse,
    AdminStatsResponse,
    SourceHealthResponse,
)

router = APIRouter(
    prefix="/admin",
    tags=["Admin — key required"],
    dependencies=[Depends(require_admin)],
)


@router.get("/sources", response_model=list[SourceHealthResponse])
async def list_sources_health() -> list[SourceHealthResponse]:
    """List all OSINT sources with health and run statistics."""
    async with get_db() as conn:
        async with conn.execute(
            "SELECT id, name, url, scraper_class, enabled, source_tier, last_scraped_at "
            "FROM osint_sources ORDER BY name"
        ) as cursor:
            sources = await cursor.fetchall()

        results = []
        for src in sources:
            source_id = src["id"]

            # Event count via attributions joined to scrape records
            async with conn.execute(
                """SELECT COUNT(DISTINCT ea.event_slug) as cnt
                   FROM event_attributions ea
                   JOIN raw_scrape_records rsr ON ea.scrape_record_id = rsr.id
                   WHERE rsr.source_id = ?""",
                (source_id,),
            ) as cur:
                row = await cur.fetchone()
                event_count = row["cnt"] if row else 0

            # Last run info
            async with conn.execute(
                """SELECT scraped_at, error_message
                   FROM raw_scrape_records
                   WHERE source_id = ?
                   ORDER BY scraped_at DESC LIMIT 1""",
                (source_id,),
            ) as cur:
                last_run = await cur.fetchone()

            last_run_status = None
            last_run_at = None
            if last_run:
                last_run_at = datetime.fromisoformat(last_run["scraped_at"])
                last_run_status = "error" if last_run["error_message"] else "success"

            # Error rate
            async with conn.execute(
                "SELECT COUNT(*) as total FROM raw_scrape_records WHERE source_id = ?",
                (source_id,),
            ) as cur:
                total_row = await cur.fetchone()
                total_runs = total_row["total"] if total_row else 0

            async with conn.execute(
                "SELECT COUNT(*) as errors FROM raw_scrape_records "
                "WHERE source_id = ? AND error_message IS NOT NULL",
                (source_id,),
            ) as cur:
                err_row = await cur.fetchone()
                error_runs = err_row["errors"] if err_row else 0

            error_rate = error_runs / total_runs if total_runs > 0 else 0.0

            results.append(
                SourceHealthResponse(
                    id=src["id"],
                    name=src["name"],
                    url=src["url"],
                    scraper_class=src["scraper_class"],
                    enabled=bool(src["enabled"]),
                    source_tier=src["source_tier"] if src["source_tier"] is not None else 1,
                    last_scraped_at=(
                        datetime.fromisoformat(src["last_scraped_at"])
                        if src["last_scraped_at"]
                        else None
                    ),
                    event_count=event_count,
                    last_run_status=last_run_status,
                    last_run_at=last_run_at,
                    error_rate=error_rate,
                )
            )

    return results


@router.post("/sources/{source_id}/refresh", response_model=AdminRefreshResponse, status_code=202)
async def refresh_source(source_id: int) -> AdminRefreshResponse:
    """Trigger manual refresh for a source."""
    async with get_db() as conn, conn.execute(
        "SELECT id FROM osint_sources WHERE id = ?", (source_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Source not found")

    return AdminRefreshResponse(status="triggered", source_id=str(source_id))


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_stats() -> AdminStatsResponse:
    """Get aggregated statistics for admin dashboard."""
    async with get_db() as conn:
        async with conn.execute("SELECT COUNT(*) as cnt FROM launch_events") as cur:
            row = await cur.fetchone()
            total_events = row["cnt"] if row else 0

        # Events by source (via attributions)
        async with conn.execute(
            """SELECT s.name, COUNT(DISTINCT ea.event_slug) as cnt
               FROM event_attributions ea
               JOIN raw_scrape_records rsr ON ea.scrape_record_id = rsr.id
               JOIN osint_sources s ON rsr.source_id = s.id
               GROUP BY s.name"""
        ) as cur:
            rows = await cur.fetchall()
            events_by_source = {row["name"]: row["cnt"] for row in rows}

        # Events by launch_type
        async with conn.execute(
            "SELECT launch_type, COUNT(*) as cnt FROM launch_events GROUP BY launch_type"
        ) as cur:
            rows = await cur.fetchall()
            events_by_type = {row["launch_type"]: row["cnt"] for row in rows}

        # Events by claim_lifecycle
        async with conn.execute(
            "SELECT claim_lifecycle, COUNT(*) as cnt FROM launch_events GROUP BY claim_lifecycle"
        ) as cur:
            rows = await cur.fetchall()
            events_by_lifecycle = {(row["claim_lifecycle"] or "indicated"): row["cnt"] for row in rows}

        # Average confidence
        async with conn.execute(
            "SELECT AVG(confidence_score) as avg_conf FROM launch_events"
        ) as cur:
            row = await cur.fetchone()
            avg_confidence = float(row["avg_conf"]) if row and row["avg_conf"] is not None else 0.0

        # Last refresh
        async with conn.execute(
            "SELECT MAX(scraped_at) as last_run FROM raw_scrape_records"
        ) as cur:
            row = await cur.fetchone()
            last_refresh_at = (
                datetime.fromisoformat(row["last_run"]) if row and row["last_run"] else None
            )

    return AdminStatsResponse(
        total_events=total_events,
        events_by_source=events_by_source,
        events_by_type=events_by_type,
        events_by_lifecycle=events_by_lifecycle,
        avg_confidence=avg_confidence,
        last_refresh_at=last_refresh_at,
    )
