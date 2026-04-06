"""Bluesky social media scraper for launch-related posts.

Fetches posts from Bluesky's public API by searching launch-related
keywords and fetching feeds from tracked space accounts. Posts are
classified as Tier 3 (Analytical/Speculative) evidence.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
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
    {"launch", "liftoff", "rocket", "satellite", "spacecraft"}
)


def _make_slug(uri: str) -> str:
    digest = hashlib.sha1(f"bluesky|{uri}".encode()).hexdigest()[:12]
    return f"bluesky-{digest}"


class BlueskyScraper(BaseScraper):
    """Scraper for launch-related posts on Bluesky.

    Queries the public Bluesky AT Protocol API for posts matching
    launch-related terms and fetches feeds from tracked space accounts.
    No authentication required.
    """

    source_name: ClassVar[str] = "bluesky"
    source_url: ClassVar[str] = "https://public.api.bsky.app"
    source_tier: ClassVar[int] = 3
    evidence_type: ClassVar[str] = "media"
    refresh_interval_hours: ClassVar[int] = 2

    SEARCH_TERMS: ClassVar[tuple[str, ...]] = (
        "launch",
        "liftoff",
        "rocket",
        "satellite",
        "spacecraft",
    )
    TRACKED_ACCOUNTS: ClassVar[tuple[str, ...]] = (
        "nasa.gov",
        "spacex.com",
        "nasaspaceflight.com",
        "spaceflightnow.com",
        "esa.int",
    )

    SEARCH_URL: ClassVar[str] = (
        "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
    )
    FEED_URL: ClassVar[str] = (
        "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
    )
    RATE_LIMIT_SECONDS: ClassVar[float] = 3.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_launch_relevant(self, text: str) -> bool:
        """Return True if *text* contains at least one launch keyword.

        Args:
            text: Post body text to check.

        Returns:
            True when any keyword from ``_LAUNCH_KEYWORDS`` is found
            (case-insensitive).
        """
        lower = text.lower()
        return any(kw in lower for kw in _LAUNCH_KEYWORDS)

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, str],
    ) -> tuple[str | None, int | None]:
        """GET *url* with *params*, return (raw_text, status_code).

        Args:
            client: Shared httpx async client.
            url: Endpoint URL.
            params: Query parameters.

        Returns:
            Tuple of (response_text, http_status).  Both are ``None`` on
            network failure.
        """
        try:
            response = await client.get(url, params=params)
            return response.text, response.status_code
        except httpx.RequestError as exc:
            logger.warning("Network error fetching %s: %s", url, exc)
            return None, None

    async def _collect_posts(
        self,
        client: httpx.AsyncClient,
    ) -> list[dict[str, Any]]:
        """Collect raw post dicts from search terms and tracked accounts.

        Applies a ``RATE_LIMIT_SECONDS`` sleep between every request.

        Args:
            client: Shared httpx async client.

        Returns:
            List of raw post dicts (may contain duplicates by URI).
        """
        raw_posts: list[dict[str, Any]] = []

        for term in self.SEARCH_TERMS:
            text, status = await self._fetch_json(
                client, self.SEARCH_URL, {"q": term, "limit": "25"}
            )
            if text and status == 200:
                try:
                    data = json.loads(text)
                    raw_posts.extend(data.get("posts", []))
                except json.JSONDecodeError:
                    logger.warning("Non-JSON response for search term '%s'", term)
            await asyncio.sleep(self.RATE_LIMIT_SECONDS)

        for handle in self.TRACKED_ACCOUNTS:
            text, status = await self._fetch_json(
                client, self.FEED_URL, {"actor": handle, "limit": "25"}
            )
            if text and status == 200:
                try:
                    data = json.loads(text)
                    for item in data.get("feed", []):
                        post = item.get("post")
                        if post:
                            raw_posts.append(post)
                except json.JSONDecodeError:
                    logger.warning("Non-JSON response for account '%s'", handle)
            await asyncio.sleep(self.RATE_LIMIT_SECONDS)

        return raw_posts

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> dict[str, int]:
        """Scrape launch posts from Bluesky and upsert into the database.

        Returns:
            Summary dict with keys ``total_fetched``, ``new_events``,
            ``updated_events``.
        """
        if _db_connection is None:
            await init_db()

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
                    url=self.source_url,
                    scraper_class="openorbit.scrapers.bluesky.BlueskyScraper",
                    enabled=True,
                    source_tier=self.source_tier,
                )

            # Fetch posts
            timeout = httpx.Timeout(30.0)
            async with httpx.AsyncClient(
                timeout=timeout,
                headers={"User-Agent": "openOrbit/0.1.0 (OSINT aggregator)"},
            ) as client:
                raw_posts = await self._collect_posts(client)

            # Deduplicate by URI
            seen: dict[str, dict[str, Any]] = {}
            for post in raw_posts:
                uri = post.get("uri", "")
                if uri and uri not in seen:
                    seen[uri] = post

            # Filter to launch-relevant posts
            relevant = [
                p
                for p in seen.values()
                if self._is_launch_relevant(p.get("record", {}).get("text", ""))
            ]

            # Log scrape run
            scrape_record_id = await log_scrape_run(
                conn,
                source_id=source_id,
                url=self.source_url,
                http_status=200,
                content_type="application/json",
                payload=json.dumps(relevant),
                error_message=None,
            )

            # Parse and upsert
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
                "Bluesky: %d total, %d new, %d updated",
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
        """Parse a JSON array of Bluesky post objects into launch events.

        Args:
            raw_data: JSON string — either a plain list of post dicts or
                the ``posts`` wrapper from the search endpoint.

        Returns:
            List of :class:`LaunchEventCreate` models (one per post).

        Raises:
            ValueError: If *raw_data* is not valid JSON.
        """
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

        # Accept both a bare list and the {"posts": [...]} wrapper
        posts = data.get("posts", []) if isinstance(data, dict) else data

        events: list[LaunchEventCreate] = []
        for post in posts:
            uri = post.get("uri", "")
            record = post.get("record", {})
            text = record.get("text", "")
            created_at_raw = record.get("createdAt") or post.get("indexedAt", "")
            author = post.get("author", {})
            handle = author.get("handle", "unknown")

            if not uri or not text:
                continue

            try:
                launch_date = datetime.fromisoformat(
                    created_at_raw.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                launch_date = datetime.now(UTC)

            slug = _make_slug(uri)
            events.append(
                LaunchEventCreate(
                    name=text[:120],
                    launch_date=launch_date,
                    launch_date_precision="day",
                    provider=handle,
                    vehicle=None,
                    location=None,
                    pad=None,
                    launch_type="unknown",
                    status="scheduled",
                    slug=slug,
                    claim_lifecycle="rumor",
                    event_kind="inferred",
                )
            )

        return events
