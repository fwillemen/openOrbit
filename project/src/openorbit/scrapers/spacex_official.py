"""Official SpaceX launch scraper using SpaceX API v4.

Fetches upcoming launches from SpaceX's public API, stores raw payloads,
parses into LaunchEventCreate models, and upserts into the database.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

import aiosqlite
import httpx

from openorbit.config import get_settings
from openorbit.db import (
    add_attribution,
    close_db,
    get_db,
    get_osint_sources,
    init_db,
    log_scrape_run,
    register_osint_source,
    update_source_last_scraped,
    upsert_launch_event,
)
from openorbit.models.db import LaunchEventCreate
from openorbit.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class SpaceXOfficialScraper(BaseScraper):
    """Scraper for SpaceX public API v4 launch data."""

    source_name: ClassVar[str] = "spacex_official"
    source_url: ClassVar[str] = "https://api.spacexdata.com/v4/launches/query"
    source_tier: ClassVar[int] = 1
    evidence_type: ClassVar[str] = "official_schedule"
    SOURCE_NAME = "SpaceX API v4"
    BASE_URL = "https://api.spacexdata.com/v4/launches/query"

    def __init__(self) -> None:
        """Initialize scraper with runtime settings."""
        self.settings = get_settings()
        self.source_id: int | None = None

    async def scrape(self) -> dict[str, int]:
        """Scrape upcoming launches from the official SpaceX API.

        Returns:
            Summary with total_fetched, new_events, and updated_events.
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
                error_message=None if raw_json else "Failed to fetch SpaceX API data",
            )

            if not raw_json:
                logger.error("Failed to fetch launch data from SpaceX API")
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
                "SpaceX scrape complete: %d total, %d new, %d updated",
                len(events),
                new_count,
                updated_count,
            )

            return {
                "total_fetched": len(events),
                "new_events": new_count,
                "updated_events": updated_count,
            }

    async def _ensure_source_registered(self, conn: aiosqlite.Connection) -> int:
        """Register source if needed and return source id."""
        sources = await get_osint_sources(conn, enabled_only=False)
        for source in sources:
            if source.name == self.SOURCE_NAME:
                return source.id

        return await register_osint_source(
            conn,
            name=self.SOURCE_NAME,
            url=self.BASE_URL,
            scraper_class="openorbit.scrapers.spacex_official.SpaceXOfficialScraper",
            enabled=True,
        )

    async def _fetch_with_retry(self, url: str) -> tuple[str | None, int | None]:
        """Fetch SpaceX launch payload with retry/backoff logic."""
        timeout = httpx.Timeout(self.settings.SCRAPER_TIMEOUT_SECONDS)
        user_agent = "openOrbit/0.1.0 (OSINT aggregator)"
        payload = {
            "query": {"upcoming": True},
            "options": {
                "pagination": False,
                "sort": {"date_utc": "asc"},
                "select": [
                    "id",
                    "name",
                    "date_utc",
                    "upcoming",
                    "success",
                    "launchpad",
                    "rocket",
                    "details",
                ],
            },
        }

        for attempt in range(self.settings.SCRAPER_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    if attempt > 0:
                        backoff_delay = 2**attempt
                        logger.info(
                            "Retry %d/%d: waiting %ds",
                            attempt,
                            self.settings.SCRAPER_MAX_RETRIES,
                            backoff_delay,
                        )
                        await asyncio.sleep(backoff_delay)
                    elif self.source_id is not None:
                        await asyncio.sleep(self.settings.SCRAPER_DELAY_SECONDS)

                    response = await client.post(
                        url,
                        headers={"User-Agent": user_agent},
                        json=payload,
                    )

                    if 400 <= response.status_code < 500:
                        logger.error(
                            "Client error %d: %s",
                            response.status_code,
                            response.text[:200],
                        )
                        return None, response.status_code

                    if response.status_code >= 500:
                        logger.warning("Server error %d, will retry", response.status_code)
                        continue

                    response.raise_for_status()
                    return response.text, response.status_code

            except httpx.TimeoutException:
                logger.warning(
                    "Timeout on attempt %d/%d",
                    attempt + 1,
                    self.settings.SCRAPER_MAX_RETRIES,
                )
                continue
            except httpx.RequestError as e:
                logger.warning("Network error on attempt %d: %s", attempt + 1, e)
                continue

        logger.error("Failed to fetch SpaceX launches after retries")
        return None, None

    def parse(self, raw_data: str) -> list[LaunchEventCreate]:  # type: ignore[override]
        """Parse SpaceX API response into LaunchEventCreate models.

        Args:
            raw_data: Raw JSON body from SpaceX launches query endpoint.

        Returns:
            Parsed launch events.

        Raises:
            ValueError: If JSON cannot be decoded.
        """
        try:
            data: dict[str, Any] = json.loads(raw_data)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON from SpaceX API: %s", e)
            raise ValueError(f"Invalid JSON: {e}") from e

        docs = data.get("docs", [])
        events: list[LaunchEventCreate] = []

        for item in docs:
            try:
                event = self._parse_launch(item)
                events.append(event)
            except (KeyError, TypeError, ValueError) as e:
                launch_name = item.get("name", "unknown")
                logger.warning("Skipping malformed SpaceX launch '%s': %s", launch_name, e)

        logger.info("Parsed %d valid SpaceX launches from %d records", len(events), len(docs))
        return events

    def _parse_launch(self, launch: dict[str, Any]) -> LaunchEventCreate:
        """Parse single SpaceX launch record."""
        launch_id = launch["id"]
        name = launch["name"]
        date_utc = launch["date_utc"]

        launch_date = datetime.fromisoformat(date_utc.replace("Z", "+00:00"))

        status = self._map_status(launch.get("upcoming"), launch.get("success"))

        launchpad = launch.get("launchpad")
        rocket = launch.get("rocket")
        details = launch.get("details")

        location = f"Launchpad {launchpad}" if launchpad else None
        vehicle = str(rocket) if rocket else None
        pad = str(launchpad) if launchpad else None

        # Stable slug based on SpaceX launch id to ensure idempotent upserts.
        slug = f"spx-{launch_id}"

        if details and isinstance(details, str):
            # Keep human context by appending details snippet when present.
            normalized_name = f"{name} | {details[:80]}" if len(details) > 0 else name
        else:
            normalized_name = name

        return LaunchEventCreate(
            name=normalized_name,
            launch_date=launch_date,
            launch_date_precision="second",
            provider="SpaceX",
            vehicle=vehicle,
            location=location,
            pad=pad,
            launch_type="civilian",
            status=status,
            slug=slug,
        )

    @staticmethod
    def _map_status(
        upcoming: bool | None,
        success: bool | None,
    ) -> Literal["scheduled", "delayed", "launched", "failed", "cancelled"]:
        """Map SpaceX status fields into database status enum."""
        if upcoming:
            return "scheduled"
        if success is True:
            return "launched"
        if success is False:
            return "failed"
        return "scheduled"


async def main() -> None:
    """CLI entry point for the SpaceX scraper."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        scraper = SpaceXOfficialScraper()
        result = await scraper.scrape()

        print("\n=== SpaceX Official Scrape Summary ===")
        print(f"Total events fetched: {result['total_fetched']}")
        print(f"New events created: {result['new_events']}")
        print(f"Existing events updated: {result['updated_events']}")
        print("=" * 38)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
