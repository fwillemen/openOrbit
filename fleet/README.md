# Fleet — User Guide

A semi-autonomous multi-agent development framework powered by GitHub Copilot CLI.
Define a goal, run one command, and watch a fleet of specialized agents plan,
architect, code, test, and document your project — sprint by sprint.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Agent Reference](#agent-reference)
4. [How It Works](#how-it-works)
5. [State Files Reference](#state-files-reference)
6. [Commands Reference](#commands-reference)
7. [Resuming Across Sessions](#resuming-across-sessions)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| `copilot` (GitHub Copilot CLI) | The AI agent runtime | [Install docs](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli) |
| `python3` 3.12+ | Runtime + **sqlite3 is built-in** (no separate install needed) | [python.org](https://python.org) |
| `uv` | Python package management for built projects | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

> **Note:** The framework uses Python's built-in `sqlite3` module — you do **not** need to install the `sqlite3` CLI tool separately.

---

## Quick Start

### Step 1: Describe your goal

Edit `state/goal.md` and replace all `[FILL IN ...]` placeholders with your project details:
- What does this project do?
- Who is it for?
- What are the must-have features?
- What is out of scope?

### Step 2: Initialize the state database

```bash
bash scripts/init-state.sh
```

This creates `state/fleet.db` and validates your `state/goal.md`.

### Step 3: Launch Copilot CLI in autonomous mode

```bash
copilot --allow-all --experimental
```

- `--allow-all` bypasses per-tool permission prompts (needed for autonomous operation)
- `--experimental` enables autopilot mode (press `Shift+Tab` if not already active)

### Step 4: Create your product backlog

Paste the contents of `fleet/prompts/fleet-start.md` into the Copilot CLI prompt:

```
Use the product-owner agent to analyze my project goal and create a prioritized product backlog.
[... rest of fleet-start.md ...]
```

The Product Owner will generate `state/backlog.md` with all features prioritized.

### Step 5: Run your first sprint

Paste the contents of `fleet/prompts/fleet-sprint.md` into Copilot CLI,
replacing `[N]` with the number of features to build (recommended: 3–5):

```
Use the scrum-master agent to load the top 3 items from the backlog...
```

The fleet will autonomously build all N features, testing and documenting each one.

### Step 6: Repeat

After each sprint completes, start the next:
```
Use the scrum-master agent to load the top 3 items from the backlog into a sprint and complete them.
```

---

## Agent Reference

### 🗂 Product Owner (`product-owner`)
**When to use:** At the start, and whenever you want to add or re-prioritize features.

```
Use the product-owner agent to create a backlog from @state/goal.md
Use the product-owner agent to re-prioritize the backlog
Use the product-owner agent to add a new feature: <description>
```

**Outputs:** `state/backlog.md`, `backlog_items` table in `state/fleet.db`

---

### 🏃 Scrum Master (`scrum-master`)
**When to use:** To start or resume a sprint.

```
Use the scrum-master agent to build the top 5 features from the backlog
Use the scrum-master agent to resume the current sprint
Use the scrum-master agent to start the next sprint with 3 items
```

**Outputs:** `state/sprint.md`, `state/progress.md`, `sprints`/`sprint_items` tables

---

### 🏗 Architect (`architect`)
**Invoked by:** Scrum Master automatically. You can also invoke directly:
```
Use the architect agent to redesign the <module> module
```

**Outputs:** `project/` skeleton, ADRs in `state/decisions.md`

---

### 💻 Programmer (`programmer`)
**Invoked by:** Scrum Master automatically. You can also invoke directly:
```
Use the programmer agent to implement <specific feature>
```

**Outputs:** `project/src/`, `project/tests/`

---

### 🧪 Tester (`tester`)
**Invoked by:** Scrum Master automatically. You can also invoke directly:
```
Use the tester agent to run tests for sprint item PO-003
```

**Outputs:** Test results, `test_runs` table

---

### 📚 Docs Writer (`docs-writer`)
**Invoked by:** Scrum Master automatically. You can also invoke directly:
```
Use the docs-writer agent to update documentation for the <module> module
```

**Outputs:** `docs/` directory

---

## How It Works

```
state/goal.md (you fill this in)
       │
       ▼  fleet-start.md prompt
Product Owner
  → Reads goal
  → Creates prioritized backlog
  → Writes state/backlog.md + SQLite
       │
       ▼  fleet-sprint.md prompt (N features)
Scrum Master
  → Loads top-N items into sprint
  → For each item:
      1. Architect designs → ADR written
      2. Programmer implements → tests written
      3. Tester runs pytest --cov
         └─ if fail → back to Programmer (max 5 cycles)
         └─ if pass → continue
      4. Docs Writer documents feature
  → Sprint complete → updates state/progress.md
       │
       ▼  next sprint
Scrum Master (again, with next N items)
       ...until all Must Have items are done
```

---

## State Files Reference

| File | Who writes it | What it contains |
|------|--------------|-----------------|
| `state/goal.md` | **You** | Project goal, constraints, success criteria |
| `state/backlog.md` | Product Owner | Prioritized feature list with acceptance criteria |
| `state/sprint.md` | Scrum Master | Current sprint board (TODO/IN_PROGRESS/DONE) |
| `state/progress.md` | Scrum Master, Docs Writer | Completed features log |
| `state/decisions.md` | Architect | Architecture Decision Records (ADRs) |
| `state/fleet.db` | All agents | Machine-readable state (SQLite, gitignored) |

---

## Commands Reference

### Initialize
```bash
bash scripts/init-state.sh          # create state/fleet.db
```

### Check Status
```bash
bash scripts/fleet-status.sh        # print sprint + backlog summary
```

### Launch Copilot CLI
```bash
copilot --allow-all --experimental  # fully autonomous mode (recommended)
copilot --continue                   # resume most recent session
```

### Copilot CLI slash commands
```
/agent                  # browse and select custom agents
/allow-all              # enable all permissions this session
/fleet                  # enable parallel subagent execution
/tasks                  # view background tasks
```

---

## Resuming Across Sessions

The fleet state is fully persistent in `state/fleet.db` and the `state/*.md` files.

To resume after closing Copilot CLI:
```bash
copilot --allow-all --experimental --continue
```

Then paste `fleet/prompts/fleet-resume.md` to pick up where you left off.

---

## Troubleshooting

**Agents aren't following instructions**
- Ensure you launched with `--experimental` for autopilot mode
- Press `Shift+Tab` to cycle to autopilot mode if needed
- Run `/allow-all` if agents are asking for permission on every tool use

**Tests keep failing**
- Check `state/sprint.md` for the Blocked section
- Run `bash scripts/fleet-status.sh` to see fix cycle counts
- You can invoke the programmer directly: `Use the programmer agent to fix...`

**state/fleet.db not found**
- Run `bash scripts/init-state.sh` first
- Requires `python3` (3.12+) — sqlite3 is part of the Python standard library, no separate install needed

**goal.md validation fails**
- The script checks for `[FILL IN` text — make sure you removed ALL placeholder lines from `state/goal.md`

**Coverage below 80% after many fix cycles**
- The tester will mark items as blocked after 5 fix cycles
- You can manually invoke: `Use the programmer agent to improve test coverage for PO-XXX`

**Agent invocation not working**
- Ensure `.github/agents/*.agent.md` files exist and are committed
- Use `/agent` to browse available agents and verify they're listed
