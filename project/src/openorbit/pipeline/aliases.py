"""Provider and launch pad alias tables for the normalisation pipeline."""

from __future__ import annotations

# Maps lower-cased full provider names → canonical short names.
PROVIDER_ALIASES: dict[str, str] = {
    "space exploration technologies": "SpaceX",
    "space exploration technologies corp": "SpaceX",
    "national aeronautics and space administration": "NASA",
    "united launch alliance": "ULA",
    "rocket lab usa": "Rocket Lab",
    "china aerospace science and technology corporation": "CASC",
    "roscosmos state corporation": "Roscosmos",
    "arianespace sa": "Arianespace",
    "blue origin llc": "Blue Origin",
    "northrop grumman innovation systems": "Northrop Grumman",
    "virgin orbit llc": "Virgin Orbit",
}

# Maps launch pad identifiers → geographic metadata.
PAD_LOCATIONS: dict[str, dict[str, float | str]] = {
    "LC-39A": {
        "lat": 28.6080,
        "lon": -80.6043,
        "location": "Kennedy Space Center, FL, USA",
    },
    "SLC-40": {
        "lat": 28.5620,
        "lon": -80.5773,
        "location": "Cape Canaveral SFS, FL, USA",
    },
    "SLC-4E": {
        "lat": 34.6321,
        "lon": -120.6110,
        "location": "Vandenberg SFB, CA, USA",
    },
    "Site 1/5": {
        "lat": 45.9200,
        "lon": 63.3420,
        "location": "Baikonur Cosmodrome, Kazakhstan",
    },
    "LP-0A": {
        "lat": 37.8329,
        "lon": -75.4880,
        "location": "Wallops Island, VA, USA",
    },
    "SLC-8": {
        "lat": 34.6400,
        "lon": -120.5950,
        "location": "Vandenberg SFB, CA, USA",
    },
    "LC-1": {
        "lat": 48.5170,
        "lon": 45.7640,
        "location": "Kapustin Yar, Russia",
    },
    "ELA-3": {
        "lat": 5.2390,
        "lon": -52.7680,
        "location": "Guiana Space Centre, French Guiana",
    },
    "LC-200/39": {
        "lat": 28.4756,
        "lon": -80.5290,
        "location": "Cape Canaveral SFS, FL, USA",
    },
    "LA-0B": {
        "lat": -2.3736,
        "lon": -44.3760,
        "location": "Alcântara, Maranhão, Brazil",
    },
    "Starbase": {
        "lat": 25.9972,
        "lon": -97.1561,
        "location": "Starbase, TX, USA",
    },
}
