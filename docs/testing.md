# Testing Guide

## Running the Test Suite

```bash
cd project && uv run pytest --cov=src/openorbit --cov-report=term-missing
```

## Current Coverage Status

| Metric | Value |
|--------|-------|
| Overall coverage | **93%** |
| Minimum per module | ≥80% |

All modules meet or exceed the 80% coverage threshold required by the project standards.

## Test Categories

### Unit Tests — Scrapers

Located in `tests/test_scrapers_*.py`. HTTP calls are intercepted using
[respx](https://github.com/lundberg/respx), so no real network traffic is made. Each
scraper is exercised against a set of mocked responses to verify parsing, error handling,
and retry behaviour.

### API Integration Tests

Located in `tests/test_api_*.py`. These spin up the FastAPI application via
`httpx.AsyncClient` with an **in-memory SQLite** database, verifying end-to-end request
handling, response schemas, and status codes without touching production data.

### Pipeline / Normalization Tests

Located in `tests/test_pipeline*.py` and `tests/test_normalization*.py`. These validate
the data-transformation layer: field mapping, type coercion, deduplication logic, and
error propagation through the ingestion pipeline.

### Coverage Enforcement

Coverage is enforced automatically via `pytest-cov`. The project is configured in
`pyproject.toml` with `--cov-fail-under=80` so CI fails if overall coverage drops below
the threshold.

## Notes

### `scrapers/base.py` — Protocol Stubs

The `BaseScraperProtocol` class in `scrapers/base.py` contains abstract method stubs
defined with `...` bodies. These are marked `# pragma: no cover` because they exist
solely as a structural contract and are never executed directly — only their concrete
implementations in subclasses are exercised by the test suite.
