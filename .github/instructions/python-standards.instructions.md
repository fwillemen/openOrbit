---
description: Python coding standards for this project
---

# Python Coding Standards

These standards apply to all code in `project/src/` and `project/tests/`.

## Package Management — `uv`

Always use `uv` (never `pip` directly):
```bash
uv add <package>           # add a runtime dependency
uv add --dev <package>     # add a dev dependency
uv sync                    # install all dependencies
uv sync --extra dev        # install including dev deps
uv run pytest              # run a tool via uv
```

## Type Annotations

All public code must be fully annotated:
```python
# ✅ Correct
def greet(name: str, *, loud: bool = False) -> str:
    return name.upper() if loud else name

# ❌ Wrong — missing annotations
def greet(name, loud=False):
    return name.upper() if loud else name
```

Avoid `Any` — use `Union`, `TypeVar`, or `Protocol` instead.
Use `from __future__ import annotations` for forward references.

## Docstrings — Google Style

```python
def process(items: list[str], limit: int = 100) -> list[str]:
    """Process a list of items.

    Args:
        items: The items to process.
        limit: Maximum number of items to return.

    Returns:
        Processed items, truncated to limit.

    Raises:
        ValueError: If items is empty.
    """
```

All public functions, classes, and modules must have docstrings.
Private functions (leading `_`) only need docstrings if complex.

## Linting — `ruff`

Run before every commit:
```bash
ruff check src/ tests/ --fix   # auto-fix what's fixable
ruff format src/ tests/         # format code
```

Active rule sets: `E`, `F`, `I` (isort), `N` (naming), `UP` (pyupgrade), `B` (bugbear), `SIM` (simplify).

## Type Checking — `mypy`

Run in strict mode:
```bash
mypy src/
```

Strict mode enables: `--disallow-untyped-defs`, `--disallow-any-generics`,
`--warn-return-any`, `--strict-equality`, and more.

## Testing — `pytest`

Test file naming: `tests/test_<module>.py`
Test function naming: `test_<function>_<scenario>()`

```python
# ✅ Good test names
def test_parse_config_returns_valid_config() -> None: ...
def test_parse_config_raises_on_missing_key() -> None: ...
def test_parse_config_handles_empty_file() -> None: ...

# ❌ Bad test names
def test_1() -> None: ...
def test_works() -> None: ...
```

Use `pytest.raises()` context manager for expected exceptions:
```python
with pytest.raises(ValueError, match="must not be empty"):
    process([])
```

Minimum 80% line coverage. Run coverage locally:
```bash
pytest --cov=src --cov-report=term-missing
```

## Project Layout

```
project/
├── pyproject.toml        # single config file (no setup.py, no requirements.txt)
├── src/
│   └── <package>/
│       ├── __init__.py   # expose public API
│       └── <module>.py
└── tests/
    ├── __init__.py
    ├── conftest.py       # shared fixtures
    └── test_<module>.py
```

Use `src/` layout — never put package directly at project root.

## Commit Messages (Conventional Commits)

```
feat(<scope>): add user authentication
fix(<scope>): handle empty input in parser
test(<scope>): add edge cases for config loader
docs(<scope>): add API reference for auth module
chore: update dependencies
refactor(<scope>): extract validation logic
```

Always end commit messages with:
```
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```
