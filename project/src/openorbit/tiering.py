"""Result tier classification helpers.

Defines dashboard-friendly tiers derived from confidence and source corroboration.
"""

from __future__ import annotations

from typing import Literal, TypeAlias

ResultTier: TypeAlias = Literal["emerging", "tracked", "verified"]

# Tier thresholds are intentionally conservative for the top tier:
# verified requires both high confidence and multi-source corroboration.
VERIFIED_MIN_CONFIDENCE = 80.0
VERIFIED_MIN_ATTRIBUTIONS = 2
TRACKED_MIN_CONFIDENCE = 60.0


def classify_result_tier(confidence_score: float, attribution_count: int) -> ResultTier:
    """Classify an event into a dashboard result tier.

    Args:
        confidence_score: Event confidence score (0-100 scale).
        attribution_count: Number of source attributions confirming the event.

    Returns:
        One of ``verified``, ``tracked``, or ``emerging``.
    """
    if (
        confidence_score >= VERIFIED_MIN_CONFIDENCE
        and attribution_count >= VERIFIED_MIN_ATTRIBUTIONS
    ):
        return "verified"
    if confidence_score >= TRACKED_MIN_CONFIDENCE:
        return "tracked"
    return "emerging"


def result_tier_sql_expr(event_alias: str = "e") -> str:
    """Build SQL CASE expression that mirrors ``classify_result_tier``.

    Args:
        event_alias: SQL table alias for launch_events rows.

    Returns:
        SQL CASE expression string yielding tier labels.
    """
    return (
        "CASE "
        f"WHEN {event_alias}.confidence_score >= {VERIFIED_MIN_CONFIDENCE} "
        "AND (SELECT COUNT(*) FROM event_attributions "
        f"WHERE event_slug = {event_alias}.slug) >= {VERIFIED_MIN_ATTRIBUTIONS} "
        "THEN 'verified' "
        f"WHEN {event_alias}.confidence_score >= {TRACKED_MIN_CONFIDENCE} "
        "THEN 'tracked' "
        "ELSE 'emerging' "
        "END"
    )