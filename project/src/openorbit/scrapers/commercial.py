"""Commercial launch provider scraper using Launch Library 2 API.

Fetches upcoming launch events for SpaceX and Rocket Lab from the
Launch Library 2 public API, normalises via the pipeline, and upserts
into the database.  Each provider is registered as a distinct OSINT source.
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
from openorbit.pipeline import NormalizationError, normalize
from openorbit.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Provider definitions: display name and LL2 lsp__name filter value
_PROVIDERS: list[dict[str, str]] = [
    {"name": "SpaceX", "ll2_filter": "SpaceX"},
    {"name": "Rocket Lab", "ll2_filter": "Rocket Lab USA"},
]

_STATUS_MAP: dict[str, Literal["scheduled", "success", "failure", "unknown"]] = {
    "Go for Launch": "scheduled",
    "Go": "scheduled",
    "TBD": "scheduled",
    "TBC": "scheduled",
    "Success": "success",
    "Failure": "failure",
    "Partial Failure": "failure",
    "In Flight": "scheduled",
    "Hold": "scheduled",
}

# Maps LL2 net_precision name → pipeline LaunchEvent precision literals
_PRECISION_MAP: dict[str, Literal["exact", "day", "week", "month"]] = {
    "Second": "exact",
    "Minute": "exact",
    "Hour": "day",
    "Day": "day",
    "Week": "week",
    "Month": "month",
    "Year": "month",
}

# Maps pipeline LaunchEvent status → DB LaunchEventCreate status
_PIPELINE_STATUS_TO_DB: dict[
    str, Literal["scheduled", "delayed", "launched", "failed", "cancelled"]
] = {
    "scheduled": "scheduled",
    "success": "launched",
    "failure": "failed",
    "unknown": "scheduled",
}

# Maps pipeline LaunchEvent precision → DB LaunchEventCreate precision
_PIPELINE_PRECISION_TO_DB: dict[
    str,
    Literal["second", "minute", "hour", "day", "month", "year", "quarter"],
] = {
    "exact": "second",
    "day": "day",
    "week": "day",
    "month": "month",
}


class CommercialLaunchScraper(BaseScraper):
    """Scraper for commercial launch providers via Launch Library 2 API.

    Fetches upcoming launches for SpaceX and Rocket Lab, normalises each
    event through the pipeline, and upserts into the launch_events table.
    Each provider is tracked as a separate OSINT source.
    """

    source_name: ClassVar[str] = "commercial"
    source_url: ClassVar[str] = "https://ll.thespacedevs.com/2.2.0/"
    SOURCE_PREFIX = "LL2 Commercial"
    BASE_URL = "https://ll.thespacedevs.com/2.2.0"
    ENDPOINT = "/launch/upcoming/"
    PROVIDERS: list[dict[str, str]] = _PROVIDERS

    def __init__(self) -> None:
        """Initialize scraper with settings."""
        self.settings = get_settings()

    async def scrape(self) -> list[dict[str, Any]]:
        """Scrape upcoming launches for all commercial providers.

        Returns:
            List of per-provider summary dicts with keys:
            ``provider``, ``total_fetched``, ``new_events``, ``updated_events``.
        """
        from openorbit.db import _db_connection

        if _db_connection is None:
            await init_db()

        summaries: list[dict[str, Any]] = []
        async with get_db() as conn:
            for i, provider in enumerate(self.PROVIDERS):
                summary = await self._scrape_provider(
                    conn, provider["name"], provider["ll2_filter"]
                )
                summaries.append(summary)

                # Delay between providers (not after last one)
                if i < len(self.PROVIDERS) - 1:
                    await asyncio.sleep(self.settings.SCRAPER_DELAY_SECONDS)

        return summaries

    async def _scrape_provider(
        self,
        conn: aiosqlite.Connection,
        provider_name: str,
        ll2_filter: str,
    ) -> dict[str, Any]:
        """Scrape a single provider and upsert results.

        Args:
            conn: Database connection.
            provider_name: Human-readable provider name (e.g. 'SpaceX').
            ll2_filter: lsp__name query value for LL2 (e.g. 'Rocket Lab USA').

        Returns:
            Summary dict with provider, total_fetched, new_events, updated_events.
        """
        source_name = f"{self.SOURCE_PREFIX} – {provider_name}"
        url = (
            f"{self.BASE_URL}{self.ENDPOINT}"
            f"?format=json&limit=100&lsp__name={ll2_filter.replace(' ', '+')}"
        )

        source_id = await self._ensure_source_registered(conn, source_name, url)

        raw_json, http_status = await self._fetch_with_retry(url)

        scrape_record_id = await log_scrape_run(
            conn,
            source_id=source_id,
            url=url,
            http_status=http_status,
            content_type="application/json" if raw_json else None,
            payload=raw_json,
            error_message=None if raw_json else "Failed to fetch data",
        )

        if not raw_json:
            logger.error("Failed to fetch data for provider '%s'", provider_name)
            return {
                "provider": provider_name,
                "total_fetched": 0,
                "new_events": 0,
                "updated_events": 0,
            }

        events = self.parse(raw_json, source_name)

        async with conn.execute("SELECT slug FROM launch_events") as cursor:
            existing_slugs = {row["slug"] for row in await cursor.fetchall()}

        new_count = 0
        updated_count = 0
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
            source_id=source_id,
            timestamp=datetime.now(UTC).isoformat(),
        )

        logger.info(
            "Provider '%s': %d total, %d new, %d updated",
            provider_name,
            len(events),
            new_count,
            updated_count,
        )
        return {
            "provider": provider_name,
            "total_fetched": len(events),
            "new_events": new_count,
            "updated_events": updated_count,
        }

    async def _ensure_source_registered(
        self,
        conn: aiosqlite.Connection,
        source_name: str,
        url: str,
    ) -> int:
        """Return existing source ID or register a new source.

        Args:
            conn: Database connection.
            source_name: Unique source display name.
            url: Canonical fetch URL for this source.

        Returns:
            Source ID.
        """
        sources = await get_osint_sources(conn, enabled_only=False)
        for source in sources:
            if source.name == source_name:
                return source.id

        return await register_osint_source(
            conn,
            name=source_name,
            url=url,
            scraper_class="openorbit.scrapers.commercial.CommercialLaunchScraper",
            enabled=True,
        )

    async def _fetch_with_retry(self, url: str) -> tuple[str | None, int | None]:
        """Fetch URL with exponential backoff retries.

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
                    if attempt > 0:
                        backoff_delay = 2**attempt
                        logger.info(
                            "Retry %d/%d: waiting %ds",
                            attempt,
                            self.settings.SCRAPER_MAX_RETRIES,
                            backoff_delay,
                        )
                        await asyncio.sleep(backoff_delay)

                    response = await client.get(url, headers={"User-Agent": user_agent})

                    if 400 <= response.status_code < 500:
                        logger.error(
                            "Client error %d fetching %s: %s",
                            response.status_code,
                            url,
                            response.text[:200],
                        )
                        return None, response.status_code

                    if response.status_code >= 500:
                        logger.warning(
                            "Server error %d, will retry", response.status_code
                        )
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
            except httpx.RequestError as exc:
                logger.warning("Network error on attempt %d: %s", attempt + 1, exc)
                continue

        logger.error(
            "Failed to fetch %s after %d attempts",
            url,
            self.settings.SCRAPER_MAX_RETRIES,
        )
        return None, None

    def parse(self, raw_data: str, source_name: str = "") -> list[LaunchEventCreate]:
        """Parse LL2 JSON response into LaunchEventCreate models.

        Calls normalize() on each raw launch dict; malformed events are
        logged and skipped rather than aborting the whole batch.

        Args:
            raw_data: Raw JSON string from LL2 API.
            source_name: OSINT source name used in normalize() and error logs.

        Returns:
            List of valid LaunchEventCreate models.

        Raises:
            ValueError: If raw_data is not valid JSON.
        """
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON from '%s': %s", source_name, exc)
            raise ValueError(f"Invalid JSON: {exc}") from exc

        results = data.get("results", [])
        events: list[LaunchEventCreate] = []

        for launch in results:
            try:
                raw_dict = self._map_ll2_to_raw(launch)
                pipeline_event = normalize(raw_dict, source_name)
                db_event = self._pipeline_event_to_db(
                    pipeline_event,
                    slug=f"ll2-{launch.get('id', '')}",
                )
                events.append(db_event)
            except NormalizationError as exc:
                logger.warning(
                    "Skipping malformed launch '%s' from '%s': %s",
                    launch.get("name", "unknown"),
                    source_name,
                    exc,
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "Skipping launch '%s' due to parse error: %s",
                    launch.get("name", "unknown"),
                    exc,
                )

        logger.info(
            "Parsed %d valid events from %d launches for '%s'",
            len(events),
            len(results),
            source_name,
        )
        return events

    def _map_ll2_to_raw(self, ll2_data: dict[str, Any]) -> dict[str, Any]:
        """Map LL2 API response fields to the pipeline raw dict format.

        Args:
            ll2_data: Single launch object from LL2 API ``results`` list.

        Returns:
            Raw dict suitable for passing to :func:`normalize`.
        """
        status_name = ll2_data.get("status", {}).get("name", "TBD")
        precision_name = ll2_data.get("net_precision", {}).get("name", "Day")

        return {
            "name": ll2_data.get("name", ""),
            "launch_date": ll2_data.get("net", ""),
            "launch_date_precision": _PRECISION_MAP.get(precision_name, "day"),
            "provider": ll2_data.get("launch_service_provider", {}).get("name", ""),
            "vehicle": ll2_data.get("rocket", {}).get("configuration", {}).get("name"),
            "location": ll2_data.get("pad", {}).get("location", {}).get("name"),
            "pad": ll2_data.get("pad", {}).get("name"),
            "launch_type": "civilian",
            "status": _STATUS_MAP.get(status_name, "unknown"),
            "confidence_score": 0.7,
        }

    def _pipeline_event_to_db(
        self,
        event: Any,
        slug: str | None = None,
    ) -> LaunchEventCreate:
        """Convert a pipeline LaunchEvent to a DB LaunchEventCreate.

        Args:
            event: Canonical LaunchEvent returned by normalize().
            slug: Optional slug override (e.g., ``ll2-<uuid>``).

        Returns:
            LaunchEventCreate suitable for upsert_launch_event().
        """
        raw_launch_type = event.launch_type
        db_launch_type: Literal["civilian", "military", "unknown"] = (
            "civilian" if raw_launch_type == "public_report" else raw_launch_type
        )
        db_status = _PIPELINE_STATUS_TO_DB.get(event.status, "scheduled")
        db_precision = _PIPELINE_PRECISION_TO_DB.get(event.launch_date_precision, "day")

        return LaunchEventCreate(
            name=event.name,
            launch_date=event.launch_date,
            launch_date_precision=db_precision,
            provider=event.provider,
            vehicle=event.vehicle,
            location=event.location,
            pad=event.pad,
            launch_type=db_launch_type,
            status=db_status,
            slug=slug or None,
        )


async def main() -> None:
    """CLI entry point for the commercial launch scraper."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    scraper = CommercialLaunchScraper()
    summaries = await scraper.scrape()

    print("\n=== Commercial Launch Providers Scrape Summary ===")
    for summary in summaries:
        print(
            f"  {summary['provider']}: "
            f"{summary['total_fetched']} fetched, "
            f"{summary['new_events']} new, "
            f"{summary['updated_events']} updated"
        )
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
