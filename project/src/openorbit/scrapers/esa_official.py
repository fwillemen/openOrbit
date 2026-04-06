"""ESA official feed scraper (non-credentialed)."""

from __future__ import annotations

import asyncio

from openorbit.scrapers.public_feed import (
    PublicFeedScraper,
    run_public_feed_scraper_cli,
)


class ESAOfficialScraper(PublicFeedScraper):
    """Scraper for ESA's public Space Transportation RSS feed."""

    source_name = "esa_official"
    source_url = "https://www.esa.int/rssfeed/Our_Activities/Space_Transportation"
    SOURCE_NAME = "ESA Official Feed"
    PROVIDER_NAME = "ESA"
    KEYWORDS = (
        "launch",
        "ariane",
        "vega",
        "satellite",
        "liftoff",
    )
    LOCATION_HINTS = (
        ("kourou", "Guiana Space Centre, French Guiana"),
        ("guiana space centre", "Guiana Space Centre, French Guiana"),
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
    """CLI entry point for ESA feed scraper."""
    await run_public_feed_scraper_cli(ESAOfficialScraper(), "ESA Official Feed")


if __name__ == "__main__":
    asyncio.run(main())
