"""Reddit scraper for launch-related posts from space subreddits.

Fetches posts from Reddit's public JSON API by polling curated subreddits
for launch-related discussions. Posts are classified as Tier 3
(Analytical/Speculative) evidence. No authentication required — all
requests use Reddit's unauthenticated ``.json`` endpoint suffix.

Image URLs attached to posts (direct links, Reddit-hosted images, and
gallery items) are captured in ``image_urls`` for downstream analysis.
"""

from __future__ import annotations

import hashlib
import json
import logging
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

_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp"}
)


def _make_slug(permalink: str) -> str:
    """Generate a deterministic slug from a Reddit post permalink.

    Args:
        permalink: Reddit post permalink (e.g. ``/r/spacex/comments/abc123/...``).

    Returns:
        Slug of the form ``reddit-{12-char sha1}``.
    """
    digest = hashlib.sha1(f"reddit|{permalink}".encode()).hexdigest()[:12]
    return f"reddit-{digest}"


def _extract_image_urls(post: dict[str, Any]) -> list[str]:
    """Extract image URLs from a Reddit post dict.

    Handles direct image links (i.redd.it, imgur), Reddit galleries
    (``gallery_data`` + ``media_metadata``), and ``preview`` image URLs.

    Args:
        post: Reddit post ``data`` dict from the JSON API.

    Returns:
        Deduplicated list of image URLs found in the post.
    """
    urls: list[str] = []
    url = post.get("url", "")

    # Direct image link (i.redd.it, imgur, etc.)
    if any(url.lower().endswith(ext) for ext in _IMAGE_EXTENSIONS):
        urls.append(url)

    # Reddit-hosted image (post_hint == "image")
    if post.get("post_hint") == "image" and url and url not in urls:
        urls.append(url)

    # Gallery posts
    media_metadata: dict[str, Any] = post.get("media_metadata") or {}
    for _media_id, meta in media_metadata.items():
        if meta.get("status") == "valid" and meta.get("s", {}).get("u"):
            img_url: str = meta["s"]["u"].replace("&amp;", "&")
            if img_url not in urls:
                urls.append(img_url)

    # Preview images
    preview = post.get("preview", {})
    for img in preview.get("images", []):
        source_url = img.get("source", {}).get("url", "")
        if source_url:
            cleaned = source_url.replace("&amp;", "&")
            if cleaned not in urls:
                urls.append(cleaned)

    return urls


def _strip_markdown(text: str) -> str:
    """Remove common Markdown formatting from text.

    Args:
        text: Markdown-formatted text.

    Returns:
        Plain text with Markdown syntax removed.
    """
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_~`#>]+", "", text)
    return text.strip()


class RedditScraper(BaseScraper):
    """Scraper for launch-related posts on Reddit.

    Queries the public Reddit JSON API (``<subreddit>/new.json``) for
    recent posts in curated space subreddits. No authentication required.
    """

    source_name: ClassVar[str] = "reddit"
    source_url: ClassVar[str] = "https://www.reddit.com"
    source_tier: ClassVar[int] = 3
    evidence_type: ClassVar[str] = "media"
    refresh_interval_hours: ClassVar[int] = 2

    SUBREDDITS: ClassVar[tuple[str, ...]] = (
        "spacex",
        "spaceflight",
        "ula",
        "rocketlab",
        "nasa",
        "space",
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
    POSTS_PER_SUBREDDIT: ClassVar[int] = 25

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_launch_relevant(self, text: str) -> bool:
        """Return True if *text* contains at least one launch keyword.

        Args:
            text: Post text to check.

        Returns:
            True when any keyword from ``_LAUNCH_KEYWORDS`` is found
            (case-insensitive).
        """
        lower = text.lower()
        return any(kw in lower for kw in _LAUNCH_KEYWORDS)

    async def _fetch_subreddit(
        self,
        client: httpx.AsyncClient,
        subreddit: str,
    ) -> list[dict[str, Any]]:
        """Fetch recent posts from a subreddit.

        Args:
            client: Shared httpx async client.
            subreddit: Subreddit name (without ``r/`` prefix).

        Returns:
            List of raw Reddit post ``data`` dicts.
        """
        url = f"https://www.reddit.com/r/{subreddit}/new.json"
        try:
            response = await client.get(
                url,
                params={"limit": str(self.POSTS_PER_SUBREDDIT), "raw_json": "1"},
            )
            if response.status_code == 200:
                data = response.json()
                children = data.get("data", {}).get("children", [])
                return [child.get("data", {}) for child in children]
            logger.warning(
                "Reddit: HTTP %s fetching r/%s",
                response.status_code,
                subreddit,
            )
        except httpx.RequestError as exc:
            logger.warning("Reddit: network error fetching r/%s: %s", subreddit, exc)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Reddit: parse error for r/%s: %s", subreddit, exc)
        return []

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> dict[str, int]:
        """Scrape launch posts from Reddit subreddits and upsert into the database.

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
                    scraper_class="openorbit.scrapers.reddit.RedditScraper",
                    enabled=True,
                    source_tier=self.source_tier,
                )

            # Fetch posts from all subreddits
            timeout = httpx.Timeout(30.0)
            all_posts: list[dict[str, Any]] = []
            async with httpx.AsyncClient(
                timeout=timeout,
                headers={"User-Agent": "openOrbit/0.1.0 (OSINT aggregator)"},
            ) as client:
                for subreddit in self.SUBREDDITS:
                    posts = await self._fetch_subreddit(client, subreddit)
                    all_posts.extend(posts)

            # Deduplicate by permalink
            seen: dict[str, dict[str, Any]] = {}
            for post in all_posts:
                permalink = post.get("permalink", "")
                if permalink and permalink not in seen:
                    seen[permalink] = post

            # Filter to launch-relevant posts
            relevant = [
                p
                for p in seen.values()
                if self._is_launch_relevant(
                    p.get("title", "") + " " + p.get("selftext", "")
                )
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
                "Reddit: %d total, %d new, %d updated",
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
        """Parse a JSON array of Reddit post dicts into launch events.

        Args:
            raw_data: JSON string — a list of Reddit post ``data`` dicts.

        Returns:
            List of :class:`LaunchEventCreate` models (one per post).

        Raises:
            ValueError: If *raw_data* is not valid JSON.
        """
        try:
            posts: list[dict[str, Any]] = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

        if not isinstance(posts, list):
            raise ValueError("Expected a JSON array of Reddit posts")

        events: list[LaunchEventCreate] = []
        for post in posts:
            permalink = post.get("permalink", "")
            title = post.get("title", "")
            author = post.get("author", "unknown")
            created_utc = post.get("created_utc", 0)

            if not permalink or not title:
                continue

            # Parse timestamp
            try:
                launch_date = datetime.fromtimestamp(float(created_utc), tz=UTC)
            except (ValueError, TypeError, OSError):
                launch_date = datetime.now(UTC)

            # Extract image URLs
            image_urls = _extract_image_urls(post)

            # Build display name from title
            display_text = _strip_markdown(title)[:120]

            slug = _make_slug(permalink)
            events.append(
                LaunchEventCreate(
                    name=display_text,
                    launch_date=launch_date,
                    launch_date_precision="day",
                    provider=f"u/{author}",
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
