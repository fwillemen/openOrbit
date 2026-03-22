# 🚀 Fleet — Semi-Autonomous Multi-Agent Development Framework

> **A GitHub Copilot CLI template that builds your Python project for you.**

[![Use this template](https://img.shields.io/badge/Use%20this%20template-2ea44f?style=for-the-badge&logo=github)](https://github.com/fwillemen/fleet/generate)
[![CI — Fleet Verify](https://github.com/fwillemen/fleet/actions/workflows/fleet-verify.yml/badge.svg)](https://github.com/fwillemen/fleet/actions/workflows/fleet-verify.yml)

Fleet is a reusable framework for semi-autonomous software development. Describe what
you want to build in `state/goal.md`. Eight specialized AI agents — orchestrated by
the Scrum Master — plan, design, implement, review, test, document, and retrospect
your Python project, sprint by sprint.

---

## ✨ What You Get

- **Instant project planning** — MoSCoW-prioritized backlog from a plain-English goal
- **Automated implementation** — agents write, test, and iterate until coverage ≥ 80%
- **Built-in quality gate** — code review (ruff / mypy / secret scan) runs before every test
- **Self-healing test loop** — failures are typed and diagnosed; the Programmer gets targeted fix hints
- **Architecture decisions recorded** — every design choice logged as an ADR
- **Living documentation** — `project/README.md` and `docs/` are updated after every sprint item
- **Sprint retrospectives** — automatic analysis of fix cycles, coverage trends, and cost
- **Cost-aware execution** — per-agent token budgets with configurable per-sprint cap
- **Parallel sprint items** — dependency-aware scheduling runs up to 3 items concurrently
- **Multi-model routing** — each agent role uses the optimal model (configurable in `models.yaml`)
- **CI/CD ready** — GitHub Actions workflows included for unattended operation
- **Fully portable output** — `project/` is a standalone Python project you own

---

## 🤖 Agent Roster

| Agent | Role | Invoked |
|-------|------|---------|
| **Product Owner** | Reads `state/goal.md` → prioritized backlog | Once, at start |
| **Scrum Master** | Orchestrates the full sprint cycle | Each sprint |
| **Architect** | Designs solution, writes ADR, scaffolds `project/` | Per item |
| **Programmer** | Implements Python features (type-safe, tested) | Per item |
| **Code Reviewer** | Runs ruff / mypy / secret scan / complexity checks | Per item |
| **Tester** | Runs `pytest --cov`; typed failure diagnosis ≥80% | Per item |
| **Docs Writer** | Updates `docs/` and `project/README.md` | Per item |
| **Retrospective** | Analyzes metrics, annotates agents with improvements | End of sprint |

### Delivery Chain
```
Product Owner ──▶ backlog
                      │
              Scrum Master (per sprint)
                      │
            ┌─────────▼──────────┐
            │  Step 0: Context   │  ← build-context-brief.sh
            │  Step 1: Architect │  ← design + ADR
            │  Step 2: Programmer│  ← implement
            │  Step 3: Code Review│ ← quality gate (ruff/mypy/secrets)
            │  Step 4: Tester    │  ← pytest ≥80%; self-healing fix loop
            │  Step 5: Docs Writer│ ← docs/ + project/README.md
            └─────────┬──────────┘
                      │  (repeat for each sprint item, up to P=3 in parallel)
                      ▼
               Retrospective ──▶ state/retrospective.md + agent annotations
```

---

## 🚀 Quick Start

### Option 1 — GitHub Template (recommended)

Click **[Use this template](https://github.com/fwillemen/fleet/generate)** →
name your repo → clone it → fill in `state/goal.md` → launch Copilot CLI.

### Option 2 — Cookiecutter

```bash
pip install cookiecutter
cookiecutter gh:fwillemen/fleet --checkout cookiecutter
```

### Then: launch the fleet

```bash
# 1. Describe your goal
edit state/goal.md

# 2. Initialize the state database
bash scripts/init-state.sh

# 3. Launch Copilot CLI in autonomous mode
copilot --allow-all --experimental
```

In the chat:

```
Use the product-owner agent to create a backlog
```

```
Use the scrum-master agent to build the top 5 features
```

That's it. Watch your project get built — with docs, tests, and a retrospective included.

---

## 📁 Repository Structure

```
fleet/
├── .github/
│   ├── agents/
│   │   ├── product-owner.agent.md
│   │   ├── scrum-master.agent.md
│   │   ├── architect.agent.md
│   │   ├── programmer.agent.md
│   │   ├── code-reviewer.agent.md    ← quality gate
│   │   ├── tester.agent.md
│   │   ├── docs-writer.agent.md
│   │   ├── retrospective.agent.md    ← sprint analysis
│   │   └── models.yaml               ← per-role model config + rate cards
│   ├── workflows/
│   │   ├── fleet-sprint.yml          ← run sprints via GitHub Actions
│   │   └── fleet-verify.yml          ← auto-verify coverage on push/PR
│   ├── copilot-instructions.md       ← agent context (auto-injected)
│   └── instructions/
│       └── python-standards.instructions.md
├── scripts/
│   ├── init-state.sh                 ← initialize state/fleet.db
│   ├── fleet-status.sh               ← live sprint status + cost summary
│   ├── fleet-viz.py                  ← pixelated agent dashboard (--watch / --replay)
│   ├── fleet-splash.py               ← animated intro banner
│   ├── build-context-brief.sh        ← generates agent memory brief
│   └── generate-audit.sh             ← generates state/audit.md from event log
├── state/
│   ├── goal.md                       ← ✏️  YOU FILL THIS IN
│   ├── backlog.md                    ← auto-generated by Product Owner
│   ├── sprint.md                     ← auto-updated by Scrum Master
│   ├── progress.md                   ← auto-updated by all agents
│   ├── decisions.md                  ← Architecture Decision Records
│   └── schema.sql                    ← SQLite schema (used by init-state.sh)
├── docs/                             ← framework documentation
├── fleet/prompts/                    ← ready-made prompt templates
├── project/                          ← ALL generated code lives here
└── AGENTS.md                         ← agent roster + delegation chain details
```

---

## ⚙️ Technology Stack (Defaults)

| Concern | Default |
|---------|---------|
| Language | Python 3.12+ |
| Package manager | `uv` |
| Testing | `pytest` + `pytest-cov` (≥80% coverage required) |
| Linting | `ruff` |
| Type checking | `mypy` (strict) |
| Docstrings | Google style |
| Commit style | Conventional Commits |
| Model routing | `models.yaml` (per-role, configurable) |
| Default sprint budget | $5.00 USD (configurable) |

---

## 📖 Documentation

- [Setup Guide](docs/setup.md) — prerequisites, installation, CI/CD, model config
- [Usage Guide](docs/usage.md) — how to drive the agents, sprint commands, tester loop
- [Architecture](docs/architecture.md) — framework internals, observability, handoffs
- [Full Agent Guide](AGENTS.md) — complete delegation chain with all 8 agents

---

## 🔄 Resuming Across Sessions

```bash
copilot --continue
# or paste fleet/prompts/fleet-resume.md at the start of a new session
```

Check current state at any time:

```bash
bash scripts/fleet-status.sh

# Live pixelated agent dashboard (auto-refreshes every 2 s)
python3 scripts/fleet-viz.py --watch state/fleet.db

# Replay a past sprint as an animation
python3 scripts/fleet-viz.py --replay state/agent-log.ndjson
```

---

## 🔁 CI/CD (GitHub Actions)

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `fleet-sprint.yml` | Manual (`workflow_dispatch`) | Runs a full sprint autonomously in CI |
| `fleet-verify.yml` | Push / PR to `project/` | Runs ruff → mypy → pytest; fails if coverage < 80% |

See [docs/setup.md](docs/setup.md) for required secrets (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`).

---

## 💡 Using This as a Template

1. Click **Use this template** on GitHub (or use cookiecutter — see [Setup Guide](docs/setup.md))
2. Fill in `state/goal.md` with your project's goal
3. Run `bash scripts/init-state.sh`
4. Start Copilot CLI and invoke the agents

Your `state/goal.md` is the only input the fleet needs. Everything else — backlog,
architecture, code, tests, docs, retrospective — is automated.

---

## Prerequisites

| Tool | Install |
|------|---------|
| GitHub Copilot CLI | [Install docs](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli) |
| Python 3.12+ | [python.org](https://python.org) |
| `uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
