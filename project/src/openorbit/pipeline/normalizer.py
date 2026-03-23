"""Data normalization pipeline — converts raw scraper dicts to LaunchEvent models."""

from __future__ import annotations

from pydantic import ValidationError

from openorbit.models.launch_event import LaunchEvent
from openorbit.pipeline.aliases import PAD_LOCATIONS, PROVIDER_ALIASES
from openorbit.pipeline.exceptions import NormalizationError


def normalize(raw: dict[str, object], source: str) -> LaunchEvent:
    """Normalize a raw scraper dict into a canonical LaunchEvent.

    Steps:
    1. Resolve provider name through PROVIDER_ALIASES (case-insensitive).
    2. Look up pad in PAD_LOCATIONS; inject lat/lon/location when not already set.
    3. Construct LaunchEvent — any ValidationError is wrapped as NormalizationError.

    Args:
        raw: Raw scraper output dictionary.
        source: Name of the OSINT source (used in error messages).

    Returns:
        Validated canonical LaunchEvent instance.

    Raises:
        NormalizationError: If the raw data cannot be coerced into a valid LaunchEvent.
    """
    data: dict[str, object] = dict(raw)

    # --- 1. Resolve provider alias ---
    provider_raw = str(data.get("provider", "")).strip()
    data["provider"] = PROVIDER_ALIASES.get(provider_raw.lower(), provider_raw)

    # --- 2. Enrich from PAD_LOCATIONS ---
    # Normalize pad: strip whitespace; convert empty/whitespace-only to None
    raw_pad = data.get("pad")
    pad = str(raw_pad).strip() if raw_pad is not None else None
    data["pad"] = pad if pad else None
    if pad and pad in PAD_LOCATIONS:
        pad_info = PAD_LOCATIONS[pad]
        if data.get("lat") is None:
            data["lat"] = pad_info["lat"]
        if data.get("lon") is None:
            data["lon"] = pad_info["lon"]
        if not data.get("location"):
            data["location"] = pad_info["location"]

    # --- 3. Construct and validate ---
    try:
        return LaunchEvent(**data)  # type: ignore[arg-type]
    except (ValidationError, NormalizationError) as exc:
        raise NormalizationError(
            f"[{source}] Failed to normalize launch event: {exc}"
        ) from exc
