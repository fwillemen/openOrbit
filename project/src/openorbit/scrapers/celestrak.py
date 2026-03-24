"""CelesTrak scraper for non-credentialed recent launch data.

Uses the public CelesTrak GP endpoint for objects launched in the last 30 days,
aggregates payload records into launch-level events, and upserts those events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any, ClassVar

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


class CelesTrakScraper(BaseScraper):
    """Scraper for CelesTrak last-30-day launch objects feed."""

    source_name: ClassVar[str] = "celestrak_recent"
    source_url: ClassVar[str] = (
        "https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=json"
    )
    SOURCE_NAME = "CelesTrak Last-30-Day Launches"

    def __init__(self) -> None:
        """Initialize scraper with runtime settings."""
        self.settings = get_settings()
        self.source_id: int | None = None

    async def scrape(self) -> dict[str, int]:
        """Scrape recent launch objects from CelesTrak.

        Returns:
            Summary with total_fetched, new_events, updated_events.
        """
        from openorbit.db import _db_connection

        if _db_connection is None:
            await init_db()

        async with get_db() as conn:
            self.source_id = await self._ensure_source_registered(conn)

            raw_json, http_status = await self._fetch_with_retry(self.source_url)

            scrape_record_id = await log_scrape_run(
                conn,
                source_id=self.source_id,
                url=self.source_url,
                http_status=http_status,
                content_type="application/json" if raw_json else None,
                payload=raw_json,
                error_message=None if raw_json else "Failed to fetch CelesTrak data",
            )

            if not raw_json:
                logger.error("Failed to fetch data from CelesTrak")
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
                "CelesTrak scrape complete: %d total, %d new, %d updated",
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
        """Register source if needed and return source ID."""
        sources = await get_osint_sources(conn, enabled_only=False)
        for source in sources:
            if source.name == self.SOURCE_NAME:
                return source.id

        return await register_osint_source(
            conn,
            name=self.SOURCE_NAME,
            url=self.source_url,
            scraper_class="openorbit.scrapers.celestrak.CelesTrakScraper",
            enabled=True,
        )

    async def _fetch_with_retry(self, url: str) -> tuple[str | None, int | None]:
        """Fetch CelesTrak feed with exponential backoff retries."""
        timeout = httpx.Timeout(self.settings.SCRAPER_TIMEOUT_SECONDS)
        user_agent = "openOrbit/0.1.0 (OSINT aggregator)"

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

                    response = await client.get(url, headers={"User-Agent": user_agent})

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

        logger.error("Failed to fetch CelesTrak feed after retries")
        return None, None

    def parse(self, raw_data: str) -> list[LaunchEventCreate]:  # type: ignore[override]
        """Parse CelesTrak JSON object list into launch-level events.

        Args:
            raw_data: Raw JSON payload from CelesTrak last-30-days endpoint.

        Returns:
            Deduplicated list of launch-level events.

        Raises:
            ValueError: If JSON payload is invalid.
        """
        try:
            objects = json.loads(raw_data)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON from CelesTrak: %s", e)
            raise ValueError(f"Invalid JSON: {e}") from e

        if not isinstance(objects, list):
            logger.warning("Unexpected CelesTrak payload shape: expected list")
            return []

        grouped: dict[str, dict[str, Any]] = {}

        for item in objects:
            if not isinstance(item, dict):
                continue

            launch_date_raw = self._extract_launch_date_string(item)
            if launch_date_raw is None:
                continue

            launch_date = self._parse_launch_date(launch_date_raw)
            if launch_date is None:
                continue

            object_id = item.get("OBJECT_ID")
            object_name = (
                item.get("OBJECT_NAME")
                if isinstance(item.get("OBJECT_NAME"), str)
                else "Unknown payload"
            )
            provider = item.get("OWNER") if isinstance(item.get("OWNER"), str) else "Unknown"
            site = item.get("SITE") if isinstance(item.get("SITE"), str) else None

            launch_key = self._launch_key(object_id, launch_date_raw, site)
            slug = f"celestrak-{self._slugify(launch_key)}"

            if launch_key not in grouped:
                grouped[launch_key] = {
                    "slug": slug,
                    "launch_date": launch_date,
                    "provider": provider,
                    "location": site,
                    "payload_names": [object_name],
                }
            else:
                grouped[launch_key]["payload_names"].append(object_name)

        events: list[LaunchEventCreate] = []
        for launch_key, data in grouped.items():
            payload_count = len(data["payload_names"])
            first_payload = str(data["payload_names"][0])
            name = f"CelesTrak launch {launch_key} ({payload_count} payloads): {first_payload}"

            event = LaunchEventCreate(
                name=name,
                launch_date=data["launch_date"],
                launch_date_precision="day",
                provider=str(data["provider"]),
                vehicle=None,
                location=data["location"],
                pad=None,
                launch_type="unknown",
                status="launched",
                slug=str(data["slug"]),
            )
            events.append(event)

        logger.info(
            "Parsed %d launch events from %d CelesTrak objects",
            len(events),
            len(objects),
        )
        return events

    @staticmethod
    def _parse_launch_date(value: str) -> datetime | None:
        """Parse launch date from either `YYYY-MM-DD` or ISO datetime text."""
        try:
            if "T" in value:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.astimezone(UTC)
            parsed = datetime.strptime(value, "%Y-%m-%d")
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            return None

    @staticmethod
    def _extract_launch_date_string(item: dict[str, Any]) -> str | None:
        """Extract best available launch-date-like value from CelesTrak row."""
        launch_date_raw = item.get("LAUNCH_DATE")
        if isinstance(launch_date_raw, str) and launch_date_raw:
            return launch_date_raw

        # Live GP rows typically include `EPOCH` but not explicit launch date.
        epoch_raw = item.get("EPOCH")
        if isinstance(epoch_raw, str) and epoch_raw:
            # Use epoch date as best-effort proxy for recent-launch feed rows.
            return epoch_raw

        return None

    @staticmethod
    def _launch_key(object_id: Any, launch_date: str, site: str | None) -> str:
        """Build stable launch-level key from OBJECT_ID or fallback fields."""
        if isinstance(object_id, str):
            match = re.match(r"^(\d{4}-\d{3})[A-Z0-9]*$", object_id.strip())
            if match:
                return match.group(1)
        site_part = site or "unknown-site"
        return f"{launch_date}-{site_part}"

    @staticmethod
    def _slugify(value: str) -> str:
        """Convert arbitrary key to URL/slug-safe lowercase token."""
        slug = value.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")


async def main() -> None:
    """CLI entry point for CelesTrak scraper."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        scraper = CelesTrakScraper()
        result = await scraper.scrape()

        print("\n=== CelesTrak Scrape Summary ===")
        print(f"Total events fetched: {result['total_fetched']}")
        print(f"New events created: {result['new_events']}")
        print(f"Existing events updated: {result['updated_events']}")
        print("=" * 33)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
