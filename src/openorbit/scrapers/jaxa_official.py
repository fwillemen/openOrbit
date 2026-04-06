"""JAXA official feed scraper (non-credentialed)."""

from __future__ import annotations

import asyncio

from openorbit.scrapers.public_feed import (
    PublicFeedScraper,
    run_public_feed_scraper_cli,
)


class JAXAOfficialScraper(PublicFeedScraper):
    """Scraper for JAXA's public press feed."""

    source_name = "jaxa_official"
    source_url = "https://global.jaxa.jp/press/rss.xml"
    SOURCE_NAME = "JAXA Official Feed"
    PROVIDER_NAME = "JAXA"
    KEYWORDS = (
        "launch",
        "h3",
        "h-ii",
        "satellite",
        "rocket",
    )
    LOCATION_HINTS = (
        ("tanegashima", "Tanegashima Space Center, Japan"),
        ("uchinoura", "Uchinoura Space Center, Japan"),
    )
    VEHICLE_HINTS = (
        ("h3", "H3"),
        ("h-iia", "H-IIA"),
        ("h-iib", "H-IIB"),
        ("epsilon", "Epsilon"),
    )

    @classmethod
    def feed_region(cls) -> str:
        """Return regional scope for this adapter."""
        return "asia"


async def main() -> None:
    """CLI entry point for JAXA feed scraper."""
    await run_public_feed_scraper_cli(JAXAOfficialScraper(), "JAXA Official Feed")


if __name__ == "__main__":
    asyncio.run(main())
