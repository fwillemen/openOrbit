"""CNSA official feed scraper (non-credentialed)."""

from __future__ import annotations

import asyncio

from openorbit.scrapers.public_feed import (
    PublicFeedScraper,
    run_public_feed_scraper_cli,
)


class CNSAOfficialScraper(PublicFeedScraper):
    """Scraper for CNSA public updates feed endpoint."""

    source_name = "cnsa_official"
    source_url = "https://www.cnsa.gov.cn/english/rss.xml"
    SOURCE_NAME = "CNSA Official Feed"
    PROVIDER_NAME = "CNSA"
    KEYWORDS = (
        "launch",
        "long march",
        "satellite",
        "spacecraft",
        "rocket",
    )
    LOCATION_HINTS = (
        ("wenchang", "Wenchang Space Launch Site, China"),
        ("jiuquan", "Jiuquan Satellite Launch Center, China"),
        ("xichang", "Xichang Satellite Launch Center, China"),
        ("taiyuan", "Taiyuan Satellite Launch Center, China"),
    )
    VEHICLE_HINTS = (
        ("long march 5", "Long March 5"),
        ("long march 7", "Long March 7"),
        ("long march", "Long March"),
    )

    @classmethod
    def feed_region(cls) -> str:
        """Return regional scope for this adapter."""
        return "asia"


async def main() -> None:
    """CLI entry point for CNSA feed scraper."""
    await run_public_feed_scraper_cli(CNSAOfficialScraper(), "CNSA Official Feed")


if __name__ == "__main__":
    asyncio.run(main())
