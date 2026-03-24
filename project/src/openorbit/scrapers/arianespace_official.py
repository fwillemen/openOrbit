"""Arianespace official feed scraper (non-credentialed)."""

from __future__ import annotations

import asyncio

from openorbit.scrapers.public_feed import PublicFeedScraper, run_public_feed_scraper_cli


class ArianespaceOfficialScraper(PublicFeedScraper):
    """Scraper for Arianespace public feed."""

    source_name = "arianespace_official"
    source_url = "https://www.arianespace.com/feed/"
    SOURCE_NAME = "Arianespace Official Feed"
    PROVIDER_NAME = "Arianespace"
    KEYWORDS = (
        "launch",
        "ariane",
        "vega",
        "satellite",
        "liftoff",
    )
    LOCATION_HINTS = (
        ("kourou", "Guiana Space Centre, French Guiana"),
        ("guiana", "Guiana Space Centre, French Guiana"),
    )
    VEHICLE_HINTS = (
        ("ariane 6", "Ariane 6"),
        ("ariane", "Ariane"),
        ("vega-c", "Vega-C"),
        ("vega", "Vega"),
    )

    @classmethod
    def feed_region(cls) -> str:
        """Return regional scope for this adapter."""
        return "europe"


async def main() -> None:
    """CLI entry point for Arianespace feed scraper."""
    await run_public_feed_scraper_cli(
        ArianespaceOfficialScraper(), "Arianespace Official Feed"
    )


if __name__ == "__main__":
    asyncio.run(main())
