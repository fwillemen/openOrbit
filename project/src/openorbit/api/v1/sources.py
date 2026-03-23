"""GET /v1/sources — list OSINT sources with metadata."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from openorbit.db import get_db, get_osint_sources

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sources"])


@router.get("/sources")
async def list_sources() -> dict[str, list[dict[str, object]]]:
    """Return all OSINT sources with event counts.

    Returns:
        JSON object with a ``data`` list of source records.
    """
    async with get_db() as conn:
        sources = await get_osint_sources(conn, enabled_only=False)

        result: list[dict[str, object]] = []
        for source in sources:
            async with conn.execute(
                """
                SELECT COUNT(DISTINCT ea.event_slug)
                FROM event_attributions ea
                JOIN raw_scrape_records rsr ON ea.scrape_record_id = rsr.id
                WHERE rsr.source_id = ?
                """,
                (source.id,),
            ) as cur:
                row = await cur.fetchone()
            event_count: int = int(row[0]) if row and row[0] is not None else 0

            result.append(
                {
                    "id": source.id,
                    "name": source.name,
                    "url": source.url,
                    "enabled": source.enabled,
                    "refresh_interval_hours": source.refresh_interval_hours,
                    "last_scraped_at": source.last_scraped_at.isoformat()
                    if source.last_scraped_at
                    else None,
                    "event_count": event_count,
                    "last_error": None,
                }
            )

    return {"data": result}
