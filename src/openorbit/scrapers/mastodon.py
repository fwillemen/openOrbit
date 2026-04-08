"""Mastodon social media scraper for launch-related posts.

Fetches posts from Mastodon public hashtag timelines for launch-related
hashtags. Posts are classified as Tier 3 (Analytical/Speculative) evidence.
No authentication required — uses public API endpoints.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from openorbit.db import (
    _db_connection,
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

_LAUNCH_KEYWORDS: frozenset[str] = frozenset(
    {"launch", "liftoff", "rocket", "satellite", "spacecraft", "mission", "orbit"}
)


def _strip_html(content: str) -> str:
    """Remove HTML tags from *content*.

    Args:
        content: HTML string.

    Returns:
        Plain text with all tags removed.
    """
    return re.sub(r"<[^>]+>", "", content)


def _make_slug(url: str) -> str:
    """Generate a deterministic slug from a Mastodon status URL.

    Args:
        url: Mastodon status URL.

    Returns:
        Slug of the form ``mastodon-{12-char sha1}``.
    """
    digest = hashlib.sha1(f"mastodon|{url}".encode()).hexdigest()[:12]
    return f"mastodon-{digest}"


class MastodonScraper(BaseScraper):
    """Scraper for launch-related posts on Mastodon.

    Queries public Mastodon hashtag timeline endpoints for space/launch
    related hashtags.  No authentication required.
    """

    source_name: ClassVar[str] = "mastodon"
    source_url: ClassVar[str] = "https://mastodon.social/api/v1/timelines/tag"
    source_tier: ClassVar[int] = 3
    evidence_type: ClassVar[str] = "media"
    refresh_interval_hours: ClassVar[int] = 2

    HASHTAGS: ClassVar[tuple[str, ...]] = (
        "spacelaunch",
        "spacex",
        "nasa",
        "rocket",
        "satellite",
    )
    LAUNCH_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "launch",
        "liftoff",
        "rocket",
        "satellite",
        "spacecraft",
        "mission",
        "orbit",
    )
    MAX_PAGES_PER_HASHTAG: ClassVar[int] = 2
    PAGE_SIZE: ClassVar[int] = 40

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_link_header(self, link_header: str | None) -> str | None:
        """Extract the ``rel="next"`` URL from a ``Link`` response header.

        Args:
            link_header: Value of the HTTP ``Link`` header, or ``None``.

        Returns:
            The next-page URL string, or ``None`` if not present.
        """
        if not link_header:
            return None
        match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
        return match.group(1) if match else None

    def _is_launch_relevant(self, text: str) -> bool:
        """Return True if *text* contains at least one launch keyword.

        Args:
            text: Plain text content to check.

        Returns:
            True when any keyword from :attr:`LAUNCH_KEYWORDS` is present
            (case-insensitive).
        """
        lower = text.lower()
        return any(kw in lower for kw in self.LAUNCH_KEYWORDS)

    async def _fetch_hashtag_statuses(
        self,
        client: httpx.AsyncClient,
        instance: str,
        hashtag: str,
    ) -> list[dict[str, Any]]:
        """Fetch up to MAX_PAGES_PER_HASHTAG pages for *hashtag*.

        Args:
            client: Shared httpx async client.
            instance: Mastodon instance hostname (e.g. ``mastodon.social``).
            hashtag: Hashtag to fetch (without ``#``).

        Returns:
            List of raw Mastodon status dicts.
        """
        url: str | None = (
            f"https://{instance}/api/v1/timelines/tag/{hashtag}?limit={self.PAGE_SIZE}"
        )
        statuses: list[dict[str, Any]] = []
        pages_fetched = 0

        while url and pages_fetched < self.MAX_PAGES_PER_HASHTAG:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    page_statuses: list[dict[str, Any]] = response.json()
                    statuses.extend(page_statuses)
                    pages_fetched += 1
                    url = self._parse_link_header(response.headers.get("Link"))
                else:
                    logger.warning(
                        "Mastodon: HTTP %s fetching #%s from %s",
                        response.status_code,
                        hashtag,
                        instance,
                    )
                    break
            except httpx.RequestError as exc:
                logger.warning(
                    "Mastodon: network error fetching #%s from %s: %s",
                    hashtag,
                    instance,
                    exc,
                )
                break

        return statuses

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> dict[str, int]:
        """Scrape launch posts from Mastodon hashtag timelines.

        Reads ``MASTODON_INSTANCE`` env var (default: ``mastodon.social``),
        fetches up to :attr:`MAX_PAGES_PER_HASHTAG` pages for each hashtag
        in :attr:`HASHTAGS`, deduplicates by status URL, filters to
        launch-relevant content, then upserts into the database.

        Returns:
            Summary dict with keys ``total_fetched``, ``new_events``,
            ``updated_events``.
        """
        if _db_connection is None:
            await init_db()

        instance = os.environ.get("MASTODON_INSTANCE", "mastodon.social")

        async with get_db() as conn:
            # Ensure source is registered
            sources = await get_osint_sources(conn, enabled_only=False)
            source_id: int | None = None
            for src in sources:
                if src.name == self.source_name:
                    source_id = src.id
                    break

            if source_id is None:
                source_id = await register_osint_source(
                    conn,
                    name=self.source_name,
                    url=f"https://{instance}/api/v1/timelines/tag",
                    scraper_class="openorbit.scrapers.mastodon.MastodonScraper",
                    enabled=True,
                    source_tier=self.source_tier,
                )

            # Fetch statuses for all hashtags
            timeout = httpx.Timeout(30.0)
            all_statuses: list[dict[str, Any]] = []
            async with httpx.AsyncClient(
                timeout=timeout,
                headers={"User-Agent": "openOrbit/0.1.0 (OSINT aggregator)"},
            ) as client:
                for hashtag in self.HASHTAGS:
                    page_statuses = await self._fetch_hashtag_statuses(
                        client, instance, hashtag
                    )
                    all_statuses.extend(page_statuses)

            # Deduplicate by status URL
            seen: dict[str, dict[str, Any]] = {}
            for status in all_statuses:
                status_url = status.get("url", "")
                if status_url and status_url not in seen:
                    seen[status_url] = status

            # Filter to launch-relevant statuses
            relevant = [
                s
                for s in seen.values()
                if self._is_launch_relevant(_strip_html(s.get("content", "")))
            ]

            # Log scrape run
            scrape_record_id = await log_scrape_run(
                conn,
                source_id=source_id,
                url=f"https://{instance}/api/v1/timelines/tag",
                http_status=200,
                content_type="application/json",
                payload=json.dumps(relevant),
                error_message=None,
            )

            # Parse and upsert events
            events = await self.parse(json.dumps(relevant))

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
                    evidence_type=self.evidence_type,
                    source_tier=self.source_tier,
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
                "Mastodon: %d total, %d new, %d updated",
                len(events),
                new_count,
                updated_count,
            )
            return {
                "total_fetched": len(events),
                "new_events": new_count,
                "updated_events": updated_count,
            }

    async def parse(self, raw_data: str) -> list[LaunchEventCreate]:
        """Parse a JSON array of Mastodon status objects into launch events.

        Args:
            raw_data: JSON string — a list of Mastodon status dicts.

        Returns:
            List of :class:`LaunchEventCreate` models (one per status).

        Raises:
            ValueError: If *raw_data* is not valid JSON.
        """
        try:
            statuses: list[dict[str, Any]] = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

        if not isinstance(statuses, list):
            raise ValueError("Expected a JSON array of Mastodon statuses")

        events: list[LaunchEventCreate] = []
        for status in statuses:
            url = status.get("url", "")
            content_html = status.get("content", "")
            created_at_raw = status.get("created_at", "")
            account = status.get("account", {})
            acct = account.get("acct", "unknown")

            if not url or not content_html:
                continue

            stripped_text = _strip_html(content_html).strip()

            try:
                launch_date = datetime.fromisoformat(
                    created_at_raw.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                launch_date = datetime.now(UTC)

            slug = _make_slug(url)
            # Extract image URLs from media attachments
            image_urls: list[str] = []
            for attachment in status.get("media_attachments", []):
                if attachment.get("type") == "image":
                    img_url = attachment.get("url", "")
                    if img_url:
                        image_urls.append(img_url)

            events.append(
                LaunchEventCreate(
                    name=stripped_text[:120],
                    launch_date=launch_date,
                    launch_date_precision="day",
                    provider=acct,
                    vehicle=None,
                    location=None,
                    pad=None,
                    launch_type="civilian",
                    status="scheduled",
                    slug=slug,
                    image_urls=image_urls,
                    claim_lifecycle="rumor",
                    event_kind="inferred",
                )
            )

        return events
