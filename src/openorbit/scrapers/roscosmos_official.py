"""Roscosmos official feed scraper (non-credentialed)."""

from __future__ import annotations

import asyncio
from typing import ClassVar

from openorbit.scrapers.public_feed import (
    PublicFeedScraper,
    run_public_feed_scraper_cli,
)


class RoscosmosOfficialScraper(PublicFeedScraper):
    """Scraper for Roscosmos public news feed.

    Monitors the Russian federal space agency's English-language RSS feed for
    launch announcements, mission updates, and rocket activity.  The feed is
    classified as Tier 1 (official/regulatory) and produces ``confirmed``
    claims with ``observed`` event kind.
    """

    source_name: ClassVar[str] = "roscosmos_official"
    source_url: ClassVar[str] = "https://www.roscosmos.ru/eng/rss.xml"
    SOURCE_NAME: ClassVar[str] = "Roscosmos Official Feed"
    PROVIDER_NAME: ClassVar[str] = "Roscosmos"
    KEYWORDS: ClassVar[tuple[str, ...]] = (
        "launch",
        "soyuz",
        "proton",
        "angara",
        "rocket",
        "satellite",
        "spacecraft",
        "liftoff",
        "cosmodrome",
    )
    LOCATION_HINTS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("baikonur", "Baikonur Cosmodrome, Kazakhstan"),
        ("plesetsk", "Plesetsk Cosmodrome, Russia"),
        ("vostochny", "Vostochny Cosmodrome, Russia"),
        ("vostochni", "Vostochny Cosmodrome, Russia"),
    )
    VEHICLE_HINTS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("soyuz-2.1b", "Soyuz-2.1b"),
        ("soyuz-2.1a", "Soyuz-2.1a"),
        ("soyuz-2", "Soyuz-2"),
        ("soyuz", "Soyuz"),
        ("angara-a5", "Angara-A5"),
        ("angara", "Angara"),
        ("proton-m", "Proton-M"),
        ("proton", "Proton"),
    )

    @classmethod
    def feed_region(cls) -> str:
        """Return regional scope for this adapter."""
        return "eurasia"


async def main() -> None:
    """CLI entry point for Roscosmos feed scraper."""
    await run_public_feed_scraper_cli(RoscosmosOfficialScraper(), "Roscosmos Official Feed")


if __name__ == "__main__":
    asyncio.run(main())
