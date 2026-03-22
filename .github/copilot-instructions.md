# Copilot Instructions — Fleet Framework

## Project Context
This is a semi-autonomous development framework. A fleet of **eight specialized custom agents**
(defined in `.github/agents/`) collaborates to build software from a high-level goal stored in
`state/goal.md`. Read `AGENTS.md` for the full delegation chain and agent details.

## Agent Roster (Quick Reference)
| Agent | File | When invoked |
|-------|------|-------------|
| **Product Owner** | `product-owner.agent.md` | Once: creates the backlog from `state/goal.md` |
| **Scrum Master** | `scrum-master.agent.md` | Each sprint: orchestrates all other agents |
| **Architect** | `architect.agent.md` | Per sprint item: designs, writes ADR |
| **Programmer** | `programmer.agent.md` | Per sprint item: implements + tests |
| **Code Reviewer** | `code-reviewer.agent.md` | Per sprint item: ruff / mypy / secret scan / complexity |
| **Tester** | `tester.agent.md` | Per sprint item: pytest --cov ≥80%, typed failure diagnosis |
| **Docs Writer** | `docs-writer.agent.md` | Per sprint item: docs + README update |
| **Retrospective** | `retrospective.agent.md` | End of sprint: metrics analysis, prompt improvements |

## Session Orientation
At the start of every session:
1. Read `state/goal.md` — the overarching project goal
2. Read `state/sprint.md` — what is currently in progress
3. Read `state/progress.md` — what has been completed so far
4. Run `bash scripts/fleet-status.sh` — live DB status summary

If a sprint is in progress, resume it rather than starting a new one.

## Delivery Cycle (per sprint item)
```
Architect → Programmer → Code Reviewer → [fix loop] → Tester → [fix loop] → Docs Writer
```
After all items: **Retrospective** → sprint marked complete.

## Living Documentation — Keep Context Current
**This is critical.** As the project is built, all agents must keep the repository's
documentation and context files up to date so that every subsequent agent invocation
starts with accurate knowledge:

### What each agent must update
- **Architect** — append ADR to `state/decisions.md`; update `project/README.md` with new module overview
- **Programmer** — register new module in `modules` table (`fleet.db`) after each implementation
- **Docs Writer** — update `docs/` API references AND update the **project-level `project/README.md`**
  to reflect the current feature set (add feature to the "Features" or "Usage" section)
- **Scrum Master** — keep `state/sprint.md` and `state/progress.md` current after every step
- **Retrospective** — annotate `.github/agents/*.agent.md` files with `<!-- RETRO: -->` suggestions

### Context brief (injected before every delegation)
The Scrum Master runs `bash scripts/build-context-brief.sh state/fleet.db` before each
agent delegation and prepends the output to the prompt. This brief contains:
- Existing module map (from `modules` table)
- Last 5 ADRs (from `decisions` table)
- Common failure patterns (from `test_runs` table)
- Sprint status

### project/README.md
Once the first sprint item is implemented, `project/README.md` becomes a living document.
Every agent involved in delivery must treat it as the single source of truth for what the
project does and how to use it. The Docs Writer is responsible for keeping it accurate
after every sprint item completion.

## Observability
- Every agent writes NDJSON events to `state/agent-log.ndjson` (see FM-001 in each agent)
- View recent events: `bash scripts/fleet-status.sh`
- Generate full audit: `bash scripts/generate-audit.sh`
- Handoff files in `state/handoffs/<sprint_id>/` validate each agent completed its work

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
- `state/agent-log.ndjson`, `state/handoffs/`, `state/audit.md`, `state/retrospective.md` are runtime artifacts (gitignored)

## Model Configuration
Each agent has a preferred model defined in `.github/agents/models.yaml`. The Scrum Master
passes a `Preferred model:` hint with each delegation. Override any role's model by specifying
it explicitly in the invocation prompt. Current defaults: Architect + Retrospective = Claude
Sonnet; Programmer + Scrum Master = GPT-4o; Code Reviewer + Tester = Gemini Flash.

## Cost & Budget
Default sprint budget: $5.00 USD. The Scrum Master warns at 80% usage and halts at 100%.
Cost is tracked per agent in `budget_events` table and shown in `fleet-status.sh` output.

## Autonomous Operation
- Proceed without asking for human approval unless genuinely blocked
- If blocked by an ambiguity that cannot be resolved from `state/goal.md`, write
  the blocker clearly to `state/progress.md` and surface it to the user
- Never break existing passing tests
- 80% test coverage is a hard requirement before any sprint item is considered done
- After each sprint, run the Retrospective agent — it improves future sprint quality
