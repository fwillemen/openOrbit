# Deployment

[![CI](https://github.com/fwillemen/openOrbit/actions/workflows/ci.yml/badge.svg)](https://github.com/fwillemen/openOrbit/actions/workflows/ci.yml)

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

## CI/CD

The repository uses **GitHub Actions** for continuous integration. Every push to `main` and every pull request runs the full CI suite automatically.

### Jobs

| Job | Command | Purpose |
|-----|---------|---------|
| `lint` | `uv run ruff check src/ tests/` + `uv run ruff format --check src/ tests/` | Style and lint checks |
| `typecheck` | `uv run mypy src/` | Static type checking (strict mode) |
| `test` | `uv run pytest --cov=src --cov-fail-under=80 -q` | Unit tests with ≥ 80% coverage |

### Workflow file

`.github/workflows/ci.yml` — triggers on `push` to `main` and all `pull_request` events. All three jobs run in parallel on `ubuntu-latest` with Python 3.12 and `uv` for dependency management.

### Branch protection setup

To enforce CI before merging, configure branch protection on `main`:

1. Go to **Settings → Branches → Add rule** for `main`
2. Enable **Require status checks to pass before merging**
3. Search for and select `lint`, `typecheck`, and `test`
4. Enable **Require branches to be up to date before merging**
5. Save the rule

### Coverage minimum

The `test` job enforces a **minimum 80% line coverage** via `--cov-fail-under=80`. Builds fail if coverage drops below this threshold. Run coverage locally with:

```bash
cd project && uv run pytest --cov=src --cov-report=term-missing -q
```
