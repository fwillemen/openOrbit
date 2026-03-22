# Developer Guide

This guide covers everything a developer needs to know to contribute to openOrbit:
- Project structure and module organization
- How to add new API endpoints
- How to add new configuration settings
- Testing guidelines and best practices
- Code quality standards

---

## Project Structure

```
project/
├── pyproject.toml              # Project metadata and dependencies (managed by uv)
├── uv.lock                     # Lock file for reproducible builds
├── .env.example                # Environment variable template
├── .python-version             # Python version hint (3.12)
├── src/openorbit/              # Main package
│   ├── __init__.py             # Package initialization
│   ├── main.py                 # FastAPI app creation & middleware
│   ├── config.py               # Settings/configuration (env vars)
│   ├── db.py                   # Database connection management
│   ├── api/                    # API route modules
│   │   ├── __init__.py
│   │   └── health.py           # GET /health endpoint
│   ├── scrapers/               # OSINT data scrapers (future)
│   │   └── __init__.py
│   └── models/                 # Pydantic models & DB schemas (future)
│       └── __init__.py
├── tests/                      # Test suite (mirrors src/ structure)
│   ├── conftest.py             # Pytest fixtures and configuration
│   ├── test_health.py          # Tests for /health endpoint
│   ├── test_config.py          # Configuration tests
│   └── test_db.py              # Database tests
└── htmlcov/                    # Coverage report (generated)
```

### Module Responsibilities

| Module | Responsibility |
|--------|-----------------|
| `main.py` | FastAPI app factory, middleware config, lifespan management |
| `config.py` | Environment-based settings (Pydantic BaseSettings) |
| `db.py` | Async SQLite connection lifecycle, dependency injection |
| `api/health.py` | Health check endpoint implementation |
| `api/__init__.py` | Exports router for inclusion in main.py |
| `conftest.py` | Shared test fixtures (client, settings, database) |

---

## Adding a New API Endpoint

### Step 1: Create a route module

Create `src/openorbit/api/launches.py`:

```python
"""Launch data API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from openorbit.config import Settings, get_settings

router = APIRouter(tags=["launches"], prefix="/launches")


@router.get("", summary="List all launches")
async def list_launches(
    settings: Settings = Depends(get_settings),
) -> dict[str, list]:
    """List all scheduled launches.
    
    Args:
        settings: Application settings (injected).
    
    Returns:
        List of launch records.
    """
    return {"launches": []}


@router.get("/{launch_id}", summary="Get launch details")
async def get_launch(
    launch_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Get details for a specific launch.
    
    Args:
        launch_id: Unique launch identifier.
        settings: Application settings (injected).
    
    Returns:
        Launch details.
    """
    return {"launch_id": launch_id, "provider": "unknown"}
```

### Step 2: Export the router

Edit `src/openorbit/api/__init__.py`:

```python
"""API route modules."""

from __future__ import annotations

from openorbit.api.health import router as health_router
from openorbit.api.launches import router as launches_router

__all__ = ["health_router", "launches_router"]
```

### Step 3: Register the router in the app

Edit `src/openorbit/main.py` in the `create_app()` function:

```python
def create_app() -> FastAPI:
    app = FastAPI(...)
    
    # Register routers
    from openorbit.api import health_router, launches_router
    app.include_router(health_router)
    app.include_router(launches_router)
    
    return app
```

### Step 4: Write tests

Create `tests/test_launches.py`:

```python
"""Tests for launches API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_launches_returns_empty_list(client: AsyncClient) -> None:
    """Test that list_launches returns empty list initially."""
    response = await client.get("/launches")
    assert response.status_code == 200
    assert response.json() == {"launches": []}


@pytest.mark.asyncio
async def test_get_launch_returns_not_found(client: AsyncClient) -> None:
    """Test that getting a non-existent launch returns 404."""
    response = await client.get("/launches/unknown")
    assert response.status_code == 404
```

### Step 5: Run tests

```bash
cd project/
uv run pytest tests/test_launches.py -v
```

### Endpoint Checklist

- ✅ Module in `src/openorbit/api/<name>.py`
- ✅ Router exported from `src/openorbit/api/__init__.py`
- ✅ Router registered in `main.py`
- ✅ Tests in `tests/test_<name>.py`
- ✅ Documentation in `docs/api/<name>.md` (or update `docs/configuration.md`)
- ✅ All tests passing with `pytest`
- ✅ Type checking passes with `mypy src/`
- ✅ Code formatted with `ruff format`

---

## Adding New Configuration Settings

### Step 1: Add to Settings class

Edit `src/openorbit/config.py`:

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # New setting
    MAX_RETRIES: int = 3
```

### Step 2: Document in .env.example

Edit `project/.env.example`:

```bash
# Maximum number of retry attempts for scraper operations
MAX_RETRIES=3
```

### Step 3: Use in your code

```python
from openorbit.config import get_settings

settings = get_settings()
max_retries = settings.MAX_RETRIES
```

### Step 4: Update documentation

Add to `docs/configuration.md`:

```markdown
### `MAX_RETRIES`

**Type:** `int`  
**Default:** `3`  
**Required:** No

Maximum number of retry attempts for scraper operations.
```

---

## Testing Guidelines

### Test Organization

```python
# tests/test_module.py
"""Tests for module."""

import pytest


@pytest.mark.asyncio
async def test_async_function_does_something() -> None:
    """Test description."""
    # Arrange
    result = await some_async_function()
    
    # Assert
    assert result == expected_value


def test_sync_function_handles_edge_case() -> None:
    """Test description."""
    # Arrange
    input_data = {...}
    
    # Act
    result = process(input_data)
    
    # Assert
    assert result is not None
```

### Running Tests

```bash
cd project/

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing

# Run specific file
uv run pytest tests/test_health.py -v

# Run with verbose output
uv run pytest -vv

# Run only failed tests
uv run pytest --lf

# Watch mode (install pytest-watch)
uv run ptw
```

### Coverage Requirements

**Minimum coverage: 80%**

View coverage report:
```bash
uv run pytest --cov=src --cov-report=html
open htmlcov/index.html
```

### Testing Best Practices

1. **Use descriptive test names:**
   ```python
   # ✅ Good
   def test_health_endpoint_returns_200_with_status_ok() -> None: ...
   
   # ❌ Bad
   def test_health() -> None: ...
   ```

2. **Test one thing per test:**
   ```python
   # ✅ Good — test one assertion
   def test_config_loads_version_from_env(monkeypatch) -> None:
       monkeypatch.setenv("VERSION", "1.0.0")
       settings = Settings()
       assert settings.VERSION == "1.0.0"
   
   # ❌ Bad — multiple assertions mixed
   def test_config() -> None:
       settings = Settings()
       assert settings.VERSION == "0.1.0"
       assert settings.LOG_LEVEL == "INFO"
       assert settings.DATABASE_URL is not None
   ```

3. **Use fixtures for common setup:**
   ```python
   # conftest.py
   @pytest.fixture
   async def client():
       from openorbit.main import app
       async with AsyncClient(app=app, base_url="http://test") as c:
           yield c
   
   # Use in tests
   async def test_health(client):
       response = await client.get("/health")
       assert response.status_code == 200
   ```

4. **Mock external dependencies:**
   ```python
   @pytest.mark.asyncio
   async def test_scraper_handles_network_error(monkeypatch):
       async def mock_fetch(*args, **kwargs):
           raise httpx.ConnectError("Connection failed")
       
       monkeypatch.setattr("openorbit.scrapers.fetch", mock_fetch)
       result = await scrape_launches()
       assert result is None
   ```

---

## Code Quality

### Type Checking

Run mypy in strict mode:

```bash
uv run mypy src/
```

All public functions must have type annotations:

```python
# ✅ Correct
def greet(name: str, *, excited: bool = False) -> str:
    return f"{name}!" if excited else name

# ❌ Incorrect — missing return type
def greet(name: str, excited: bool = False):
    return f"{name}!" if excited else name
```

### Formatting and Linting

```bash
# Format code
uv run ruff format src/ tests/

# Check for issues
uv run ruff check src/ tests/

# Fix auto-fixable issues
uv run ruff check src/ tests/ --fix
```

### Docstrings

Use Google-style docstrings for all public code:

```python
def process_launch(launch_id: str, retry_count: int = 0) -> dict[str, str]:
    """Process a launch record.
    
    Fetches launch data from external sources and stores in database.
    
    Args:
        launch_id: Unique launch identifier.
        retry_count: Number of retry attempts on failure.
    
    Returns:
        Processed launch record with fields: id, provider, date.
    
    Raises:
        ValueError: If launch_id is empty.
        TimeoutError: If fetch exceeds 30 seconds.
    """
    if not launch_id:
        raise ValueError("launch_id must not be empty")
    
    return {"id": launch_id, "provider": "unknown", "date": "2025-01-01"}
```

---

## Development Workflow

### 1. Create a feature branch

```bash
git checkout -b feat/new-endpoint
```

### 2. Install development dependencies

```bash
cd project/
uv sync
```

### 3. Make your changes

- Add code to `src/openorbit/`
- Add tests to `tests/`
- Update documentation

### 4. Run all quality checks

```bash
cd project/

# Format
uv run ruff format src/ tests/

# Lint
uv run ruff check src/ tests/ --fix

# Type check
uv run mypy src/

# Test
uv run pytest tests/ --cov=src --cov-report=term-missing
```

### 5. Commit with Conventional Commits

```bash
git add .
git commit -m "feat: add launches endpoint with GET /launches"
```

Commit types:
- `feat:` — new feature
- `fix:` — bug fix
- `test:` — test additions/changes
- `docs:` — documentation
- `refactor:` — code restructuring
- `chore:` — maintenance, dependencies

### 6. Push and create pull request

```bash
git push origin feat/new-endpoint
```

---

## Common Issues and Solutions

### Issue: Import errors when running tests

**Error:** `ModuleNotFoundError: No module named 'openorbit'`

**Solution:** Ensure you're using uv to run pytest:
```bash
uv run pytest  # ✅ Correct
pytest         # ❌ Wrong
```

### Issue: Async test not running

**Error:** `RuntimeWarning: coroutine was never awaited`

**Solution:** Add `@pytest.mark.asyncio` decorator:
```python
@pytest.mark.asyncio  # ✅ Don't forget this
async def test_async_function():
    result = await some_function()
    assert result is not None
```

### Issue: Type checker fails on FastAPI Depends

**Error:** `error: Argument of type "..." has incompatible type "Depends"`

**Solution:** This is a known FastAPI/mypy issue. Mark specific functions with:
```python
# pyproject.toml
[[tool.mypy.overrides]]
module = "openorbit.api.*"
disable_error_code = ["arg-type"]
```

---

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [pytest Documentation](https://docs.pytest.org/)
- [mypy Documentation](https://www.mypy-lang.org/)
- [Architecture Decision Records](../state/decisions.md)

---

## See Also

- [API Reference](./api/health.md)
- [Configuration Guide](./configuration.md)
- [Architecture](./architecture.md)
