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

---

## Visualization

Fleet includes a zero-dependency pixelated agent dashboard built with pure Python 3 stdlib.

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/fleet-viz.py` | Agent dashboard — snapshot, live watch, or event replay |
| `scripts/fleet-splash.py` | Animated intro banner shown after `init-state.sh` |

### Modes

```bash
# Single snapshot (called automatically by fleet-status.sh)
python3 scripts/fleet-viz.py state/fleet.db

# Live auto-refresh every 2 s (ANSI cursor repositioning, no flicker)
python3 scripts/fleet-viz.py --watch state/fleet.db

# Replay past sprint event-by-event from agent log
python3 scripts/fleet-viz.py --replay state/agent-log.ndjson

# Animated intro banner
python3 scripts/fleet-splash.py
```

### Rendering Technique

The visualization uses **Unicode half-block characters** (`▀` U+2580) with ANSI
truecolor escape sequences (`\033[38;2;R;G;Bm` foreground / `\033[48;2;R;G;Bm`
background). Each terminal character cell carries **two pixels** — the top pixel
uses the foreground colour and the bottom pixel uses the background colour —
yielding 2× vertical resolution with no external libraries.

Sprites are 5 characters wide × 4 lines tall (= 5×8 pixels). Each agent has two
animation frames for an active "working" state.

**Palette**: PICO-8-inspired 16-colour set stored as RGB tuples. Transparent
pixels are rendered against terminal background `(15, 15, 25)`.

**Graceful degradation**: both scripts silently exit when:
- stdout is not a TTY (piped output, CI environments)
- Terminal width < 60 columns

### Status Colour Coding

| Status | Colour |
|--------|--------|
| idle | Dim grey |
| active / running | Bright yellow |
| done | Green |
| failed | Red |
| blocked | Orange |
