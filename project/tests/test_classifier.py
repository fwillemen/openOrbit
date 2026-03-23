"""Tests for openorbit.pipeline.classifier — ≥8 distinct scenarios."""

from __future__ import annotations

import pytest

from openorbit.pipeline.classifier import LaunchType, classify_launch_type


# ---------------------------------------------------------------------------
# Scenario 1: MISSILE keyword → public_report
# ---------------------------------------------------------------------------
def test_missile_keyword_returns_public_report() -> None:
    result = classify_launch_type(
        provider="SpaceX",
        keywords=["MISSILE", "RANGE"],
    )
    assert result == "public_report"


# ---------------------------------------------------------------------------
# Scenario 2: Known military provider → military
# ---------------------------------------------------------------------------
def test_known_military_provider_returns_military() -> None:
    result = classify_launch_type(provider="Department of Defense")
    assert result == "military"


# ---------------------------------------------------------------------------
# Scenario 3: Unknown provider, no keywords → civilian
# ---------------------------------------------------------------------------
def test_unknown_provider_no_keywords_returns_civilian() -> None:
    result = classify_launch_type(provider="AcmeSat Inc.")
    assert result == "civilian"


# ---------------------------------------------------------------------------
# Scenario 4: Non-MISSILE keyword + SpaceX → civilian
# ---------------------------------------------------------------------------
def test_rocket_keyword_non_military_provider_returns_civilian() -> None:
    result = classify_launch_type(
        provider="SpaceX",
        keywords=["ROCKET", "DEBRIS"],
    )
    assert result == "civilian"


# ---------------------------------------------------------------------------
# Scenario 5: source_name containing "military" → military
# ---------------------------------------------------------------------------
def test_military_in_source_name_returns_military() -> None:
    result = classify_launch_type(
        provider="Unknown Provider",
        source_name="US Military Launch Tracker",
    )
    assert result == "military"


# ---------------------------------------------------------------------------
# Scenario 6: Valid hint wins regardless of other signals
# ---------------------------------------------------------------------------
def test_valid_hint_takes_priority_over_keywords() -> None:
    result = classify_launch_type(
        provider="SpaceX",
        keywords=["MISSILE"],
        hint="public_report",
    )
    assert result == "public_report"


def test_valid_hint_civilian_wins_over_military_provider() -> None:
    result = classify_launch_type(
        provider="Department of Defense",
        hint="civilian",
    )
    assert result == "civilian"


# ---------------------------------------------------------------------------
# Scenario 7: MISSILE keyword + non-military provider → public_report
# ---------------------------------------------------------------------------
def test_missile_keyword_with_non_military_provider_returns_public_report() -> None:
    result = classify_launch_type(
        provider="Rocket Lab",
        keywords=["SATELLITE", "MISSILE", "RECOVERY"],
    )
    assert result == "public_report"


# ---------------------------------------------------------------------------
# Scenario 8: USSF provider → military
# ---------------------------------------------------------------------------
def test_ussf_provider_returns_military() -> None:
    result = classify_launch_type(provider="USSF")
    assert result == "military"


# ---------------------------------------------------------------------------
# Scenario 9: source_name containing "dod" → military
# ---------------------------------------------------------------------------
def test_dod_in_source_name_returns_military() -> None:
    result = classify_launch_type(
        provider="Unknown",
        source_name="DoD Space Operations",
    )
    assert result == "military"


# ---------------------------------------------------------------------------
# Scenario 10: hint that is NOT a valid type is ignored
# ---------------------------------------------------------------------------
def test_invalid_hint_is_ignored() -> None:
    result = classify_launch_type(
        provider="SpaceX",
        hint="experimental",  # not in valid set
    )
    assert result == "civilian"


# ---------------------------------------------------------------------------
# Scenario 11: NRO in provider → military
# ---------------------------------------------------------------------------
def test_nro_in_provider_returns_military() -> None:
    result = classify_launch_type(provider="NRO Launch")
    assert result == "military"


# ---------------------------------------------------------------------------
# Scenario 12: Empty keywords list does not crash
# ---------------------------------------------------------------------------
def test_empty_keywords_returns_civilian() -> None:
    result = classify_launch_type(provider="Virgin Orbit", keywords=[])
    assert result == "civilian"


# ---------------------------------------------------------------------------
# Scenario 13: hint="unknown" is a valid type and is returned
# ---------------------------------------------------------------------------
def test_hint_unknown_is_valid() -> None:
    result = classify_launch_type(provider="SpaceX", hint="unknown")
    assert result == "unknown"


# ---------------------------------------------------------------------------
# Return type annotation sanity check
# ---------------------------------------------------------------------------
def test_return_type_is_valid_launch_type() -> None:
    valid: set[str] = {"civilian", "military", "public_report", "unknown"}
    scenarios: list[dict] = [
        {"provider": "SpaceX"},
        {"provider": "USSF"},
        {"provider": "SpaceX", "keywords": ["MISSILE"]},
        {"provider": "AcmeSat", "source_name": "military tracker"},
    ]
    for kwargs in scenarios:
        result = classify_launch_type(**kwargs)  # type: ignore[arg-type]
        assert result in valid, f"Unexpected type {result!r} for {kwargs}"
