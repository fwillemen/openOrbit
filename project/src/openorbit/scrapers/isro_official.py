"""ISRO official feed scraper (non-credentialed)."""

from __future__ import annotations

import asyncio

from openorbit.scrapers.public_feed import (
    PublicFeedScraper,
    run_public_feed_scraper_cli,
)


class ISROOfficialScraper(PublicFeedScraper):
    """Scraper for ISRO public news feed."""

    source_name = "isro_official"
    source_url = "https://www.isro.gov.in/rss.xml"
    SOURCE_NAME = "ISRO Official Feed"
    PROVIDER_NAME = "ISRO"
    KEYWORDS = (
        "launch",
        "gslv",
        "pslv",
        "satellite",
        "rocket",
    )
    LOCATION_HINTS = (
        ("sriharikota", "Satish Dhawan Space Centre, India"),
        ("satish dhawan", "Satish Dhawan Space Centre, India"),
    )
    VEHICLE_HINTS = (
        ("pslv", "PSLV"),
        ("gslv", "GSLV"),
        ("lvm3", "LVM3"),
        ("sslv", "SSLV"),
    )

    @classmethod
    def feed_region(cls) -> str:
        """Return regional scope for this adapter."""
        return "asia"


async def main() -> None:
    """CLI entry point for ISRO feed scraper."""
    await run_public_feed_scraper_cli(ISROOfficialScraper(), "ISRO Official Feed")


if __name__ == "__main__":
    asyncio.run(main())
