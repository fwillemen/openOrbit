"""FastAPI application initialization.

Creates the FastAPI app instance, registers routes, configures middleware,
and manages application lifecycle (startup/shutdown).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from openorbit.api import health_router, v1_router
from openorbit.config import get_settings
from openorbit.db import close_db, init_db
from openorbit.middleware import RateLimiterMiddleware
from openorbit.scheduler import start_scheduler, stop_scheduler


def configure_logging() -> None:
    """Configure structured logging with structlog.

    Sets up JSON output for production, pretty console for dev.
    Log level is controlled via LOG_LEVEL environment variable.
    """
    settings = get_settings()

    # Determine if we're in dev mode (DEBUG/INFO) or production (WARNING+)
    is_dev = settings.LOG_LEVEL.upper() in ("DEBUG", "INFO")

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if is_dev:
        # Pretty console output for development
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        # JSON output for production
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.LOG_LEVEL.upper()),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle.

    Handles startup (DB init, logging config) and shutdown (DB cleanup).

    Args:
        app: FastAPI application instance.

    Yields:
        Control during application lifetime.
    """
    # Startup
    configure_logging()
    logger = structlog.get_logger()
    logger.info("Starting openOrbit API service")

    await init_db()
    await start_scheduler()
    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down openOrbit API service")
    await stop_scheduler()
    await close_db()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI app instance.
    """
    settings = get_settings()

    openapi_tags = [
        {
            "name": "launches",
            "description": "Launch event discovery and detail endpoints",
        },
        {
            "name": "sources",
            "description": "OSINT source registry",
        },
        {
            "name": "auth",
            "description": "API key management (admin only)",
        },
        {
            "name": "health",
            "description": "Service health check",
        },
    ]

    app = FastAPI(
        title="openOrbit",
        description=(
            "OSINT platform for orbital launch intelligence. "
            "Aggregates launch data from multiple open-source intelligence sources, "
            "providing a unified REST API for launch schedules, provider information, "
            "and historical launch data.\n\n"
            "All `GET` endpoints are **public**. "
            "Write operations require an `X-API-Key` header."
        ),
        version=settings.VERSION,
        lifespan=lifespan,
        openapi_tags=openapi_tags,
    )

    # CORS middleware — origins are configurable via CORS_ORIGINS env var.
    # Wildcard "*" disables credentials to comply with the CORS spec.
    # Set CORS_ORIGINS to specific domains in production (e.g. "https://app.example.com").
    cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    allow_credentials = cors_origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting: 60 requests/minute per client IP.
    app.add_middleware(RateLimiterMiddleware, calls=60, period=60)

    # Register API routes
    app.include_router(health_router)
    app.include_router(v1_router)

    return app


# App instance for uvicorn
app = create_app()
