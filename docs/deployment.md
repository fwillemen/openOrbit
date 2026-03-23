# Deployment

This document describes how to build and run openOrbit using Docker.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 20.10+
- [Docker Compose](https://docs.docker.com/compose/install/) v2+

## Build the Image

From the repository root:

```bash
docker build -t openorbit:latest .
```

The build uses a **multi-stage** approach:

| Stage | Base | Purpose |
|-------|------|---------|
| `builder` | `python:3.12-slim` | Installs `uv` and resolves dependencies into `.venv` |
| `runtime` | `python:3.12-slim` | Copies the virtualenv and source; runs as non-root `appuser` |

Target image size: < 300 MB.

## Run the Container

```bash
docker run -d \
  --name openorbit \
  -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -e DATABASE_URL="sqlite+aiosqlite:///./data/openorbit.db" \
  openorbit:latest
```

The API is available at <http://localhost:8000>.

## Docker Compose

A `docker-compose.yml` is provided at the repository root for convenience:

```bash
# Start the API (detached)
docker compose up -d

# View logs
docker compose logs -f api

# Stop and remove containers
docker compose down
```

### Environment Variables

The compose file reads from `.env.example`. Copy it to `.env` and customise:

```bash
cp .env.example .env
# edit .env as needed
docker compose up -d
```

Key environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/openorbit.db` | SQLite database path |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `PORT` | `8000` | Port the uvicorn server listens on |

## Data Persistence

The `data/` directory is mounted as a volume at `/app/data` inside the container.
The SQLite database file is stored there and persists across container restarts.

## Health Check

Docker Compose configures an automatic health check:

```
GET http://localhost:8000/health
```

Interval: 30 s — Timeout: 10 s — Retries: 3

Check the container health status with:

```bash
docker inspect --format='{{.State.Health.Status}}' openorbit
```

## Security Notes

- The container process runs as `appuser` (non-root) inside the `appgroup` group.
- No secrets are baked into the image; supply them via environment variables or `.env`.
- The `.dockerignore` excludes `state/`, `.git/`, test fixtures, and other non-runtime files.
