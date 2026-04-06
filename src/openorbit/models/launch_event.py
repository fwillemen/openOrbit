"""Canonical LaunchEvent model for the normalization pipeline.

This is the write-side pipeline model, separate from the DB representation
in models/db.py.  It accepts raw scraper output and normalises it via
Pydantic v2 validators.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from openorbit.pipeline.exceptions import NormalizationError

_LAUNCH_TYPE_MAP: dict[str, str] = {
    "commercial": "civilian",
    "government": "civilian",
    "civil": "civilian",
    "civilian": "civilian",
    "mil": "military",
    "military": "military",
    "public_report": "public_report",
    "unknown": "unknown",
}


class LaunchEvent(BaseModel):
    """Canonical launch event produced by the normalisation pipeline."""

    name: str
    launch_date: datetime
    launch_date_precision: Literal["exact", "day", "week", "month"] = "day"
    provider: str
    vehicle: str | None = None
    location: str | None = None
    pad: str | None = None
    launch_type: Literal["civilian", "military", "public_report", "unknown"] = "unknown"
    status: Literal["scheduled", "success", "failure", "unknown"] = "unknown"
    confidence_score: float = Field(default=0.4, ge=0.0, le=1.0)
    lat: float | None = None
    lon: float | None = None

    @field_validator("launch_date", mode="before")
    @classmethod
    def parse_launch_date(cls, v: Any) -> datetime:
        """Parse launch_date from multiple input formats.

        Args:
            v: Raw value — datetime, int/float (Unix timestamp), or str.

        Returns:
            timezone-aware datetime (UTC).

        Raises:
            NormalizationError: If the value cannot be parsed.
        """
        if isinstance(v, datetime):
            return v if v.tzinfo is not None else v.replace(tzinfo=UTC)

        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=UTC)

        if isinstance(v, str):
            # Try ISO 8601 (handles both datetime and date strings via fromisoformat)
            try:
                dt = datetime.fromisoformat(v)
                return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
            except ValueError:
                pass

            # Try YYYY-MM-DD as a plain date
            try:
                d = date.fromisoformat(v)
                return datetime(d.year, d.month, d.day, tzinfo=UTC)
            except ValueError:
                pass

            # Try "Month DD, YYYY"
            for fmt in ("%B %d, %Y", "%B %d %Y"):
                try:
                    return datetime.strptime(v, fmt).replace(tzinfo=UTC)  # noqa: DTZ007
                except ValueError:
                    continue

            raise NormalizationError(f"Cannot parse launch_date: {v!r}")

        raise NormalizationError(
            f"launch_date must be str, int, float, or datetime; got {type(v).__name__}"
        )

    @field_validator("launch_type", mode="before")
    @classmethod
    def normalize_launch_type(cls, v: Any) -> str:
        """Map raw launch type strings to canonical values.

        Args:
            v: Raw launch type string.

        Returns:
            Canonical launch type string.
        """
        if not isinstance(v, str):
            return "unknown"
        return _LAUNCH_TYPE_MAP.get(v.strip().lower(), "unknown")
