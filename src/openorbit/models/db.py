"""Pydantic models for database entities.

These models provide type-safe representations of database records
and are used by repository functions for input/output validation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OSINTSource(BaseModel):
    """OSINT data source model.

    Represents a registered scraper/data source for launch event data.
    """

    id: int = Field(description="Source ID")
    name: str = Field(description="Source name")
    url: str = Field(description="Source URL")
    scraper_class: str = Field(
        description="Python class path (e.g., 'openorbit.scrapers.nasa.NASAScraper')"
    )
    enabled: bool = Field(description="Is source enabled")
    last_scraped_at: datetime | None = Field(
        default=None, description="Last scrape timestamp"
    )
    refresh_interval_hours: int = Field(
        default=6, description="Scrape refresh interval in hours"
    )
    source_tier: int = Field(
        default=1,
        description="Source credibility tier: 1=Official, 2=Operational, 3=Analytical",
    )


class LaunchEventCreate(BaseModel):
    """Input model for creating/updating launch events.

    Used by upsert_launch_event() to create or update event records.
    Slug is auto-generated if not provided.
    """

    name: str = Field(description="Event name")
    launch_date: datetime = Field(description="Launch date/time (UTC)")
    launch_date_precision: Literal[
        "second", "minute", "hour", "day", "month", "year", "quarter"
    ] = Field(description="Date precision level")
    provider: str = Field(description="Launch provider (e.g., 'SpaceX', 'NASA')")
    vehicle: str | None = Field(
        default=None, description="Launch vehicle (e.g., 'Falcon 9')"
    )
    location: str | None = Field(
        default=None, description="Launch location (e.g., 'Kennedy Space Center')"
    )
    pad: str | None = Field(default=None, description="Launch pad (e.g., 'LC-39A')")
    launch_type: Literal["civilian", "military", "unknown"] = Field(
        default="unknown", description="Launch type classification"
    )
    status: Literal["scheduled", "delayed", "launched", "failed", "cancelled"] = Field(
        description="Event status"
    )
    slug: str | None = Field(default=None, description="Optional manual slug override")
    image_urls: list[str] = Field(
        default_factory=list,
        description="URLs of images attached to the source post (e.g. social media imagery)",
    )
    claim_lifecycle: Literal[
        "rumor", "indicated", "corroborated", "confirmed", "retracted"
    ] = Field(default="indicated", description="Epistemic lifecycle state of the claim")
    event_kind: Literal["observed", "inferred"] = Field(
        default="observed",
        description="Whether the event is directly observed or inferred",
    )


class LaunchEvent(LaunchEventCreate):
    """Complete launch event model (database representation).

    Extends LaunchEventCreate with database-managed fields.
    """

    id: int = Field(default=0, description="Row ID (SQLite rowid)")
    slug: str = Field(description="Event slug (primary key)")
    confidence_score: int = Field(description="0-100 confidence score")
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    attribution_count: int = Field(
        default=0, description="Number of sources confirming this event"
    )
    inference_flags: list[str] = Field(
        default_factory=list, description="Inference rule flags applied to this event"
    )


class EventAttribution(BaseModel):
    """Attribution linking an event to a source.

    Represents which OSINT sources have confirmed a launch event.
    """

    source_name: str = Field(description="OSINT source name")
    scraped_at: datetime = Field(description="When data was scraped")
    url: str = Field(description="URL scraped")
    source_url: str | None = Field(
        default=None, description="Direct URL of the evidence"
    )
    observed_at: datetime | None = Field(
        default=None, description="Timestamp of when evidence was observed"
    )
    evidence_type: str | None = Field(
        default=None,
        description="Evidence classification (e.g., 'official_schedule', 'notam')",
    )
    source_tier: int | None = Field(
        default=None,
        description="Credibility tier: 1=Official, 2=Operational, 3=Analytical",
    )
    confidence_score: int | None = Field(
        default=None, description="0–100 confidence score for this attribution"
    )
    confidence_rationale: str | None = Field(
        default=None, description="Rationale for the confidence score"
    )
