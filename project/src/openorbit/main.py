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
    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down openOrbit API service")
    await close_db()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI app instance.
    """
    settings = get_settings()

    app = FastAPI(
        title="openOrbit",
        description="OSINT platform for orbital launch intelligence",
        version=settings.VERSION,
        lifespan=lifespan,
    )

    # CORS middleware (allow all origins for dev, restrict in production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    app.include_router(health_router)
    app.include_router(v1_router)

    return app


# App instance for uvicorn
app = create_app()
