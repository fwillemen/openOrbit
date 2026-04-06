"""Normalization pipeline package.

Exposes the public API: normalize() and NormalizationError.
"""

from __future__ import annotations

from openorbit.pipeline.exceptions import NormalizationError
from openorbit.pipeline.normalizer import normalize

__all__ = ["NormalizationError", "normalize"]
