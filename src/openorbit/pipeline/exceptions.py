"""Exceptions for the normalization pipeline."""

from __future__ import annotations


class NormalizationError(ValueError):
    """Raised when raw scraper data cannot be normalized into a LaunchEvent.

    Wraps Pydantic ValidationError or custom validation failures and
    attaches source context so callers can log and route the error.
    """
