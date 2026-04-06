"""Tests for the in-memory rate limiter middleware."""

from __future__ import annotations

from datetime import UTC

import pytest
from httpx import ASGITransport, AsyncClient

import openorbit.db as db_module
from openorbit.db import close_db, init_db
from openorbit.main import create_app
from openorbit.middleware.rate_limiter import RateLimiterMiddleware


@pytest.fixture
async def rate_limited_client() -> AsyncClient:  # type: ignore[return]
    """Create an async HTTP client with a very low rate limit (3 req/60 s).

    Yields:
        AsyncClient connected to the rate-limited test app.
    """
    import os

    import openorbit.config

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    openorbit.config._settings = None
    db_module._db_connection = None

    await init_db()
    app = create_app()
    # Replace the 60-req middleware with a tight 3-req limit for testing.
    app.middleware_stack = None  # type: ignore[assignment]
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(RateLimiterMiddleware, calls=3, period=60)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Rebuild the middleware stack with the new middleware.
    app.middleware_stack = app.build_middleware_stack()  # type: ignore[attr-defined]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    await close_db()
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
    openorbit.config._settings = None


@pytest.fixture
async def default_client() -> AsyncClient:  # type: ignore[return]
    """Create an async HTTP client with default rate limiting (60 req/min).

    Yields:
        AsyncClient connected to the test app.
    """
    import os

    import openorbit.config

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    openorbit.config._settings = None
    db_module._db_connection = None

    await init_db()
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    await close_db()
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
    openorbit.config._settings = None


class TestRateLimitHeaders:
    """Normal requests must carry X-RateLimit-* headers."""

    async def test_response_includes_ratelimit_limit_header(
        self, default_client: AsyncClient
    ) -> None:
        """X-RateLimit-Limit header present on normal requests."""
        response = await default_client.get("/v1/launches")
        assert response.status_code == 200
        assert "x-ratelimit-limit" in response.headers

    async def test_response_includes_ratelimit_remaining_header(
        self, default_client: AsyncClient
    ) -> None:
        """X-RateLimit-Remaining header present on normal requests."""
        response = await default_client.get("/v1/launches")
        assert response.status_code == 200
        assert "x-ratelimit-remaining" in response.headers

    async def test_ratelimit_limit_value_is_correct(
        self, default_client: AsyncClient
    ) -> None:
        """X-RateLimit-Limit reflects the configured limit (60)."""
        response = await default_client.get("/v1/launches")
        assert response.headers["x-ratelimit-limit"] == "60"

    async def test_ratelimit_remaining_decrements(
        self, default_client: AsyncClient
    ) -> None:
        """X-RateLimit-Remaining decrements with each request."""
        r1 = await default_client.get("/v1/launches")
        r2 = await default_client.get("/v1/launches")
        rem1 = int(r1.headers["x-ratelimit-remaining"])
        rem2 = int(r2.headers["x-ratelimit-remaining"])
        assert rem2 == rem1 - 1


class TestRateLimitEnforcement:
    """Requests beyond the limit return HTTP 429."""

    async def test_exceeding_limit_returns_429(
        self, rate_limited_client: AsyncClient
    ) -> None:
        """The (limit+1)-th request returns 429."""
        for _ in range(3):
            r = await rate_limited_client.get("/v1/launches")
            assert r.status_code == 200

        response = await rate_limited_client.get("/v1/launches")
        assert response.status_code == 429

    async def test_429_response_includes_retry_after(
        self, rate_limited_client: AsyncClient
    ) -> None:
        """429 responses include a Retry-After header."""
        for _ in range(3):
            await rate_limited_client.get("/v1/launches")

        response = await rate_limited_client.get("/v1/launches")
        assert response.status_code == 429
        assert "retry-after" in response.headers

    async def test_429_response_includes_ratelimit_remaining_zero(
        self, rate_limited_client: AsyncClient
    ) -> None:
        """429 responses carry X-RateLimit-Remaining: 0."""
        for _ in range(3):
            await rate_limited_client.get("/v1/launches")

        response = await rate_limited_client.get("/v1/launches")
        assert response.status_code == 429
        assert response.headers["x-ratelimit-remaining"] == "0"

    async def test_429_response_body_detail(
        self, rate_limited_client: AsyncClient
    ) -> None:
        """429 response body contains a detail field."""
        for _ in range(3):
            await rate_limited_client.get("/v1/launches")

        response = await rate_limited_client.get("/v1/launches")
        assert response.status_code == 429
        body = response.json()
        assert "detail" in body


class TestRateLimiterIpIsolation:
    """Each client IP has an independent rate-limit bucket."""

    async def test_different_ips_are_independent(self) -> None:
        """Two different IPs share no rate-limit bucket."""
        from datetime import datetime

        limiter: RateLimiterMiddleware = RateLimiterMiddleware(
            object(), calls=2, period=60
        )
        now = datetime.now(UTC).timestamp()

        # Exhaust IP1's quota.
        limiter._requests["192.168.0.1"].append(now)
        limiter._requests["192.168.0.1"].append(now)
        assert len(limiter._requests["192.168.0.1"]) >= 2

        # IP2 still has a clean slate.
        assert len(limiter._requests["192.168.0.2"]) == 0
