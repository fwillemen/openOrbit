# Fleet — Semi-Autonomous Multi-Agent Development System

This repository is a **meta-framework** for semi-autonomous software development powered by
GitHub Copilot CLI's custom agent capabilities. A fleet of specialized agents collaborates
to build software from a high-level goal — all you need to do is describe what you want.

---

## Agent Roster

This fleet consists of six custom agents defined in `.github/agents/`:

| Agent | File | Role |
|-------|------|------|
| **Product Owner** | `product-owner.agent.md` | Reads `state/goal.md` → creates prioritized product backlog |
| **Scrum Master** | `scrum-master.agent.md` | Loads sprint from backlog → coordinates full delivery cycle |
| **Architect** | `architect.agent.md` | Designs system architecture and project skeleton per sprint item |
| **Programmer** | `programmer.agent.md` | Implements Python features following the architect's design |
| **Code Reviewer** | `code-reviewer.agent.md` | Runs ruff, mypy, secret scan, import hygiene, complexity checks after Programmer |
| **Tester** | `tester.agent.md` | Runs pytest, verifies ≥80% coverage, loops back on failures |
| **Docs Writer** | `docs-writer.agent.md` | Generates MkDocs-style documentation from code and ADRs |
| **Retrospective** | `retrospective.agent.md` | Analyzes sprint metrics, surfaces friction points, annotates agent files |

---

## Delegation Chain

```
User fills state/goal.md
     │
     ▼ "Use the product-owner agent to create a backlog"
Product Owner → writes state/backlog.md + SQLite backlog_items
     │
     ▼ "Use the scrum-master agent to build the top N features"
Scrum Master (uses `agent` tool to coordinate):
  For each sprint item:
    ├── Architect      → designs solution, scaffolds project/
    ├── Programmer     → implements feature
    ├── Code Reviewer  → runs ruff/mypy/secret scan/complexity checks; if fail → back to Programmer
    ├── Tester         → runs pytest --cov; if fail → back to Programmer
    └── Docs Writer    → documents completed item
  → Retrospective → analyzes metrics, annotates agent files
  → Sprint complete → updates state/sprint.md + state/progress.md
```

---

## State Files

All state is stored in two forms:

| File | Updated by | Purpose |
|------|-----------|---------|
| `state/goal.md` | **You** | High-level project goal + constraints |
| `state/backlog.md` | Product Owner | Prioritized feature backlog (MoSCoW) |
| `state/sprint.md` | Scrum Master | Current sprint board (TODO/IN_PROGRESS/DONE) |
| `state/progress.md` | Scrum Master, Docs Writer | Overall progress log |
| `state/decisions.md` | Architect | Architecture Decision Records (ADRs) |
| `state/fleet.db` | All agents | SQLite machine state (gitignored) |

---

## Quick Start

```
1. Fill in state/goal.md with your project goal
2. Run: bash scripts/init-state.sh
3. Launch Copilot CLI: copilot --allow-all --experimental
4. Paste the contents of fleet/prompts/fleet-start.md
5. Paste the contents of fleet/prompts/fleet-sprint.md (set N = desired features)
```

To resume across sessions:
```
copilot --continue
# or paste fleet/prompts/fleet-resume.md
```

To check current status any time:
```
bash scripts/fleet-status.sh
```

---

## Autonomous Operation

For fully autonomous operation (recommended):
- Launch with: `copilot --allow-all --experimental`
- Or run `/allow-all` then press `Shift+Tab` to activate autopilot mode
- Agents will proceed without asking for permission at each step

The fleet will interrupt you only when genuinely blocked (e.g., missing credentials,
an ambiguous requirement that cannot be resolved from the goal file alone).

---

## Built Code

All generated code lives in `project/`. The framework files (this directory structure)
are never modified by the agents. After the goal is achieved, `project/` contains a
standalone Python project you can use independently — or migrate to its own repository.

---

## Using This as a Template for Your Own Project

Fleet is designed to be reused. You have two options:

### Option A — GitHub Template (Recommended)

1. Click **[Use this template](https://github.com/fwillemen/fleet/generate)** on GitHub
2. Clone your new repo
3. Fill in `state/goal.md`
4. Run `bash scripts/init-state.sh`
5. Launch Copilot CLI and invoke the agents

### Option B — Cookiecutter

```bash
pip install cookiecutter
cookiecutter gh:fwillemen/fleet --checkout cookiecutter
```

Follow the prompts to name your project, then fill in `state/goal.md`.

### Customising the Framework

- **Change coding standards:** edit `.github/instructions/python-standards.instructions.md`
- **Add a new agent:** create `.github/agents/<name>.agent.md` and document it here
- **Change the delivery cycle:** edit `.github/agents/scrum-master.agent.md`
- **Change session context:** edit `.github/copilot-instructions.md`

---

## Technology Stack (Defaults)

| Concern | Tool |
|---------|------|
| Package management | `uv` |
| Testing | `pytest` + `pytest-cov` |
| Linting / formatting | `ruff` |
| Type checking | `mypy` |
| Documentation | MkDocs-style Markdown |
| Commits | Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`) |
| Coverage minimum | 80% per sprint item |
