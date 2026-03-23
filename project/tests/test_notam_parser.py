"""Tests for the NOTAM text parser (pure unit tests — no I/O, no HTTP)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from openorbit.pipeline.notam_parser import (
    NotamMatch,
    classify_notam,
    extract_launch_candidates,
    parse_notam,
    parse_q_line,
    parse_validity,
)


class TestParseNotam:
    """Tests for parse_notam() — high-level NOTAM classification."""

    def test_rocket_launch_keyword_is_civilian(self) -> None:
        """NOTAM with ROCKET LAUNCH → is_launch_related=True, launch_type=civilian."""
        result = parse_notam("ROCKET LAUNCH WILL TAKE PLACE 5NM RADIUS")
        assert result.is_launch_related is True
        assert result.launch_type == "civilian"

    def test_missile_keyword_is_military(self) -> None:
        """NOTAM with MISSILE → is_launch_related=True, launch_type=military."""
        result = parse_notam("MISSILE FIRING EXERCISE IN RESTRICTED AIRSPACE")
        assert result.is_launch_related is True
        assert result.launch_type == "military"

    def test_range_closure_is_launch_related(self) -> None:
        """NOTAM with RANGE CLOSURE → is_launch_related=True."""
        result = parse_notam("RANGE CLOSURE IN EFFECT DUE TO LAUNCH ACTIVITIES")
        assert result.is_launch_related is True
        assert result.launch_type == "unknown"

    def test_no_keywords_not_launch_related(self) -> None:
        """NOTAM with no launch keywords → is_launch_related=False, unknown."""
        result = parse_notam("TAXIWAY ALPHA CLOSED FOR MAINTENANCE OPERATIONS")
        assert result.is_launch_related is False
        assert result.launch_type == "unknown"
        assert result.matched_keywords == []

    def test_missile_priority_over_rocket(self) -> None:
        """NOTAM with both ROCKET and MISSILE → military (MISSILE takes priority)."""
        result = parse_notam("ROCKET LAUNCH AREA: MISSILE TEST EXERCISE")
        assert result.is_launch_related is True
        assert result.launch_type == "military"
        assert "MISSILE" in result.matched_keywords
        assert "ROCKET" in result.matched_keywords

    def test_case_insensitive_missile(self) -> None:
        """Lowercase 'missile' → is_launch_related=True, military."""
        result = parse_notam("missile test in restricted airspace r-2901")
        assert result.is_launch_related is True
        assert result.launch_type == "military"

    def test_multi_keyword_matched_keywords(self) -> None:
        """SPACE LAUNCH VEHICLE ROCKET → matched_keywords includes both."""
        result = parse_notam("SPACE LAUNCH VEHICLE ROCKET DEPARTURE CORRIDOR")
        assert result.is_launch_related is True
        # Both SPACE LAUNCH and ROCKET should be found by findall
        assert len(result.matched_keywords) >= 2
        assert "SPACE LAUNCH" in result.matched_keywords
        assert "ROCKET" in result.matched_keywords

    def test_space_launch_is_civilian(self) -> None:
        """NOTAM with SPACE LAUNCH → civilian."""
        result = parse_notam("SPACE LAUNCH VEHICLE DEPARTURE FROM PAD 39A")
        assert result.is_launch_related is True
        assert result.launch_type == "civilian"

    def test_raw_text_preserved(self) -> None:
        """raw_text field should contain original input unchanged."""
        text = "ROCKET LAUNCH AREA ACTIVE"
        result = parse_notam(text)
        assert result.raw_text == text

    def test_returns_notam_match_type(self) -> None:
        """parse_notam always returns a NotamMatch instance."""
        result = parse_notam("some arbitrary notam text")
        assert isinstance(result, NotamMatch)

    def test_space_vehicle_is_civilian(self) -> None:
        """NOTAM with SPACE VEHICLE → civilian."""
        result = parse_notam("SPACE VEHICLE REENTRY EXPECTED IN SECTOR 7")
        assert result.is_launch_related is True
        assert result.launch_type == "civilian"


class TestClassifyNotam:
    """Tests for classify_notam() — priority-based keyword classification."""

    @pytest.mark.parametrize(
        ("text", "expected_keyword", "expected_type"),
        [
            ("ROCKET LAUNCH WILL TAKE PLACE 5NM RADIUS", "ROCKET", "civilian"),
            ("SPACE LAUNCH VEHICLE DEPARTURE", "SPACE LAUNCH", "civilian"),
            ("MISSILE FIRING EXERCISE", "MISSILE", "military"),
            ("RANGE CLOSURE IN EFFECT", "RANGE CLOSURE", "unknown"),
            ("AIRSHOW PERFORMANCE NO LAUNCH", None, None),
        ],
    )
    def test_parametrized_classification(
        self,
        text: str,
        expected_keyword: str | None,
        expected_type: str | None,
    ) -> None:
        """Parametrized test for classify_notam against known NOTAM texts."""
        keyword, launch_type = classify_notam(text)
        assert keyword == expected_keyword
        assert launch_type == expected_type

    def test_space_launch_before_rocket(self) -> None:
        """SPACE LAUNCH takes priority over bare ROCKET when both present."""
        keyword, ltype = classify_notam("SPACE LAUNCH ROCKET DEPLOY")
        # MISSILE is checked first, then SPACE LAUNCH — so SPACE LAUNCH wins over ROCKET
        assert keyword == "SPACE LAUNCH"
        assert ltype == "civilian"

    def test_missile_beats_space_launch(self) -> None:
        """MISSILE takes priority over SPACE LAUNCH."""
        keyword, ltype = classify_notam("SPACE LAUNCH VEHICLE MISSILE PAYLOAD")
        assert keyword == "MISSILE"
        assert ltype == "military"

    def test_empty_string(self) -> None:
        """Empty text returns (None, None)."""
        keyword, ltype = classify_notam("")
        assert keyword is None
        assert ltype is None

    def test_case_insensitive(self) -> None:
        """Classification is case-insensitive."""
        keyword, ltype = classify_notam("missile test in area")
        assert keyword == "MISSILE"
        assert ltype == "military"


class TestParseQLine:
    """Tests for parse_q_line() — Q-line coordinate extraction."""

    def test_standard_coordinates(self) -> None:
        """'3030N08145W001' parses to lat=30.5, lon=-81.75."""
        result = parse_q_line("Q) KZJX/QRTCA/IV/BO/AE/000/999/3030N08145W001")
        assert result["lat"] == pytest.approx(30.5)
        assert result["lon"] == pytest.approx(-81.75)

    def test_northern_eastern_hemisphere(self) -> None:
        """Coordinates with N and E → positive lat and lon."""
        result = parse_q_line("Q) XXXX/QRTCA/.../5130N00000E001")
        assert result["lat"] == pytest.approx(51.5)
        assert result["lon"] == pytest.approx(0.0)

    def test_southern_western_hemisphere(self) -> None:
        """Coordinates with S and W → negative lat and lon."""
        result = parse_q_line("Q) XXXX/QRTCA/.../2845S04512W010")
        assert result["lat"] == pytest.approx(-28.75)
        assert result["lon"] == pytest.approx(-45.2)

    def test_malformed_returns_none(self) -> None:
        """Malformed or missing coordinate segment → lat=None, lon=None."""
        result = parse_q_line("Q) KZJX/QRTCA/IV/BO/AE/000/999/MALFORMED")
        assert result == {"lat": None, "lon": None}

    def test_empty_string_returns_none(self) -> None:
        """Empty Q-line → lat=None, lon=None."""
        result = parse_q_line("")
        assert result == {"lat": None, "lon": None}


class TestParseValidity:
    """Tests for parse_validity() — B/C-line timestamp parsing."""

    def test_valid_start_and_end(self) -> None:
        """Valid B and C lines parse to UTC datetimes."""
        start, end = parse_validity("2301011500", "2301012300")
        assert start == datetime(2023, 1, 1, 15, 0, tzinfo=UTC)
        assert end == datetime(2023, 1, 1, 23, 0, tzinfo=UTC)

    def test_perm_end_returns_none(self) -> None:
        """C-line 'PERM' → end datetime is None."""
        start, end = parse_validity("2301011500", "PERM")
        assert start == datetime(2023, 1, 1, 15, 0, tzinfo=UTC)
        assert end is None

    def test_perm_case_insensitive(self) -> None:
        """'perm' (lowercase) → end datetime is None."""
        start, end = parse_validity("2301011500", "perm")
        assert start is not None
        assert end is None

    def test_invalid_b_line_returns_none_tuple(self) -> None:
        """Invalid B-line → (None, None)."""
        start, end = parse_validity("INVALID", "2301012300")
        assert start is None
        assert end is None

    def test_invalid_c_line_returns_start_only(self) -> None:
        """Invalid C-line (non-PERM) → returns start, end=None."""
        start, end = parse_validity("2306151200", "BADDATA")
        assert start == datetime(2023, 6, 15, 12, 0, tzinfo=UTC)
        assert end is None

    def test_datetimes_are_utc(self) -> None:
        """Parsed datetimes are always timezone-aware (UTC)."""
        start, end = parse_validity("2312251000", "2312252000")
        assert start is not None and start.tzinfo is UTC
        assert end is not None and end.tzinfo is UTC


class TestExtractLaunchCandidates:
    """Tests for extract_launch_candidates() — full NOTAM list processing."""

    def _make_notam(
        self,
        notam_id: str,
        e_text: str,
        q_line: str = "",
        start: str = "2306151200",
        end: str = "2306151800",
        location: str = "KZJX",
    ) -> dict:
        return {
            "notamNumber": notam_id,
            "traditionalMessageFrom4thLine": e_text,
            "qLine": q_line,
            "startValidity": start,
            "endValidity": end,
            "location": location,
        }

    def test_launch_notams_extracted(self) -> None:
        """2 launch NOTAMs + 1 non-launch → 2 events returned."""
        notams = [
            self._make_notam("1/2345", "ROCKET LAUNCH CORRIDOR ACTIVE"),
            self._make_notam("2/6789", "SPACE LAUNCH VEHICLE DEPARTURE"),
            self._make_notam("3/0001", "TAXIWAY BRAVO CLOSED"),
        ]
        events = extract_launch_candidates(notams)
        assert len(events) == 2

    def test_empty_list_returns_empty(self) -> None:
        """Empty input list → empty output list."""
        events = extract_launch_candidates([])
        assert events == []

    def test_non_launch_notam_excluded(self) -> None:
        """NOTAM without launch keywords is excluded."""
        notams = [self._make_notam("4/9999", "VOR OUT OF SERVICE FOR MAINTENANCE")]
        events = extract_launch_candidates(notams)
        assert events == []

    def test_slug_format(self) -> None:
        """Slug should be 'notam-{id}' with slashes replaced by hyphens."""
        notams = [self._make_notam("1/2345", "ROCKET LAUNCH")]
        events = extract_launch_candidates(notams)
        assert events[0].slug == "notam-1-2345"

    def test_provider_is_faa(self) -> None:
        """Provider field should always be 'FAA'."""
        notams = [self._make_notam("5/1111", "MISSILE EXERCISE")]
        events = extract_launch_candidates(notams)
        assert events[0].provider == "FAA"

    def test_status_is_scheduled(self) -> None:
        """Status should default to 'scheduled'."""
        notams = [self._make_notam("6/2222", "SPACE LAUNCH WINDOW")]
        events = extract_launch_candidates(notams)
        assert events[0].status == "scheduled"

    def test_day_precision_when_start_parsed(self) -> None:
        """When startValidity parses successfully, precision is 'day'."""
        notams = [self._make_notam("7/3333", "ROCKET LAUNCH")]
        events = extract_launch_candidates(notams)
        assert events[0].launch_date_precision == "day"

    def test_week_precision_when_start_unparseable(self) -> None:
        """When startValidity is unparseable, precision falls back to 'month'."""
        notams = [self._make_notam("8/4444", "ROCKET LAUNCH", start="INVALID")]
        events = extract_launch_candidates(notams)
        assert events[0].launch_date_precision == "month"

    def test_coordinates_in_location_when_q_line_present(self) -> None:
        """When Q-line has coordinates, location is set from them."""
        notams = [
            self._make_notam(
                "9/5555",
                "ROCKET LAUNCH",
                q_line="Q) KZJX/QRTCA/.../3030N08145W001",
            )
        ]
        events = extract_launch_candidates(notams)
        assert events[0].location is not None
        assert "30.50N" in events[0].location

    def test_missile_launch_type_is_military(self) -> None:
        """MISSILE in E-line → launch_type='military'."""
        notams = [self._make_notam("10/6666", "MISSILE FIRING EXERCISE")]
        events = extract_launch_candidates(notams)
        assert events[0].launch_type == "military"

    def test_name_includes_notam_id_and_keyword(self) -> None:
        """Event name should include NOTAM number and matched keyword."""
        notams = [self._make_notam("11/7777", "SPACE LAUNCH VEHICLE")]
        events = extract_launch_candidates(notams)
        assert "11/7777" in events[0].name
        assert "SPACE LAUNCH" in events[0].name
