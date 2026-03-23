# ─── Builder stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY project/pyproject.toml project/uv.lock* ./

# Install dependencies only (no source yet)
RUN uv sync --frozen --no-dev 2>/dev/null || uv sync --no-dev

# Copy source
COPY project/src ./src

# ─── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copy virtualenv and source from builder
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/src /app/src

# Create data dir with correct ownership
RUN mkdir -p /app/data && chown appuser:appgroup /app/data

USER appuser

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    DATABASE_URL="sqlite+aiosqlite:///./data/openorbit.db" \
    LOG_LEVEL="INFO" \
    PORT="8000"

EXPOSE 8000

CMD ["uvicorn", "openorbit.main:app", "--host", "0.0.0.0", "--port", "8000"]
