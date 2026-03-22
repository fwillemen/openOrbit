# Copilot Instructions — Fleet Framework

## Project Context
This is a semi-autonomous development framework. A fleet of specialized custom agents
(defined in `.github/agents/`) collaborates to build software from a high-level goal
stored in `state/goal.md`. Read `AGENTS.md` for the full fleet overview.

## Session Orientation
At the start of every session:
1. Check `state/goal.md` — understand the overarching project goal
2. Check `state/sprint.md` — understand what is currently in progress
3. Check `state/progress.md` — understand what has been completed

## Python Stack
All code in `project/` follows these defaults unless the goal specifies otherwise:
- **Package management:** `uv` (never `pip` directly)
- **Testing:** `pytest` with `pytest-cov` (minimum 80% coverage)
- **Linting / formatting:** `ruff` (check and format before committing)
- **Type checking:** `mypy` in strict mode
- **Docstrings:** Google style
- **Python version:** 3.12+ unless constrained

## Commit Style
All commits use Conventional Commits format:
- `feat: <description>` — new feature
- `fix: <description>` — bug fix
- `test: <description>` — test additions/changes
- `docs: <description>` — documentation
- `chore: <description>` — maintenance, deps, config
- `refactor: <description>` — code restructure without behavior change

Always include the Co-authored-by trailer:
```
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

## Project Isolation
- All generated code lives in `project/` — never modify framework files outside `project/`, `state/`, or `docs/`
- The `state/fleet.db` SQLite database tracks all agent state (read/write it freely)
- `state/*.md` files are human-readable state (always keep them up to date)

## Autonomous Operation
- Proceed without asking for human approval unless genuinely blocked
- If blocked by an ambiguity that cannot be resolved from `state/goal.md`, write
  the blocker clearly to `state/progress.md` and surface it to the user
- Never break existing passing tests
- 80% test coverage is a hard requirement before any sprint item is considered done
