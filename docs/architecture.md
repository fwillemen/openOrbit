# Architecture

## Repository Layout

```
fleet/                          ← Framework root (never modified by agents)
├── .github/
│   ├── agents/                 ← Agent definitions (Markdown files)
│   │   ├── product-owner.agent.md
│   │   ├── scrum-master.agent.md
│   │   ├── architect.agent.md
│   │   ├── programmer.agent.md
│   │   ├── tester.agent.md
│   │   └── docs-writer.agent.md
│   ├── copilot-instructions.md ← Session-level context for Copilot CLI
│   └── instructions/           ← Reusable instruction files (e.g. python-standards)
├── fleet/
│   ├── README.md               ← User guide
│   └── prompts/                ← Ready-made prompt templates
├── scripts/
│   ├── init-state.sh           ← Initializes state/fleet.db schema
│   └── fleet-status.sh         ← Prints current sprint/backlog summary
├── state/                      ← Runtime state (human-readable + SQLite)
│   ├── goal.md                 ← YOU fill this in
│   ├── backlog.md              ← Written by Product Owner
│   ├── sprint.md               ← Written by Scrum Master
│   ├── progress.md             ← Written by Scrum Master + Docs Writer
│   ├── decisions.md            ← Written by Architect (ADRs)
│   ├── schema.sql              ← SQLite schema reference
│   └── fleet.db                ← SQLite machine state (gitignored)
├── docs/                       ← Framework documentation (this directory)
├── project/                    ← ALL generated code lives here (agent-managed)
│   ├── pyproject.toml
│   ├── src/<package>/
│   └── tests/
└── AGENTS.md                   ← Agent roster and delegation chain
```

---

## Agent Communication

Agents are stateless — each invocation is independent. They communicate by reading
and writing **shared files** (`state/*.md`, `project/`, `docs/`) and the **SQLite
database** (`state/fleet.db`).

```
state/goal.md ──────────────────────────────────────────────► Product Owner
state/backlog.md (written by PO) ──────────────────────────► Scrum Master
state/sprint.md (written by SM) ───────────────────────────► Architect
project/ (written by Architect) ───────────────────────────► Programmer
project/ (modified by Programmer) ─────────────────────────► Tester
project/ + docs/ (verified by Tester) ─────────────────────► Docs Writer
state/progress.md ◄──────────────────────────────────────── All agents
```

---

## State Database Schema

`state/fleet.db` is a SQLite database. The schema is in `state/schema.sql`.

Key tables:

| Table | Purpose |
|-------|---------|
| `backlog_items` | All backlog items with priority and status |
| `sprint_items` | Items in the current sprint |
| `test_results` | Latest test run results per sprint item |

---

## Technology Stack (Defaults)

Generated projects use these defaults unless the goal specifies otherwise:

| Concern | Tool |
|---------|------|
| Package management | `uv` |
| Testing | `pytest` + `pytest-cov` (≥80% coverage) |
| Linting / formatting | `ruff` |
| Type checking | `mypy` (strict mode) |
| Docstrings | Google style |
| Commits | Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`) |
| Python version | 3.12+ |

---

## Extending the Framework

### Adding a new agent

1. Create `.github/agents/<name>.agent.md` following the existing pattern
2. Document it in `AGENTS.md`
3. Reference it from `scrum-master.agent.md` if it should be part of the delivery cycle

### Changing the tech stack

Edit `.github/instructions/python-standards.instructions.md` — this file is
automatically included in every agent's context and defines conventions for the
generated code.
