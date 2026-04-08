"""Scraper modules for OSINT data collection.

Importing this package registers all built-in scrapers with the global registry.
"""

from openorbit.scrapers import (  # noqa: F401
    arianespace_official,
    bluesky,
    celestrak,
    cnsa_official,
    commercial,
    esa_official,
    fourchan,
    isro_official,
    jaxa_official,
    mastodon,
    notams,
    public_feed,
    reddit,
    space_agency,
    spacex_official,
    twitter,
)
