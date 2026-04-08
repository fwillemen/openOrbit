"""Twitter/X social media scraper for launch-related tweets.

Fetches tweets from the Twitter/X API v2 ``/tweets/search/recent`` endpoint
by searching launch-related keywords and tracking curated space accounts.
Tweets are classified as Tier 3 (Analytical/Social) evidence.

Rate limiting
-------------
The free tier of the Twitter API v2 allows **180 requests per 15 minutes**
on the recent-search endpoint.  In production (``TWITTER_BEARER_TOKEN``
set) the scraper honours this limit by sleeping between requests.  When no
bearer token is configured the scraper is effectively disabled and returns
an empty result set — callers see ``total_fetched: 0``.

Environment variables
---------------------
``TWITTER_BEARER_TOKEN``
    OAuth 2.0 Bearer token for the Twitter/X API v2.  **Required** for
    production use.  Omit to disable the scraper gracefully.
"""

from __future__ import annotations

import asyncio
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
    {
        "launch",
        "liftoff",
        "rocket",
        "satellite",
        "spacecraft",
        "mission",
        "orbit",
    }
)


def _strip_urls(text: str) -> str:
    """Remove ``https://t.co/…`` short-links from tweet text.

    Args:
        text: Raw tweet text.

    Returns:
        Text with ``https://t.co/…`` URLs removed.
    """
    return re.sub(r"https?://t\.co/\S+", "", text).strip()


def _make_slug(tweet_id: str) -> str:
    """Generate a deterministic slug from a tweet ID.

    Args:
        tweet_id: Twitter tweet ID string.

    Returns:
        Slug of the form ``twitter-{12-char sha1}``.
    """
    digest = hashlib.sha1(f"twitter|{tweet_id}".encode()).hexdigest()[:12]
    return f"twitter-{digest}"


class TwitterScraper(BaseScraper):
    """Scraper for launch-related tweets on Twitter/X.

    Queries the Twitter API v2 ``/tweets/search/recent`` endpoint for
    tweets matching launch-related terms.  Requires a bearer token set
    via the ``TWITTER_BEARER_TOKEN`` environment variable.

    Free-tier rate limits (180 requests / 15 min) are respected by
    sleeping :attr:`RATE_LIMIT_SECONDS` between every API call.
    """

    source_name: ClassVar[str] = "twitter"
    source_url: ClassVar[str] = "https://api.twitter.com/2"
    source_tier: ClassVar[int] = 3
    evidence_type: ClassVar[str] = "media"
    refresh_interval_hours: ClassVar[int] = 2

    SEARCH_TERMS: ClassVar[tuple[str, ...]] = (
        "rocket launch",
        "satellite launch",
        "spacecraft launch",
        "liftoff",
        "space mission",
    )
    TRACKED_ACCOUNTS: ClassVar[tuple[str, ...]] = (
        "NASA",
        "SpaceX",
        "Roscosmos",
        "CNSAWatcher",
        "NASASpaceflight",
        "RocketLab",
    )

    SEARCH_URL: ClassVar[str] = "https://api.twitter.com/2/tweets/search/recent"
    # Free tier: 180 requests per 15 min → ~5 s between requests to stay safe
    RATE_LIMIT_SECONDS: ClassVar[float] = 5.0
    MAX_RESULTS_PER_QUERY: ClassVar[int] = 10

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_launch_relevant(self, text: str) -> bool:
        """Return True if *text* contains at least one launch keyword.

        Args:
            text: Tweet body text to check.

        Returns:
            True when any keyword from ``_LAUNCH_KEYWORDS`` is found
            (case-insensitive).
        """
        lower = text.lower()
        return any(kw in lower for kw in _LAUNCH_KEYWORDS)

    def _get_bearer_token(self) -> str | None:
        """Read the Twitter bearer token from the environment.

        Returns:
            The bearer token string, or ``None`` when not configured.
        """
        return os.environ.get("TWITTER_BEARER_TOKEN")

    async def _fetch_search(
        self,
        client: httpx.AsyncClient,
        query: str,
    ) -> tuple[str | None, int | None]:
        """Execute a recent-search request for *query*.

        Args:
            client: Shared httpx async client (already carries auth header).
            query: Twitter search query string.

        Returns:
            Tuple of (response_text, http_status).  Both are ``None`` on
            network failure.
        """
        params: dict[str, str] = {
            "query": query,
            "max_results": str(self.MAX_RESULTS_PER_QUERY),
            "tweet.fields": "created_at,author_id,attachments",
            "expansions": "author_id,attachments.media_keys",
            "media.fields": "url,preview_image_url,type",
            "user.fields": "username",
        }
        try:
            response = await client.get(self.SEARCH_URL, params=params)
            return response.text, response.status_code
        except httpx.RequestError as exc:
            logger.warning("Twitter: network error for query '%s': %s", query, exc)
            return None, None

    async def _collect_tweets(
        self,
        client: httpx.AsyncClient,
    ) -> list[dict[str, Any]]:
        """Collect raw tweet dicts from search terms and tracked accounts.

        Each request is followed by a ``RATE_LIMIT_SECONDS`` sleep to stay
        within the free-tier rate limit (180 requests / 15 min).

        Args:
            client: Shared httpx async client.

        Returns:
            List of raw tweet dicts (may contain duplicates by ID).
        """
        raw_tweets: list[dict[str, Any]] = []
        users_map: dict[str, str] = {}  # author_id → username
        media_map: dict[str, str] = {}  # media_key → url

        for term in self.SEARCH_TERMS:
            text, status = await self._fetch_search(client, term)
            if text and status == 200:
                try:
                    data = json.loads(text)
                    tweets = data.get("data", [])
                    # Collect user lookup
                    includes = data.get("includes", {})
                    for user in includes.get("users", []):
                        users_map[user["id"]] = user.get("username", "unknown")
                    for media in includes.get("media", []):
                        url = media.get("url") or media.get("preview_image_url", "")
                        if url:
                            media_map[media["media_key"]] = url
                    # Annotate tweets with resolved username
                    for tweet in tweets:
                        tweet["_username"] = users_map.get(
                            tweet.get("author_id", ""), "unknown"
                        )
                        # Resolve media URLs
                        media_keys = tweet.get("attachments", {}).get("media_keys", [])
                        tweet["_image_urls"] = [
                            media_map[mk] for mk in media_keys if mk in media_map
                        ]
                    raw_tweets.extend(tweets)
                except json.JSONDecodeError:
                    logger.warning("Twitter: non-JSON response for query '%s'", term)
            await asyncio.sleep(self.RATE_LIMIT_SECONDS)

        # Fetch tweets from tracked accounts via ``from:`` operator
        for account in self.TRACKED_ACCOUNTS:
            text, status = await self._fetch_search(client, f"from:{account}")
            if text and status == 200:
                try:
                    data = json.loads(text)
                    tweets = data.get("data", [])
                    includes = data.get("includes", {})
                    for user in includes.get("users", []):
                        users_map[user["id"]] = user.get("username", "unknown")
                    for media in includes.get("media", []):
                        url = media.get("url") or media.get("preview_image_url", "")
                        if url:
                            media_map[media["media_key"]] = url
                    for tweet in tweets:
                        tweet["_username"] = users_map.get(
                            tweet.get("author_id", ""), account
                        )
                        media_keys = tweet.get("attachments", {}).get("media_keys", [])
                        tweet["_image_urls"] = [
                            media_map[mk] for mk in media_keys if mk in media_map
                        ]
                    raw_tweets.extend(tweets)
                except json.JSONDecodeError:
                    logger.warning(
                        "Twitter: non-JSON response for account '%s'", account
                    )
            await asyncio.sleep(self.RATE_LIMIT_SECONDS)

        return raw_tweets

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> dict[str, int]:
        """Scrape launch tweets from Twitter/X and upsert into the database.

        When ``TWITTER_BEARER_TOKEN`` is not set the scraper returns an
        empty result and logs a warning — it will **not** fail.

        Returns:
            Summary dict with keys ``total_fetched``, ``new_events``,
            ``updated_events``.
        """
        bearer_token = self._get_bearer_token()
        if not bearer_token:
            logger.warning("Twitter: TWITTER_BEARER_TOKEN not set — scraper disabled")
            return {"total_fetched": 0, "new_events": 0, "updated_events": 0}

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
                    scraper_class="openorbit.scrapers.twitter.TwitterScraper",
                    enabled=True,
                    source_tier=self.source_tier,
                )

            # Fetch tweets
            timeout = httpx.Timeout(30.0)
            async with httpx.AsyncClient(
                timeout=timeout,
                headers={
                    "User-Agent": "openOrbit/0.1.0 (OSINT aggregator)",
                    "Authorization": f"Bearer {bearer_token}",
                },
            ) as client:
                raw_tweets = await self._collect_tweets(client)

            # Deduplicate by tweet ID
            seen: dict[str, dict[str, Any]] = {}
            for tweet in raw_tweets:
                tid = tweet.get("id", "")
                if tid and tid not in seen:
                    seen[tid] = tweet

            # Filter to launch-relevant tweets
            relevant = [
                t for t in seen.values() if self._is_launch_relevant(t.get("text", ""))
            ]

            # Log scrape run
            scrape_record_id = await log_scrape_run(
                conn,
                source_id=source_id,
                url=self.SEARCH_URL,
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
                "Twitter: %d total, %d new, %d updated",
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
        """Parse a JSON array of Twitter tweet objects into launch events.

        Args:
            raw_data: JSON string — either a plain list of tweet dicts or
                the ``data`` wrapper from the search endpoint.

        Returns:
            List of :class:`LaunchEventCreate` models (one per tweet).

        Raises:
            ValueError: If *raw_data* is not valid JSON.
        """
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

        # Accept both a bare list and the {"data": [...]} wrapper
        tweets = data.get("data", []) if isinstance(data, dict) else data

        events: list[LaunchEventCreate] = []
        for tweet in tweets:
            tweet_id = tweet.get("id", "")
            text = tweet.get("text", "")
            created_at_raw = tweet.get("created_at", "")
            username = tweet.get("_username", "unknown")

            if not tweet_id or not text:
                continue

            # Clean display text (remove t.co links)
            display_text = _strip_urls(text)[:120]

            try:
                launch_date = datetime.fromisoformat(
                    created_at_raw.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                launch_date = datetime.now(UTC)

            slug = _make_slug(tweet_id)

            # Extract image URLs from resolved media
            image_urls: list[str] = tweet.get("_image_urls", [])

            events.append(
                LaunchEventCreate(
                    name=display_text,
                    launch_date=launch_date,
                    launch_date_precision="day",
                    provider=f"@{username}",
                    vehicle=None,
                    location=None,
                    pad=None,
                    launch_type="unknown",
                    status="scheduled",
                    slug=slug,
                    image_urls=image_urls,
                    claim_lifecycle="rumor",
                    event_kind="inferred",
                )
            )

        return events
