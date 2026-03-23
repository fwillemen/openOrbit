"""Launch type classifier — pure function, no I/O."""

from __future__ import annotations

from typing import Literal

from openorbit.pipeline.military_programs import MILITARY_PROGRAMS

LaunchType = Literal["civilian", "military", "public_report", "unknown"]

_VALID_TYPES: frozenset[str] = frozenset({"civilian", "military", "public_report", "unknown"})


def classify_launch_type(
    provider: str,
    source_name: str = "",
    keywords: list[str] | None = None,
    hint: str | None = None,
) -> LaunchType:
    """Classify the launch type based on provider, source, and keywords.

    Priority order:
    1. If hint is already a valid launch type, return it.
    2. If 'MISSILE' in keywords → ``public_report``.
    3. If provider (lowercased) matches any MILITARY_PROGRAMS entry → ``military``.
    4. If source_name (lowercased) contains 'military' or 'dod' → ``military``.
    5. Default → ``civilian``.

    Args:
        provider: Launch provider name (after alias resolution).
        source_name: OSINT source name (e.g. "FAA NOTAM Database").
        keywords: Keywords extracted from NOTAM text (from notam_parser).
        hint: Existing launch_type value from the scraper (may be None).

    Returns:
        Validated launch type string.
    """
    if hint in _VALID_TYPES:
        return hint  # type: ignore[return-value]

    kw_upper = {k.upper() for k in (keywords or [])}
    if "MISSILE" in kw_upper:
        return "public_report"

    provider_lower = provider.strip().lower()
    if any(prog in provider_lower for prog in MILITARY_PROGRAMS):
        return "military"

    source_lower = source_name.strip().lower()
    if "military" in source_lower or "dod" in source_lower:
        return "military"

    return "civilian"
