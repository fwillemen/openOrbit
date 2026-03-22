# Fleet Framework Documentation

**Fleet** is a semi-autonomous multi-agent development framework powered by GitHub Copilot CLI.
You describe a goal, and a coordinated fleet of specialized agents plans, architects, codes,
tests, and documents your Python project — sprint by sprint.

---

## How It Works

```
You fill state/goal.md
       │
       ▼  "Use the product-owner agent to create a backlog"
Product Owner → state/backlog.md (MoSCoW-prioritized features)
       │
       ▼  "Use the scrum-master agent to build the top N features"
Scrum Master (coordinates):
  For each sprint item:
  ├── Architect   → designs the solution, scaffolds project/
  ├── Programmer  → implements the feature (loops until tests pass)
  ├── Tester      → runs pytest --cov; fails → back to Programmer
  └── Docs Writer → documents the completed feature
  → Updates state/sprint.md + state/progress.md
```

---

## Agents

| Agent | Role |
|-------|------|
| [Product Owner](../AGENTS.md#product-owner) | Reads goal → creates prioritized backlog |
| [Scrum Master](../AGENTS.md#scrum-master) | Coordinates sprint delivery cycle |
| [Architect](../AGENTS.md#architect) | Designs solution, scaffolds project skeleton |
| [Programmer](../AGENTS.md#programmer) | Implements Python features |
| [Tester](../AGENTS.md#tester) | Runs pytest, enforces ≥80% coverage |
| [Docs Writer](../AGENTS.md#docs-writer) | Generates documentation |

---

## Contents

- [Setup Guide](setup.md) — prerequisites and quick start
- [Usage Guide](usage.md) — how to drive the agents
- [Architecture](architecture.md) — how the framework is structured

---

## Output

All generated code lives in `project/`. The framework files are never modified by the agents.
After your goal is achieved, `project/` contains a standalone Python project you can use
independently — or migrate to its own repository.
