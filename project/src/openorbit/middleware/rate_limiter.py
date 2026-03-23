"""In-memory sliding-window rate limiter middleware.

Limits each client IP to a configurable number of requests per time window.
Exceeding the limit returns HTTP 429 with Retry-After and X-RateLimit-* headers.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter keyed by client IP.

    Args:
        app: ASGI application.
        calls: Maximum allowed requests per period (default: 60).
        period: Time window in seconds (default: 60).
    """

    def __init__(self, app: object, calls: int = 60, period: int = 60) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.calls = calls
        self.period = period
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: object) -> Response:
        """Process each request, enforcing the rate limit.

        Args:
            request: Incoming HTTP request.
            call_next: Next ASGI handler callable.

        Returns:
            HTTP response, either the normal response or a 429 if rate limited.
        """
        client_ip = request.client.host if request.client else "unknown"
        now = datetime.now(timezone.utc).timestamp()
        window = self._requests[client_ip]

        # Evict timestamps outside the current sliding window.
        while window and window[0] < now - self.period:
            window.popleft()

        remaining = self.calls - len(window)

        if len(window) >= self.calls:
            return Response(
                content='{"detail": "Rate limit exceeded"}',
                status_code=429,
                headers={
                    "Content-Type": "application/json",
                    "Retry-After": str(self.period),
                    "X-RateLimit-Limit": str(self.calls),
                    "X-RateLimit-Remaining": "0",
                },
            )

        window.append(now)
        # call_next is typed as Callable in BaseHTTPMiddleware internals.
        response: Response = await call_next(request)  # type: ignore[operator]
        response.headers["X-RateLimit-Limit"] = str(self.calls)
        response.headers["X-RateLimit-Remaining"] = str(remaining - 1)
        return response
