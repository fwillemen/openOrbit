"""Pure NOTAM text parser — no I/O, no side effects.

Classifies NOTAM text for launch-related content and extracts structured data
from Q-line coordinates and B/C-line validity windows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from openorbit.models.db import LaunchEventCreate

# Combined pattern for extracting ALL matched keywords from text
LAUNCH_KEYWORDS = re.compile(
    r"\b(SPACE LAUNCH|ROCKET|MISSILE|RANGE CLOSURE|SPACE VEHICLE|JATO)\b",
    re.IGNORECASE,
)

# Priority-ordered classification rules: first match wins.
# MISSILE is highest priority so it overrides other keywords (e.g., ROCKET + MISSILE → military).
_KEYWORD_RULES: list[
    tuple[re.Pattern[str], str, Literal["civilian", "military", "unknown"]]
] = [
    (re.compile(r"\bMISSILE\b", re.IGNORECASE), "MISSILE", "military"),
    (re.compile(r"\bSPACE LAUNCH\b", re.IGNORECASE), "SPACE LAUNCH", "civilian"),
    (re.compile(r"\bROCKET\b", re.IGNORECASE), "ROCKET", "civilian"),
    (re.compile(r"\bRANGE CLOSURE\b", re.IGNORECASE), "RANGE CLOSURE", "unknown"),
    (re.compile(r"\bSPACE VEHICLE\b", re.IGNORECASE), "SPACE VEHICLE", "civilian"),
    (re.compile(r"\bJATO\b", re.IGNORECASE), "JATO", "civilian"),
]

_Q_LINE_COORDS = re.compile(r"(\d{4}[NS])(\d{5}[EW])")
_VALIDITY_FMT = "%y%m%d%H%M"


@dataclass
class NotamMatch:
    """Result of parsing a single NOTAM text for launch relevance."""

    is_launch_related: bool
    launch_type: str  # "civilian" | "military" | "unknown"
    matched_keywords: list[str] = field(default_factory=list)
    raw_text: str = ""


def classify_notam(
    text: str,
) -> tuple[str | None, Literal["civilian", "military", "unknown"] | None]:
    """Classify NOTAM text by highest-priority launch keyword.

    Priority order: MISSILE → SPACE LAUNCH → ROCKET → RANGE CLOSURE →
    SPACE VEHICLE → JATO.  MISSILE is first so a combined ROCKET+MISSILE NOTAM
    is always flagged as military.

    Args:
        text: NOTAM text to classify.

    Returns:
        Tuple of (matched_keyword_label, launch_type), or (None, None) if no match.
    """
    for pattern, label, ltype in _KEYWORD_RULES:
        if pattern.search(text):
            return label, ltype
    return None, None


def parse_notam(notam_text: str) -> NotamMatch:
    """Parse NOTAM text for launch-related keywords.

    Extracts all keyword matches from the text; launch_type is determined by
    the highest-priority keyword (MISSILE overrides ROCKET, etc.).

    Args:
        notam_text: Raw NOTAM text to parse.

    Returns:
        NotamMatch with is_launch_related, launch_type, and all matched_keywords.
    """
    keyword, launch_type = classify_notam(notam_text)
    if keyword is None or launch_type is None:
        return NotamMatch(False, "unknown", [], notam_text)

    matched = [m.upper() for m in LAUNCH_KEYWORDS.findall(notam_text)]
    return NotamMatch(
        is_launch_related=True,
        launch_type=launch_type,
        matched_keywords=matched,
        raw_text=notam_text,
    )


def parse_q_line(q_line: str) -> dict[str, float | None]:
    """Extract latitude and longitude from a NOTAM Q-line.

    Coordinate segment format: ``3030N08145W`` → lat=30.5, lon=-81.75
    (degrees + minutes / 60, negated for S/W).

    Args:
        q_line: Raw Q-line string from NOTAM.

    Returns:
        Dict with ``lat`` and ``lon`` as floats, or None when unparseable.
    """
    match = _Q_LINE_COORDS.search(q_line)
    if not match:
        return {"lat": None, "lon": None}

    lat_str, lon_str = match.group(1), match.group(2)

    lat = float(lat_str[:2]) + float(lat_str[2:4]) / 60.0
    if lat_str.endswith("S"):
        lat = -lat

    lon = float(lon_str[:3]) + float(lon_str[3:5]) / 60.0
    if lon_str.endswith("W"):
        lon = -lon

    return {"lat": lat, "lon": lon}


def parse_validity(
    b_line: str, c_line: str
) -> tuple[datetime | None, datetime | None]:
    """Parse NOTAM validity window from B-line (start) and C-line (end).

    Args:
        b_line: Start validity string (YYMMDDHHMM format).
        c_line: End validity string (YYMMDDHHMM format, or ``PERM``).

    Returns:
        Tuple of (start_datetime, end_datetime).  end_datetime is None for
        ``PERM``.  Returns (None, None) if the B-line cannot be parsed.
    """
    try:
        start = datetime.strptime(b_line.strip(), _VALIDITY_FMT).replace(tzinfo=UTC)
    except ValueError:
        return None, None

    if c_line.strip().upper() == "PERM":
        return start, None

    try:
        end = datetime.strptime(c_line.strip(), _VALIDITY_FMT).replace(tzinfo=UTC)
    except ValueError:
        return start, None

    return start, end


def extract_launch_candidates(notams: list[dict[str, Any]]) -> list[LaunchEventCreate]:
    """Extract launch-related events from a list of raw NOTAM dicts.

    Iterates the FAA API ``items`` list, classifies each NOTAM's E-line text,
    and converts matches to LaunchEventCreate models ready for DB upsert.

    Args:
        notams: List of raw NOTAM dicts from FAA API.

    Returns:
        LaunchEventCreate models for all launch-related NOTAMs.
    """
    events: list[LaunchEventCreate] = []

    for notam in notams:
        notam_id: str = str(notam.get("notamNumber", notam.get("id", "UNKNOWN")))
        e_text = notam.get("traditionalMessageFrom4thLine") or notam.get(
            "icaoMessage", ""
        )

        keyword, launch_type = classify_notam(str(e_text))
        if keyword is None or launch_type is None:
            continue

        coords = parse_q_line(str(notam.get("qLine", "")))
        start, _ = parse_validity(
            str(notam.get("startValidity", "")),
            str(notam.get("endValidity", "")),
        )
        launch_date = start if start is not None else datetime.now(UTC)
        # LaunchEventCreate only accepts the standard precision literals; use
        # "month" when no exact start date is available (widest imprecision bucket).
        precision: Literal["day", "month"] = "day" if start is not None else "month"

        lat, lon = coords.get("lat"), coords.get("lon")
        if lat is not None and lon is not None:
            location: str | None = (
                f"{lat:.2f}N/{abs(lon):.2f}{'W' if lon < 0 else 'E'}"
            )
        else:
            location = None

        pad_raw = notam.get("location", "")
        pad: str | None = str(pad_raw).strip() if pad_raw else None

        events.append(
            LaunchEventCreate(
                name=f"NOTAM {notam_id}: {keyword}",
                launch_date=launch_date,
                launch_date_precision=precision,
                provider="FAA",
                vehicle=None,
                location=location,
                pad=pad,
                launch_type=launch_type,
                status="scheduled",
                slug=f"notam-{notam_id.replace('/', '-')}",
            )
        )

    return events
