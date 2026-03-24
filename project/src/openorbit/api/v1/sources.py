"""GET /v1/sources — list OSINT sources with metadata."""

from __future__ import annotations

import logging

import openorbit.scrapers  # noqa: F401 — triggers scraper registration
from fastapi import APIRouter

from openorbit.db import get_db, get_osint_sources
from openorbit.scrapers.registry import registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sources"])


@router.get(
    "/sources",
    tags=["sources"],
    summary="List OSINT sources",
    description=(
        "Return the full registry of OSINT data sources tracked by openOrbit, "
        "including enabled/disabled status, refresh schedule, last scrape timestamp, "
        "and the number of launch events attributed to each source."
    ),
    response_description="Object with `data` array of source records.",
)
async def list_sources() -> dict[str, list[dict[str, object]]]:
    """Return all OSINT sources with event counts.

    Merges the scraper registry with DB rows so that registered scrapers
    that have never been run still appear in the response.

    Returns:
        JSON object with a ``data`` list of source records.
    """
    async with get_db() as conn:
        sources = await get_osint_sources(conn, enabled_only=False)

        result: list[dict[str, object]] = []
        seen_names: set[str] = set()

        for source in sources:
            seen_names.add(source.name)
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

    # Add registry-only scrapers (registered but not yet in DB)
    for scraper_cls in registry.get_all():
        if scraper_cls.source_name not in seen_names:
            result.append(
                {
                    "id": None,
                    "name": scraper_cls.source_name,
                    "url": scraper_cls.source_url,
                    "enabled": True,
                    "refresh_interval_hours": 6,
                    "last_scraped_at": None,
                    "event_count": 0,
                    "last_error": None,
                }
            )

    return {"data": result}
