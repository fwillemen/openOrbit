"""Tier 3 News RSS scrapers for SpaceFlightNow and NASASpaceflight.

These scrapers ingest launch-related news articles from RSS feeds and apply
fuzzy entity linking to associate articles with existing launch events or
create new rumor-level events when no match is found.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import aiosqlite

from openorbit.db import (
    add_attribution,
    get_db,
    init_db,
    log_scrape_run,
    register_osint_source,
    update_source_last_scraped,
    upsert_launch_event,
)
from openorbit.models.db import LaunchEventCreate
from openorbit.scrapers.public_feed import PublicFeedScraper

logger = logging.getLogger(__name__)

_FUZZY_WINDOW_DAYS = 1


class NewsRSSScraper(PublicFeedScraper):
    """Abstract base for Tier 3 news RSS scrapers.

    Overrides parse() to stamp claim_lifecycle='rumor' and event_kind='inferred',
    overrides _ensure_source_registered() to pass source_tier=3, and overrides
    scrape() to perform fuzzy entity linking against existing events.
    """

    source_tier: ClassVar[int] = 3
    evidence_type: ClassVar[str] = "media"
    KEYWORDS: ClassVar[tuple[str, ...]] = (
        "launch",
        "liftoff",
        "rocket",
        "satellite",
        "spacecraft",
        "mission",
        "orbit",
        "countdown",
    )

    def parse(self, raw_data: str) -> list[LaunchEventCreate]:  # type: ignore[override]
        """Parse RSS feed and stamp rumor/inferred lifecycle on every event.

        Args:
            raw_data: Raw RSS/Atom XML feed.

        Returns:
            List of LaunchEventCreate with claim_lifecycle='rumor' and
            event_kind='inferred'.
        """
        events = super().parse(raw_data)
        stamped: list[LaunchEventCreate] = []
        for event in events:
            stamped.append(
                event.model_copy(
                    update={"claim_lifecycle": "rumor", "event_kind": "inferred"}
                )
            )
        return stamped

    async def _ensure_source_registered(self, conn: aiosqlite.Connection) -> int:
        """Register source at source_tier=3 if not yet present."""
        from openorbit.db import get_osint_sources

        sources = await get_osint_sources(conn, enabled_only=False)
        for source in sources:
            if source.name == self.SOURCE_NAME:
                return source.id

        return await register_osint_source(
            conn,
            name=self.SOURCE_NAME,
            url=self.source_url,
            scraper_class=f"{self.__class__.__module__}.{self.__class__.__name__}",
            enabled=True,
            source_tier=3,
        )

    async def scrape(self) -> dict[str, int]:
        """Scrape feed with fuzzy entity linking.

        For each parsed event:
        - If provider + date ±1 day matches an existing event → attribution only.
        - Otherwise → upsert new event then add attribution.

        Returns:
            Dict with total_fetched, new_events, updated_events counts.
        """
        from openorbit.db import _db_connection

        if _db_connection is None:
            await init_db()

        async with get_db() as conn:
            self.source_id = await self._ensure_source_registered(conn)

            raw_feed, http_status = await self._fetch_with_retry(self.source_url)

            scrape_record_id = await log_scrape_run(
                conn,
                source_id=self.source_id,
                url=self.source_url,
                http_status=http_status,
                content_type=("application/xml" if raw_feed else None),
                payload=raw_feed,
                error_message=(
                    None if raw_feed else f"Failed to fetch {self.SOURCE_NAME} feed"
                ),
            )

            if not raw_feed:
                logger.error("Failed to fetch data from %s", self.SOURCE_NAME)
                return {"total_fetched": 0, "new_events": 0, "updated_events": 0}

            events = self.parse(raw_feed)
            new_count = 0
            updated_count = 0

            # Load existing events for fuzzy matching
            async with conn.execute(
                "SELECT slug, provider, launch_date FROM launch_events"
            ) as cursor:
                existing_rows = await cursor.fetchall()

            existing_events = [
                {
                    "slug": row["slug"],
                    "provider": row["provider"],
                    "launch_date": row["launch_date"],
                }
                for row in existing_rows
            ]

            for event in events:
                matched_slug = self._fuzzy_match(event, existing_events)

                if matched_slug:
                    # Attribution only — event already tracked
                    await add_attribution(
                        conn,
                        event_slug=matched_slug,
                        scrape_record_id=scrape_record_id,
                        evidence_type=self.evidence_type,
                        source_tier=self.source_tier,
                        confidence_rationale="Fuzzy provider+date match from news RSS",
                    )
                    updated_count += 1
                else:
                    slug = await upsert_launch_event(conn, event)
                    await add_attribution(
                        conn,
                        event_slug=slug,
                        scrape_record_id=scrape_record_id,
                        evidence_type=self.evidence_type,
                        source_tier=self.source_tier,
                        confidence_rationale="News RSS article — unmatched, new rumor event",
                    )
                    existing_events.append(
                        {
                            "slug": slug,
                            "provider": event.provider,
                            "launch_date": event.launch_date.isoformat(),
                        }
                    )
                    new_count += 1

            await update_source_last_scraped(
                conn,
                source_id=self.source_id,
                timestamp=datetime.now(UTC).isoformat(),
            )

            logger.info(
                "%s scrape complete: %d total, %d new, %d linked",
                self.SOURCE_NAME,
                len(events),
                new_count,
                updated_count,
            )

            return {
                "total_fetched": len(events),
                "new_events": new_count,
                "updated_events": updated_count,
            }

    def _fuzzy_match(
        self,
        event: LaunchEventCreate,
        existing: list[dict[str, str]],
    ) -> str | None:
        """Return slug of matching existing event or None.

        Matches on provider equality and launch_date within ±1 day.

        Args:
            event: Candidate event to match.
            existing: List of dicts with 'slug', 'provider', 'launch_date'.

        Returns:
            Matched slug or None.
        """
        window = timedelta(days=_FUZZY_WINDOW_DAYS)
        for row in existing:
            if row["provider"].lower() != event.provider.lower():
                continue
            try:
                existing_dt = datetime.fromisoformat(
                    row["launch_date"].replace("Z", "+00:00")
                )
                if existing_dt.tzinfo is None:
                    existing_dt = existing_dt.replace(tzinfo=UTC)
            except (ValueError, AttributeError):
                continue
            candidate_dt = event.launch_date
            if candidate_dt.tzinfo is None:
                candidate_dt = candidate_dt.replace(tzinfo=UTC)
            if abs(existing_dt - candidate_dt) <= window:
                return row["slug"]
        return None


class SpaceFlightNowScraper(NewsRSSScraper):
    """Scraper for SpaceFlightNow RSS feed (Tier 3 / media)."""

    source_name: ClassVar[str] = "news_spaceflightnow"
    source_url: ClassVar[str] = "https://spaceflightnow.com/feed/"
    SOURCE_NAME: ClassVar[str] = "SpaceFlightNow RSS"
    PROVIDER_NAME: ClassVar[str] = "SpaceFlightNow"

    @classmethod
    def feed_region(cls) -> str:
        """Return global feed region."""
        return "global"


class NASASpaceflightScraper(NewsRSSScraper):
    """Scraper for NASASpaceflight.com RSS feed (Tier 3 / media)."""

    source_name: ClassVar[str] = "news_nasaspaceflight"
    source_url: ClassVar[str] = "https://www.nasaspaceflight.com/feed/"
    SOURCE_NAME: ClassVar[str] = "NASASpaceflight RSS"
    PROVIDER_NAME: ClassVar[str] = "NASASpaceflight"

    @classmethod
    def feed_region(cls) -> str:
        """Return global feed region."""
        return "global"
