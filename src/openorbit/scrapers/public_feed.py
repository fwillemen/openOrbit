"""Reusable non-credentialed RSS/Atom launch feed scraper primitives."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import xml.etree.ElementTree as ET
from abc import abstractmethod
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import ClassVar

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


class PublicFeedScraper(BaseScraper):
    """Base scraper for non-credentialed official RSS/Atom feeds."""

    source_name: ClassVar[str] = "public_feed_base"
    source_url: ClassVar[str] = "https://example.invalid/rss"
    source_tier: ClassVar[int] = 1
    evidence_type: ClassVar[str] = "official_schedule"
    SOURCE_NAME: ClassVar[str]
    PROVIDER_NAME: ClassVar[str]
    KEYWORDS: ClassVar[tuple[str, ...]] = (
        "launch",
        "liftoff",
        "rocket",
        "satellite",
        "spacecraft",
        "vehicle",
    )
    EXCLUDE_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "internship",
        "conference",
        "workshop",
        "education",
        "training",
        "outreach",
        "vacancy",
        "award",
        "procurement",
        "tender",
    )
    LOCATION_HINTS: ClassVar[tuple[tuple[str, str], ...]] = ()
    VEHICLE_HINTS: ClassVar[tuple[tuple[str, str], ...]] = ()

    @classmethod
    @abstractmethod
    def feed_region(cls) -> str:
        """Return adapter region label (used to keep this base class abstract)."""

    def __init__(self) -> None:
        """Initialize scraper with runtime settings."""
        self.settings = get_settings()
        self.source_id: int | None = None

    async def scrape(self) -> dict[str, int]:
        """Scrape feed items and upsert launch-like events."""
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
                error_message=(None if raw_feed else f"Failed to fetch {self.SOURCE_NAME} feed"),
            )

            if not raw_feed:
                logger.error("Failed to fetch data from %s", self.SOURCE_NAME)
                return {"total_fetched": 0, "new_events": 0, "updated_events": 0}

            events = self.parse(raw_feed)
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
                "%s scrape complete: %d total, %d new, %d updated",
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

    async def _ensure_source_registered(self, conn: aiosqlite.Connection) -> int:
        """Register source row if needed and return source id."""
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
        )

    async def _fetch_with_retry(self, url: str) -> tuple[str | None, int | None]:
        """Fetch feed with standard retry/backoff behavior."""
        timeout = httpx.Timeout(self.settings.SCRAPER_TIMEOUT_SECONDS)
        user_agent = "openOrbit/0.1.0 (OSINT aggregator)"

        for attempt in range(self.settings.SCRAPER_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout, verify=self.settings.SCRAPER_SSL_VERIFY) as client:
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

        logger.error("Failed to fetch feed after retries: %s", url)
        return None, None

    def parse(self, raw_data: str) -> list[LaunchEventCreate]:  # type: ignore[override]
        """Parse RSS/Atom feed into launch-like events.

        Args:
            raw_data: Raw RSS/Atom XML feed.

        Returns:
            List of launch-like events filtered by keywords.

        Raises:
            ValueError: If XML cannot be parsed.
        """
        entries = self._parse_feed_entries(raw_data)

        events: list[LaunchEventCreate] = []
        seen_slugs: set[str] = set()
        now = datetime.now(UTC)

        for entry in entries:
            title = entry.get("title") or "Untitled mission update"
            summary = entry.get("summary") or ""
            text = f"{title} {summary}".lower()

            if not self._is_launch_relevant(text):
                continue

            published = self._parse_datetime(entry.get("published")) or now
            status = self._infer_status(text, published, now)
            link = entry.get("link") or self.source_url
            location = self._infer_location(text)
            vehicle = self._infer_vehicle(text)

            slug = self._build_slug(link=link, title=title)
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            events.append(
                LaunchEventCreate(
                    name=title,
                    launch_date=published,
                    launch_date_precision="day",
                    provider=self.PROVIDER_NAME,
                    vehicle=vehicle,
                    location=location,
                    pad=None,
                    launch_type="civilian",
                    status=status,
                    slug=slug,
                )
            )

        logger.info(
            "Parsed %d launch-like events from %d feed entries for %s",
            len(events),
            len(entries),
            self.SOURCE_NAME,
        )
        return events

    def _is_launch_relevant(self, text: str) -> bool:
        """Return True when the feed item text matches launch keywords."""
        has_launch_signal = any(keyword in text for keyword in self.KEYWORDS)
        has_exclusion_signal = any(keyword in text for keyword in self.EXCLUDE_KEYWORDS)
        return has_launch_signal and not has_exclusion_signal

    @staticmethod
    def _infer_status(
        text: str,
        published: datetime,
        now: datetime,
    ) -> str:
        """Infer coarse launch status from text and publish date."""
        if "cancel" in text:
            return "cancelled"
        if "delay" in text or "postpon" in text:
            return "delayed"
        if "scheduled" in text or "upcoming" in text or "will launch" in text:
            return "scheduled"
        if "launch successful" in text or "launched" in text or "liftoff" in text:
            return "launched"
        if published < now:
            return "launched"
        return "scheduled"

    def _infer_location(self, text: str) -> str | None:
        """Infer launch location from source-specific keyword hints."""
        for key, location in self.LOCATION_HINTS:
            if key in text:
                return location
        return None

    def _infer_vehicle(self, text: str) -> str | None:
        """Infer launch vehicle from source-specific keyword hints."""
        for key, vehicle in self.VEHICLE_HINTS:
            if key in text:
                return vehicle
        return None

    def _build_slug(self, link: str, title: str) -> str:
        """Build stable deterministic slug from source + link + title."""
        digest = hashlib.sha1(f"{self.source_name}|{link}|{title}".encode()).hexdigest()[:12]
        return f"{self.source_name}-{digest}"

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        """Parse RFC822/ISO datetime text as timezone-aware UTC."""
        if not value:
            return None

        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except (TypeError, ValueError):
            pass

        try:
            parsed_iso = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed_iso.tzinfo is None:
                parsed_iso = parsed_iso.replace(tzinfo=UTC)
            return parsed_iso.astimezone(UTC)
        except ValueError:
            return None

    @staticmethod
    def _text_or_none(element: ET.Element | None) -> str | None:
        """Return stripped text from an XML element when present."""
        if element is None or element.text is None:
            return None
        text = element.text.strip()
        return text or None

    def _parse_feed_entries(self, raw_data: str) -> list[dict[str, str | None]]:
        """Parse RSS or Atom XML into normalized feed entry dictionaries."""
        try:
            root = ET.fromstring(raw_data)
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML feed: {e}") from e

        entries: list[dict[str, str | None]] = []

        # RSS: channel/item
        for item in root.findall(".//item"):
            entries.append(
                {
                    "title": self._text_or_none(item.find("title")),
                    "link": self._text_or_none(item.find("link")),
                    "published": self._text_or_none(item.find("pubDate")),
                    "summary": self._text_or_none(item.find("description")),
                }
            )

        # Atom: feed/entry
        for entry in root.findall(".//{*}entry"):
            link_node = entry.find("{*}link")
            link = link_node.attrib.get("href") if link_node is not None else None
            entries.append(
                {
                    "title": self._text_or_none(entry.find("{*}title")),
                    "link": link,
                    "published": self._text_or_none(entry.find("{*}published"))
                    or self._text_or_none(entry.find("{*}updated")),
                    "summary": self._text_or_none(entry.find("{*}summary"))
                    or self._text_or_none(entry.find("{*}content")),
                }
            )

        return entries


async def run_public_feed_scraper_cli(scraper: PublicFeedScraper, title: str) -> None:
    """Run a public feed scraper with standard CLI formatting and cleanup."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        result = await scraper.scrape()
        print(f"\n=== {title} Scrape Summary ===")
        print(f"Total events fetched: {result['total_fetched']}")
        print(f"New events created: {result['new_events']}")
        print(f"Existing events updated: {result['updated_events']}")
        print("=" * 40)
    finally:
        await close_db()
