"""4chan imageboard scraper for launch-related threads.

Fetches threads from 4chan's public JSON API by scanning the catalog of
curated boards (primarily /sci/) for launch-related discussions. Posts
are classified as Tier 3 (Analytical/Speculative) evidence.

Image URLs for files attached to opening posts are captured in
``image_urls`` for downstream analysis.

No authentication required — all requests use 4chan's public read-only
JSON API (https://github.com/4chan/4chan-API).
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
        "spacex",
        "nasa",
        "starship",
        "falcon",
    }
)


def _make_slug(board: str, thread_no: int) -> str:
    """Generate a deterministic slug from a 4chan board and thread number.

    Args:
        board: Board code (e.g. ``sci``).
        thread_no: Thread number.

    Returns:
        Slug of the form ``4chan-{12-char sha1}``.
    """
    digest = hashlib.sha1(f"4chan|/{board}/{thread_no}".encode()).hexdigest()[:12]
    return f"4chan-{digest}"


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities.

    4chan API returns ``com`` (comment) as HTML with ``<br>`` line breaks,
    ``<a>`` quote links, ``<span>`` greentext, etc.

    Args:
        text: HTML comment text from the 4chan API.

    Returns:
        Plain text with HTML stripped and entities decoded.
    """
    text = text.replace("<br>", " ").replace("<br/>", " ")
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#039;", "'")
    return text.strip()


def _build_image_url(board: str, tim: int, ext: str) -> str:
    """Build a full image URL from 4chan's CDN.

    Args:
        board: Board code (e.g. ``sci``).
        tim: Unix timestamp filename assigned by 4chan.
        ext: File extension (e.g. ``.jpg``).

    Returns:
        Full URL to the image on 4chan's CDN.
    """
    return f"https://i.4cdn.org/{board}/{tim}{ext}"


class FourChanScraper(BaseScraper):
    """Scraper for launch-related threads on 4chan.

    Scans the catalog of configured boards for threads matching
    launch-related keywords. Uses 4chan's public read-only JSON API.
    No authentication required.
    """

    source_name: ClassVar[str] = "4chan"
    source_url: ClassVar[str] = "https://a.4cdn.org"
    source_tier: ClassVar[int] = 3
    evidence_type: ClassVar[str] = "media"
    refresh_interval_hours: ClassVar[int] = 2

    BOARDS: ClassVar[tuple[str, ...]] = ("sci",)
    LAUNCH_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "launch",
        "liftoff",
        "rocket",
        "satellite",
        "spacecraft",
        "mission",
        "orbit",
        "spacex",
        "nasa",
        "starship",
        "falcon",
    )
    MAX_THREADS_PER_BOARD: ClassVar[int] = 25

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_launch_relevant(self, text: str) -> bool:
        """Return True if *text* contains at least one launch keyword.

        Args:
            text: Thread subject or comment text to check.

        Returns:
            True when any keyword from ``_LAUNCH_KEYWORDS`` is found
            (case-insensitive).
        """
        lower = text.lower()
        return any(kw in lower for kw in _LAUNCH_KEYWORDS)

    async def _fetch_catalog(
        self,
        client: httpx.AsyncClient,
        board: str,
    ) -> list[dict[str, Any]]:
        """Fetch the thread catalog for a board.

        The catalog endpoint returns all threads grouped by page. We
        flatten them into a single list, limited to :attr:`MAX_THREADS_PER_BOARD`.

        Args:
            client: Shared httpx async client.
            board: Board code (e.g. ``sci``).

        Returns:
            List of raw thread OP dicts from the catalog.
        """
        url = f"https://a.4cdn.org/{board}/catalog.json"
        try:
            response = await client.get(url)
            if response.status_code == 200:
                pages: list[dict[str, Any]] = response.json()
                threads: list[dict[str, Any]] = []
                for page in pages:
                    for thread in page.get("threads", []):
                        threads.append(thread)
                        if len(threads) >= self.MAX_THREADS_PER_BOARD:
                            return threads
                return threads
            logger.warning(
                "4chan: HTTP %s fetching /%s/ catalog",
                response.status_code,
                board,
            )
        except httpx.RequestError as exc:
            logger.warning("4chan: network error fetching /%s/ catalog: %s", board, exc)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("4chan: parse error for /%s/ catalog: %s", board, exc)
        return []

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> dict[str, int]:
        """Scrape launch threads from 4chan boards and upsert into the database.

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
                    scraper_class="openorbit.scrapers.fourchan.FourChanScraper",
                    enabled=True,
                    source_tier=self.source_tier,
                )

            # Fetch thread catalogs from all boards
            timeout = httpx.Timeout(30.0)
            all_threads: list[dict[str, Any]] = []
            async with httpx.AsyncClient(
                timeout=timeout,
                headers={"User-Agent": "openOrbit/0.1.0 (OSINT aggregator)"},
            ) as client:
                for board in self.BOARDS:
                    threads = await self._fetch_catalog(client, board)
                    # Tag each thread with its board for slug generation
                    for thread in threads:
                        thread["_board"] = board
                    all_threads.extend(threads)

            # Deduplicate by board+thread_no
            seen: dict[str, dict[str, Any]] = {}
            for thread in all_threads:
                board = thread.get("_board", "sci")
                thread_no = thread.get("no", 0)
                key = f"/{board}/{thread_no}"
                if key not in seen:
                    seen[key] = thread

            # Filter to launch-relevant threads
            relevant = [
                t
                for t in seen.values()
                if self._is_launch_relevant(
                    t.get("sub", "") + " " + _strip_html(t.get("com", ""))
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
                "4chan: %d total, %d new, %d updated",
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
        """Parse a JSON array of 4chan thread dicts into launch events.

        Args:
            raw_data: JSON string — a list of 4chan catalog thread dicts.

        Returns:
            List of :class:`LaunchEventCreate` models (one per thread).

        Raises:
            ValueError: If *raw_data* is not valid JSON.
        """
        try:
            threads: list[dict[str, Any]] = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

        if not isinstance(threads, list):
            raise ValueError("Expected a JSON array of 4chan threads")

        events: list[LaunchEventCreate] = []
        for thread in threads:
            thread_no: int = thread.get("no", 0)
            board: str = thread.get("_board", "sci")
            subject = thread.get("sub", "")
            comment = _strip_html(thread.get("com", ""))
            timestamp = thread.get("time", 0)

            if not thread_no:
                continue

            # Use subject if available, otherwise first 120 chars of comment
            display_text = (subject or comment)[:120]
            if not display_text:
                continue

            # Parse timestamp
            try:
                launch_date = datetime.fromtimestamp(float(timestamp), tz=UTC)
            except (ValueError, TypeError, OSError):
                launch_date = datetime.now(UTC)

            # Extract image URL from OP
            image_urls: list[str] = []
            tim = thread.get("tim")
            ext = thread.get("ext", "")
            if tim and ext:
                image_urls.append(_build_image_url(board, tim, ext))

            slug = _make_slug(board, thread_no)
            events.append(
                LaunchEventCreate(
                    name=display_text,
                    launch_date=launch_date,
                    launch_date_precision="day",
                    provider=f"4chan/{board}",
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
