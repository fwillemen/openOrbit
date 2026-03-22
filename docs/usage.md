# Usage Guide

## Driving the Fleet

Fleet agents are driven by natural-language instructions in the Copilot CLI chat.
The standard workflow is linear — each step feeds the next.

---

## Step 1: Create the Backlog

```
Use the product-owner agent to create a backlog
```

The Product Owner reads `state/goal.md` and writes a MoSCoW-prioritized backlog
to `state/backlog.md`. It also inserts items into `state/fleet.db` for agent tracking.

**Output:** `state/backlog.md`

---

## Step 2: Run a Sprint

```
Use the scrum-master agent to build the top 5 features
```

Adjust `5` to however many features you want in this sprint. The Scrum Master:

1. Loads the top N pending items from the backlog
2. For each item, delegates to Architect → Programmer → Tester (loop) → Docs Writer
3. Updates `state/sprint.md` and `state/progress.md` as work completes

**Output:** code in `project/`, docs in `docs/`, updated state files

---

## Checking Status

```bash
bash scripts/fleet-status.sh
```

Or ask in chat:

```
What is the current sprint status?
```

---

## Running Additional Sprints

After Sprint 1 completes, start another:

```
Use the scrum-master agent to build the next 5 features
```

The Scrum Master picks up where it left off (already-done items are skipped).

---

## Agent-Specific Commands

You can invoke agents individually for targeted tasks:

| Goal | Command |
|------|---------|
| Refresh the backlog after editing goal.md | `Use the product-owner agent to update the backlog` |
| Architect a single feature | `Use the architect agent to design [feature]` |
| Fix failing tests | `Use the tester agent to investigate and fix failing tests` |
| Re-document a module | `Use the docs-writer agent to document [module]` |

---

## Autonomous Mode

For fully hands-off operation:

```bash
copilot --allow-all --experimental
```

Then press `Shift+Tab` to activate autopilot mode. Agents will proceed without
interruption until blocked by an unresolvable ambiguity — which they surface in
`state/progress.md`.

---

## Prompts Reference

Ready-made prompt files live in `fleet/prompts/`:

| File | Use when |
|------|----------|
| `fleet-start.md` | Starting a brand new project |
| `fleet-sprint.md` | Kicking off a sprint (edit N = desired features) |
| `fleet-resume.md` | Resuming after a session break |
