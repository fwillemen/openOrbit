"""Space agency scraper using Launch Library 2 API.

Fetches upcoming launch events from Launch Library 2 (thespacedevs.com),
stores raw JSON, parses into LaunchEventCreate models, and upserts into the database.
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


class SpaceAgencyScraper(BaseScraper):
    """Scraper for Launch Library 2 API (thespacedevs.com).

    Fetches upcoming launch events, stores raw JSON in raw_scrape_records,
    parses into LaunchEventCreate models, and upserts into launch_events table.
    """

    source_name: ClassVar[str] = "space_agency"
    source_url: ClassVar[str] = "https://ll.thespacedevs.com/2.2.0/"
    SOURCE_NAME = "Launch Library 2"
    BASE_URL = "https://ll.thespacedevs.com/2.2.0"
    ENDPOINT = "/launch/upcoming/"

    def __init__(self) -> None:
        """Initialize scraper with settings."""
        self.settings = get_settings()
        self.source_id: int | None = None

    async def scrape(self) -> dict[str, int]:
        """Scrape upcoming launches from Launch Library 2.

        Returns:
            Summary dict with total_fetched, new_events, updated_events counts.

        Raises:
            Exception: If critical failure occurs.
        """
        # Initialize DB if not already done
        from openorbit.db import _db_connection

        if _db_connection is None:
            await init_db()

        # Register or get existing source
        async with get_db() as conn:
            self.source_id = await self._ensure_source_registered(conn)

            # Fetch data with retries
            url = f"{self.BASE_URL}{self.ENDPOINT}?limit=100"
            raw_json, http_status = await self._fetch_with_retry(url)

            # Log raw scrape
            scrape_record_id = await log_scrape_run(
                conn,
                source_id=self.source_id,
                url=url,
                http_status=http_status,
                content_type="application/json" if raw_json else None,
                payload=raw_json,
                error_message=None if raw_json else "Failed to fetch data",
            )

            if not raw_json:
                logger.error("Failed to fetch data from Launch Library 2")
                return {"total_fetched": 0, "new_events": 0, "updated_events": 0}

            # Parse and upsert events
            events = await self.parse(raw_json)
            new_count = 0
            updated_count = 0

            # Get existing event slugs to determine new vs. updated
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
                    existing_slugs.add(slug)  # Add to set for next iteration

            # Update source timestamp
            await update_source_last_scraped(
                conn,
                source_id=self.source_id,
                timestamp=datetime.now(UTC).isoformat(),
            )

            logger.info(
                f"Scrape complete: {len(events)} total, "
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

        # Register new source
        source_id = await register_osint_source(
            conn,
            name=self.SOURCE_NAME,
            url=f"{self.BASE_URL}{self.ENDPOINT}",
            scraper_class="openorbit.scrapers.space_agency.SpaceAgencyScraper",
            enabled=True,
        )
        return source_id

    async def _fetch_with_retry(self, url: str) -> tuple[str | None, int | None]:
        """Fetch URL with exponential backoff retry logic.

        Args:
            url: URL to fetch.

        Returns:
            Tuple of (raw_json_string, http_status_code).
            Returns (None, None) if all retries fail.
        """
        timeout = httpx.Timeout(self.settings.SCRAPER_TIMEOUT_SECONDS)
        user_agent = "openOrbit/0.1.0 (OSINT aggregator)"

        for attempt in range(self.settings.SCRAPER_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    # Apply rate limiting (except first attempt)
                    if attempt > 0:
                        backoff_delay = 2**attempt
                        max_retries = self.settings.SCRAPER_MAX_RETRIES
                        logger.info(
                            f"Retry {attempt}/{max_retries}: waiting {backoff_delay}s"
                        )
                        await asyncio.sleep(backoff_delay)
                    elif self.source_id is not None:
                        # Apply standard delay between requests
                        await asyncio.sleep(self.settings.SCRAPER_DELAY_SECONDS)

                    response = await client.get(
                        url,
                        headers={"User-Agent": user_agent},
                    )

                    # 4xx errors: don't retry (client error)
                    if 400 <= response.status_code < 500:
                        logger.error(
                            f"Client error {response.status_code}: "
                            f"{response.text[:200]}"
                        )
                        return None, response.status_code

                    # 5xx errors: retry
                    if response.status_code >= 500:
                        logger.warning(
                            f"Server error {response.status_code}, will retry"
                        )
                        continue

                    # Success
                    response.raise_for_status()
                    return response.text, response.status_code

            except httpx.TimeoutException:
                max_retries = self.settings.SCRAPER_MAX_RETRIES
                logger.warning(f"Timeout on attempt {attempt + 1}/{max_retries}")
                continue
            except httpx.RequestError as e:
                logger.warning(f"Network error on attempt {attempt + 1}: {e}")
                continue

        # All retries exhausted
        max_retries = self.settings.SCRAPER_MAX_RETRIES
        logger.error(f"Failed to fetch after {max_retries} attempts")
        return None, None

    async def parse(self, raw_data: str) -> list[LaunchEventCreate]:
        """Parse Launch Library 2 JSON response into LaunchEventCreate models.

        Args:
            raw_data: Raw JSON string from LL2 API.

        Returns:
            List of LaunchEventCreate models.

        Raises:
            ValueError: If JSON is invalid or missing required fields.
        """
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            raise ValueError(f"Invalid JSON: {e}") from e

        if "results" not in data:
            logger.warning("No 'results' key in API response")
            return []

        launches = data["results"]
        events: list[LaunchEventCreate] = []

        for launch in launches:
            try:
                event = self._parse_launch(launch)
                events.append(event)
            except (KeyError, ValueError, TypeError) as e:
                launch_name = launch.get("name", "unknown")
                logger.warning(f"Skipping malformed launch: {e} (data: {launch_name})")
                continue

        logger.info(f"Parsed {len(events)} valid events from {len(launches)} launches")
        return events

    def _parse_launch(self, launch: dict[str, Any]) -> LaunchEventCreate:
        """Parse a single launch object into LaunchEventCreate.

        Args:
            launch: Single launch dict from LL2 API.

        Returns:
            LaunchEventCreate model.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If date parsing fails.
        """
        # Required fields
        name = launch["name"]
        net_iso = launch["net"]  # "NET" = "No Earlier Than" timestamp
        net_precision = launch.get("net_precision", {}).get("id", 3)  # Default to "day"
        ll2_id = launch.get("id", "")  # LL2 unique identifier

        # Parse launch date (always UTC)
        launch_date = datetime.fromisoformat(net_iso.replace("Z", "+00:00"))

        # Map LL2 precision (0-7) to our enum
        precision_map: dict[
            int, Literal["second", "minute", "hour", "day", "month", "year"]
        ] = {
            0: "year",
            1: "month",
            2: "day",
            3: "day",
            4: "hour",
            5: "hour",
            6: "minute",
            7: "second",
        }
        launch_date_precision = precision_map.get(net_precision, "day")

        # Provider
        provider = launch.get("launch_service_provider", {}).get("name", "Unknown")

        # Vehicle
        vehicle = launch.get("rocket", {}).get("configuration", {}).get("name")

        # Location and pad
        location = launch.get("pad", {}).get("location", {}).get("name")
        pad = launch.get("pad", {}).get("name")

        # Status mapping
        status_name = launch.get("status", {}).get("name", "TBD")
        status_map: dict[
            str, Literal["scheduled", "delayed", "launched", "failed", "cancelled"]
        ] = {
            "Go for Launch": "scheduled",
            "Go": "scheduled",
            "TBD": "scheduled",
            "TBC": "scheduled",
            "Success": "launched",
            "Failure": "failed",
            "Partial Failure": "failed",
            "In Flight": "launched",
            "Hold": "delayed",
        }
        status = status_map.get(status_name, "scheduled")

        # Generate slug with LL2 ID to ensure idempotency
        # Format: ll2-{uuid} (e.g., ll2-abc-123-def)
        slug = f"ll2-{ll2_id}" if ll2_id else None

        return LaunchEventCreate(
            name=name,
            launch_date=launch_date,
            launch_date_precision=launch_date_precision,
            provider=provider,
            vehicle=vehicle,
            location=location,
            pad=pad,
            launch_type="civilian",  # LL2 doesn't distinguish military launches
            status=status,
            slug=slug,
        )


async def main() -> None:
    """CLI entry point for space agency scraper."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    scraper = SpaceAgencyScraper()
    result = await scraper.scrape()

    print("\n=== Launch Library 2 Scrape Summary ===")
    print(f"Total events fetched: {result['total_fetched']}")
    print(f"New events created: {result['new_events']}")
    print(f"Existing events updated: {result['updated_events']}")
    print("=" * 40)


if __name__ == "__main__":
    asyncio.run(main())
