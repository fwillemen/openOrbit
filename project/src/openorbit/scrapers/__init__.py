"""Scraper modules for OSINT data collection.

Importing this package registers all built-in scrapers with the global registry.
"""

from openorbit.scrapers import (  # noqa: F401
	arianespace_official,
	celestrak,
	cnsa_official,
	commercial,
	esa_official,
	isro_official,
	jaxa_official,
	notams,
	public_feed,
	space_agency,
	spacex_official,
)
