"""Tests for the data normalization pipeline.

Covers normalizer.py and models/launch_event.py with ≥90% branch coverage.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from openorbit.pipeline import NormalizationError, normalize
from openorbit.pipeline.aliases import PAD_LOCATIONS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE: dict[str, object] = {
    "name": "Test Mission",
    "launch_date": "2025-01-15T12:00:00",
    "provider": "SpaceX",
    "status": "scheduled",
}


def _raw(**kwargs: object) -> dict[str, object]:
    return {**BASE, **kwargs}


# ---------------------------------------------------------------------------
# Date parsing — ISO 8601 datetime string
# ---------------------------------------------------------------------------


def test_iso_datetime_string() -> None:
    event = normalize(_raw(launch_date="2025-06-01T18:30:00+00:00"), "test")
    assert event.launch_date == datetime(2025, 6, 1, 18, 30, tzinfo=UTC)


def test_iso_datetime_string_naive_gets_utc() -> None:
    event = normalize(_raw(launch_date="2025-06-01T18:30:00"), "test")
    assert event.launch_date.tzinfo == UTC


# ---------------------------------------------------------------------------
# Date parsing — YYYY-MM-DD
# ---------------------------------------------------------------------------


def test_date_only_string() -> None:
    event = normalize(_raw(launch_date="2025-03-20"), "test")
    assert event.launch_date == datetime(2025, 3, 20, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Date parsing — "Month DD, YYYY"
# ---------------------------------------------------------------------------


def test_month_dd_comma_yyyy() -> None:
    event = normalize(_raw(launch_date="January 15, 2025"), "test")
    assert event.launch_date == datetime(2025, 1, 15, tzinfo=UTC)


def test_month_dd_yyyy_no_comma() -> None:
    event = normalize(_raw(launch_date="March 22 2025"), "test")
    assert event.launch_date == datetime(2025, 3, 22, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Date parsing — Unix timestamps
# ---------------------------------------------------------------------------


def test_unix_timestamp_int() -> None:
    ts = 1_700_000_000
    event = normalize(_raw(launch_date=ts), "test")
    assert event.launch_date == datetime.fromtimestamp(ts, tz=UTC)


def test_unix_timestamp_float() -> None:
    ts = 1_700_000_000.5
    event = normalize(_raw(launch_date=ts), "test")
    assert event.launch_date == datetime.fromtimestamp(ts, tz=UTC)


# ---------------------------------------------------------------------------
# Date parsing — datetime object passthrough
# ---------------------------------------------------------------------------


def test_datetime_passthrough_aware() -> None:
    dt = datetime(2025, 4, 1, 9, 0, tzinfo=UTC)
    event = normalize(_raw(launch_date=dt), "test")
    assert event.launch_date == dt


def test_datetime_passthrough_naive_gets_utc() -> None:
    dt = datetime(2025, 4, 1, 9, 0)
    event = normalize(_raw(launch_date=dt), "test")
    assert event.launch_date.tzinfo == UTC


# ---------------------------------------------------------------------------
# Date parsing — invalid input → NormalizationError
# ---------------------------------------------------------------------------


def test_unparseable_date_string_raises() -> None:
    with pytest.raises(NormalizationError):
        normalize(_raw(launch_date="not-a-date"), "test")


def test_unparseable_date_type_raises() -> None:
    with pytest.raises(NormalizationError):
        normalize(_raw(launch_date={"year": 2025}), "test")


# ---------------------------------------------------------------------------
# Provider alias resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw_name,expected", [
    ("Space Exploration Technologies", "SpaceX"),
    ("space exploration technologies", "SpaceX"),
    ("SPACE EXPLORATION TECHNOLOGIES", "SpaceX"),
    ("Space Exploration Technologies Corp", "SpaceX"),
    ("National Aeronautics and Space Administration", "NASA"),
    ("United Launch Alliance", "ULA"),
    ("Rocket Lab USA", "Rocket Lab"),
    ("China Aerospace Science and Technology Corporation", "CASC"),
    ("Roscosmos State Corporation", "Roscosmos"),
    ("Arianespace SA", "Arianespace"),
    ("Blue Origin LLC", "Blue Origin"),
    ("Northrop Grumman Innovation Systems", "Northrop Grumman"),
    ("Virgin Orbit LLC", "Virgin Orbit"),
])
def test_provider_alias_resolution(raw_name: str, expected: str) -> None:
    event = normalize(_raw(provider=raw_name), "test")
    assert event.provider == expected


def test_unknown_provider_stays_as_is() -> None:
    event = normalize(_raw(provider="Acme Rockets Inc."), "test")
    assert event.provider == "Acme Rockets Inc."


# ---------------------------------------------------------------------------
# Pad lookup enriches lat/lon/location
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pad", list(PAD_LOCATIONS.keys()))
def test_known_pad_enriches_coordinates(pad: str) -> None:
    event = normalize(_raw(pad=pad), "test")
    assert event.lat == PAD_LOCATIONS[pad]["lat"]
    assert event.lon == PAD_LOCATIONS[pad]["lon"]
    assert event.location == PAD_LOCATIONS[pad]["location"]


def test_known_pad_does_not_overwrite_existing_lat_lon() -> None:
    event = normalize(_raw(pad="LC-39A", lat=1.0, lon=2.0, location="Custom"), "test")
    assert event.lat == 1.0
    assert event.lon == 2.0
    assert event.location == "Custom"


def test_unknown_pad_lat_lon_remain_none() -> None:
    event = normalize(_raw(pad="UNKNOWN-PAD-99"), "test")
    assert event.lat is None
    assert event.lon is None


# ---------------------------------------------------------------------------
# confidence_score validation
# ---------------------------------------------------------------------------


def test_confidence_score_default() -> None:
    event = normalize(BASE, "test")
    assert event.confidence_score == pytest.approx(0.4)


def test_confidence_score_valid_range() -> None:
    event = normalize(_raw(confidence_score=0.9), "test")
    assert event.confidence_score == pytest.approx(0.9)


def test_confidence_score_too_high_raises() -> None:
    with pytest.raises(NormalizationError):
        normalize(_raw(confidence_score=1.5), "test")


def test_confidence_score_negative_raises() -> None:
    with pytest.raises(NormalizationError):
        normalize(_raw(confidence_score=-0.1), "test")


# ---------------------------------------------------------------------------
# launch_type aliasing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw_type,expected", [
    ("commercial", "civilian"),
    ("government", "civilian"),
    ("civil", "civilian"),
    ("civilian", "civilian"),
    ("mil", "military"),
    ("military", "military"),
    ("public_report", "public_report"),
    ("unknown", "unknown"),
    ("MILITARY", "military"),
    ("COMMERCIAL", "civilian"),
])
def test_launch_type_aliasing(raw_type: str, expected: str) -> None:
    event = normalize(_raw(launch_type=raw_type), "test")
    assert event.launch_type == expected


def test_unrecognised_launch_type_becomes_unknown() -> None:
    event = normalize(_raw(launch_type="recreational"), "test")
    assert event.launch_type == "unknown"


# ---------------------------------------------------------------------------
# NormalizationError source context
# ---------------------------------------------------------------------------


def test_normalization_error_contains_source() -> None:
    with pytest.raises(NormalizationError, match="mysource"):
        normalize(_raw(launch_date="bad-date"), "mysource")


# ---------------------------------------------------------------------------
# Missing required fields raise NormalizationError
# ---------------------------------------------------------------------------


def test_missing_name_raises() -> None:
    raw = {k: v for k, v in BASE.items() if k != "name"}
    with pytest.raises(NormalizationError):
        normalize(raw, "test")


def test_missing_provider_defaults_to_empty_string() -> None:
    # provider is not required at the dict level; missing key → empty string provider
    raw = {k: v for k, v in BASE.items() if k != "provider"}
    event = normalize(raw, "test")
    assert event.provider == ""


# ---------------------------------------------------------------------------
# Optional fields default correctly
# ---------------------------------------------------------------------------


def test_optional_fields_default_none() -> None:
    event = normalize(BASE, "test")
    assert event.vehicle is None
    assert event.location is None
    assert event.pad is None
    assert event.lat is None
    assert event.lon is None


def test_status_defaults_to_unknown() -> None:
    raw = {k: v for k, v in BASE.items() if k != "status"}
    event = normalize(raw, "test")
    assert event.status == "unknown"
