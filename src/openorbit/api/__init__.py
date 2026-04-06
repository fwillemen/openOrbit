"""API router package."""

from openorbit.api.health import router as health_router
from openorbit.api.v1 import router as v1_router

__all__ = ["health_router", "v1_router"]
