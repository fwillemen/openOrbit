"""FAA NOTAM scraper for launch-related airspace notices.

Fetches NOTAMs from the FAA public API, filters for launch-related content
using notam_parser, and upserts matched events into the database.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import aiosqlite
import httpx

from openorbit.config import get_settings
from openorbit.db import (
    add_attribution,
    get_db,
    get_osint_sources,
    init_db,
    log_scrape_run,
    register_osint_source,
    update_source_last_scraped,
    upsert_launch_event,
)
from openorbit.models.db import LaunchEventCreate
from openorbit.pipeline.notam_parser import extract_launch_candidates

logger = logging.getLogger(__name__)

FAA_NOTAM_URL = "https://external-api.faa.gov/notamapi/v1/notams"

# TODO: cycle through multiple ARTCC regions for broader coverage
# (e.g., KZMA, KZJX, KZAB, KZLA, KZOA, KZSE, KZDV, KZAU, KZID, etc.)
_DEFAULT_PARAMS: dict[str, str | int] = {
    "domesticLocation": "KZJX",
    "pageSize": 100,
    "pageNum": 1,
}


class NotamScraper:
    """Scraper for FAA NOTAM Database (launch-related airspace notices).

    Fetches NOTAMs from the FAA public API, filters for launch keywords,
    parses into LaunchEventCreate models, and upserts into the database.
    """

    SOURCE_NAME = "FAA NOTAM Database"
    BASE_URL = FAA_NOTAM_URL

    def __init__(self) -> None:
        """Initialize scraper with settings."""
        self.settings = get_settings()
        self.source_id: int | None = None

    async def scrape(self) -> dict[str, int]:
        """Scrape launch-related NOTAMs from FAA API.

        Returns:
            Summary dict with total_fetched, new_events, updated_events counts.
        """
        from openorbit.db import _db_connection

        if _db_connection is None:
            await init_db()

        async with get_db() as conn:
            self.source_id = await self._ensure_source_registered(conn)

            raw_json, http_status = await self._fetch_with_retry(self.BASE_URL)

            scrape_record_id = await log_scrape_run(
                conn,
                source_id=self.source_id,
                url=self.BASE_URL,
                http_status=http_status,
                content_type="application/json" if raw_json else None,
                payload=raw_json,
                error_message=None if raw_json else "Failed to fetch FAA NOTAM data",
            )

            if not raw_json:
                logger.error("Failed to fetch data from FAA NOTAM API")
                return {"total_fetched": 0, "new_events": 0, "updated_events": 0}

            events = self.parse(raw_json)
            new_count = 0
            updated_count = 0

            async with conn.execute("SELECT slug FROM launch_events") as cursor:
                existing_slugs = {row["slug"] for row in await cursor.fetchall()}

            for event in events:
                slug = await upsert_launch_event(conn, event)
                await add_attribution(
                    conn,
                    event_slug=slug,
                    scrape_record_id=scrape_record_id,
                )
                if slug in existing_slugs:
                    updated_count += 1
                else:
                    new_count += 1
                    existing_slugs.add(slug)

            await update_source_last_scraped(
                conn,
                source_id=self.source_id,
                timestamp=datetime.now(UTC).isoformat(),
            )

            logger.info(
                f"NOTAM scrape complete: {len(events)} matched, "
                f"{new_count} new, {updated_count} updated"
            )

            return {
                "total_fetched": len(events),
                "new_events": new_count,
                "updated_events": updated_count,
            }

    async def _ensure_source_registered(self, conn: aiosqlite.Connection) -> int:
        """Register source if not exists, return source ID.

        Args:
            conn: Database connection.

        Returns:
            Source ID.
        """
        sources = await get_osint_sources(conn, enabled_only=False)
        for source in sources:
            if source.name == self.SOURCE_NAME:
                return source.id

        source_id = await register_osint_source(
            conn,
            name=self.SOURCE_NAME,
            url=self.BASE_URL,
            scraper_class="openorbit.scrapers.notams.NotamScraper",
            enabled=True,
        )
        return source_id

    async def _fetch_with_retry(self, url: str) -> tuple[str | None, int | None]:
        """Fetch FAA NOTAM API with exponential backoff retry.

        Returns immediately on 401/403 (credentials required) without retrying.

        Args:
            url: URL to fetch.

        Returns:
            Tuple of (raw_json_string, http_status_code), or (None, None) on failure.
        """
        timeout = httpx.Timeout(self.settings.SCRAPER_TIMEOUT_SECONDS)
        user_agent = "openOrbit/0.1.0 (OSINT aggregator)"

        for attempt in range(self.settings.SCRAPER_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    if attempt > 0:
                        backoff_delay = 2**attempt
                        logger.info(
                            f"Retry {attempt}/{self.settings.SCRAPER_MAX_RETRIES}: "
                            f"waiting {backoff_delay}s"
                        )
                        await asyncio.sleep(backoff_delay)
                    elif self.source_id is not None:
                        await asyncio.sleep(self.settings.SCRAPER_DELAY_SECONDS)

                    response = await client.get(
                        url,
                        headers={"User-Agent": user_agent},
                        params=_DEFAULT_PARAMS,
                    )

                    if response.status_code in (401, 403):
                        logger.warning(
                            "FAA NOTAM API requires credentials — configure "
                            "FAA_API_KEY env var"
                        )
                        return None, response.status_code

                    if 400 <= response.status_code < 500:
                        logger.error(
                            f"Client error {response.status_code}: "
                            f"{response.text[:200]}"
                        )
                        return None, response.status_code

                    if response.status_code >= 500:
                        logger.warning(
                            f"Server error {response.status_code}, will retry"
                        )
                        continue

                    response.raise_for_status()
                    return response.text, response.status_code

            except httpx.TimeoutException:
                logger.warning(
                    f"Timeout on attempt {attempt + 1}/{self.settings.SCRAPER_MAX_RETRIES}"
                )
                continue
            except httpx.RequestError as e:
                logger.warning(f"Network error on attempt {attempt + 1}: {e}")
                continue

        logger.error(
            f"Failed to fetch FAA NOTAMs after {self.settings.SCRAPER_MAX_RETRIES} attempts"
        )
        return None, None

    def parse(self, raw_data: str) -> list[LaunchEventCreate]:
        """Parse FAA NOTAM JSON response into LaunchEventCreate models.

        Args:
            raw_data: Raw JSON string from FAA NOTAM API.

        Returns:
            List of LaunchEventCreate models for launch-related NOTAMs.

        Raises:
            ValueError: If JSON is invalid.
        """
        try:
            data: dict[str, Any] = json.loads(raw_data)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from FAA NOTAM API: {e}")
            raise ValueError(f"Invalid JSON: {e}") from e

        items: list[dict[str, Any]] = data.get("items", [])
        events = extract_launch_candidates(items)
        logger.info(f"Parsed {len(events)} launch-related NOTAMs from {len(items)} total")
        return events


async def main() -> None:
    """CLI entry point for NOTAM scraper."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    scraper = NotamScraper()
    result = await scraper.scrape()

    print("\n=== FAA NOTAM Scrape Summary ===")
    print(f"Total launch events found: {result['total_fetched']}")
    print(f"New events created: {result['new_events']}")
    print(f"Existing events updated: {result['updated_events']}")
    print("=" * 35)


if __name__ == "__main__":
    asyncio.run(main())
