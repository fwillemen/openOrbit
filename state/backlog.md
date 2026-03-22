# Fleet Framework — Product Backlog

> **Source:** Desk research into multi-agent best practices (Anthropic engineering,
> Microsoft Multi-Agent Reference Architecture, Google Cloud ADK, AWS agentic patterns,
> CrewAI, AutoGen, GitHub Copilot CLI custom agent docs, 2024-2025 literature).
> **Scope:** Improvements to the fleet metalayer itself — not to any generated project.
> **Last updated:** 2026-03-22

---

## Summary

| Priority    | Count | Done |
|-------------|-------|------|
| Must Have   | 10    | 0    |
| Should Have | 0     | 0    |
| Could Have  | 0     | 0    |
| Won't Have  | 0     | —    |

---

## Research Findings & Gap Analysis

The fleet framework was benchmarked against leading multi-agent best practices.
Six gaps were rated critical (Must Have) and four rated architecturally important
(also Must Have) given their direct impact on autonomous operation quality.

### Key Sources Consulted
- Anthropic: *How we built our multi-agent research system* (2025)
- Microsoft: *Multi-Agent Reference Architecture* — Patterns & Observability
- Google Cloud: *Choose a design pattern for your agentic AI system*
- AWS: *Agentic AI patterns and workflows*
- Zylos AI: *AI Agent Self-Healing and Auto-Recovery Patterns* (2026)
- Scalex: *Self-Healing Codebases with Agentic AI in CI/CD* (2025)
- Benjamin Abt: *GitHub Copilot Custom Agents for Full-Stack Teams* (2026)
- Collabnix: *Multi-Agent and Multi-LLM Architecture — Complete Guide* (2025)
- Braintrust: *What is agent observability? Tracing tool calls, memory, and multi-step workflows*
- Microsoft Azure AI Foundry: *Observability for Multi-Agent Systems* (2025)

---

## Must Have

---

### FM-001: Structured Agent Observability & Audit Trail

**Priority:** Must Have
**Research basis:** Anthropic, Microsoft Azure AI Foundry, Braintrust — *"Observability is
about making the internal decision-making and interactions of autonomous agents transparent
across the entire workflow."* Audit trails are critical for compliance, debugging, and trust.

**Description:**
Every agent invocation must write structured, machine-readable events to `state/agent-log.ndjson`
(newline-delimited JSON). Each event captures: agent name, sprint item ID, step number,
action taken, outcome (pass/fail/blocked), timestamp, and estimated token count.
The `scripts/fleet-status.sh` script is updated to parse this log and display a human-readable
summary. A new `state/audit.md` is generated on demand showing the full audit trail for the
last completed sprint. This is the single source of truth for debugging agent behaviour.

**Acceptance Criteria:**
- [ ] Every agent (architect, programmer, tester, docs-writer, scrum-master) writes at least
      one NDJSON event per invocation to `state/agent-log.ndjson`
- [ ] Event schema: `{ts, agent, sprint_id, item_id, step, action, outcome, tokens_est}`
- [ ] `scripts/fleet-status.sh` outputs a structured summary table parsed from the log
- [ ] `scripts/generate-audit.sh` creates `state/audit.md` with full trail for last sprint
- [ ] Log is append-only; never truncated between sprints (use sprint_id to filter)
- [ ] `.gitignore` excludes `state/agent-log.ndjson` (runtime artifact, not committed)
- [ ] Documented in `docs/architecture.md` under "Observability"

**Status:** `pending`

---

### FM-002: Self-Healing Tester with Typed Failure Diagnosis

**Priority:** Must Have
**Research basis:** Zylos AI, Scalex, DeepWiki/ms-agent — *"LLM-based systems can analyze
stack traces or error messages, generate corrective code, and re-run failing tasks."* Structured
diagnosis reduces fix-cycle count by giving the Programmer targeted, typed hints.

**Description:**
The Tester agent currently returns unstructured failure text to the Scrum Master, which passes it
verbatim to the Programmer. This is inefficient — the Programmer must re-parse raw pytest output.
Instead, the Tester must classify each failure into a typed category and provide a structured
JSON diagnosis block. The Programmer agent is updated to consume this structured input and apply
targeted fix strategies per failure type, dramatically reducing fix-cycle count.

**Failure types and fix strategies:**

| Failure Type | Tester Signal | Programmer Strategy |
|---|---|---|
| `import-error` | Missing module / wrong import path | Add dependency via `uv add`, fix import |
| `assertion-error` | Test assertion mismatch | Fix implementation logic or fixture |
| `coverage-gap` | Lines not covered (list provided) | Add test cases for uncovered branches |
| `type-error` | mypy strict violation (list provided) | Add type annotations, fix type mismatches |
| `syntax-error` | Python syntax / indentation issue | Fix syntax before re-running |
| `fixture-error` | conftest fixture missing or broken | Fix test infrastructure |

**Acceptance Criteria:**
- [ ] Tester produces a structured diagnosis block in `state/handoffs/<sprint_id>/tester.json`
      with fields: `failure_type`, `affected_files`, `line_numbers`, `error_summary`, `fix_hint`
- [ ] Programmer agent reads and acknowledges the diagnosis block before fixing
- [ ] Fix strategy documentation for each failure type added to `.github/agents/tester.agent.md`
- [ ] Average fix cycles per item tracked in `test_runs` table (new `failure_type` column)
- [ ] `fleet-status.sh` shows fix-cycle count per sprint item
- [ ] Documented in `docs/usage.md` under "Tester Loop"

**Status:** `pending`

---

### FM-003: Parallel Sprint Item Execution

**Priority:** Must Have
**Research basis:** CrewAI, AutoGen, AWS patterns — *"Enhanced parallelism, scalability, and
specialization... natural fit for enterprise-scale workflows."* Sequential processing is the
primary bottleneck in current fleet throughput.

**Description:**
The Scrum Master currently processes sprint items strictly sequentially: item 1 fully completes
before item 2 begins. For sprints with independent items (no shared modules), this is unnecessary
overhead. The Scrum Master must support a configurable parallelism level `P` (default 1, max 3)
that allows up to P items to be in the Architect/Programmer/Tester cycle simultaneously.
Dependencies between items are declared in a `sprint_deps` table and respected during scheduling.

**Acceptance Criteria:**
- [ ] New `sprint_deps(sprint_item_id, depends_on_item_id)` table in `state/fleet.db`
- [ ] Scrum Master queries dependency graph before scheduling; only starts items whose
      dependencies are `done`
- [ ] Parallelism level `P` configurable in Scrum Master invocation prompt (default: 1)
- [ ] `state/sprint.md` shows parallel execution groups clearly
- [ ] Parallel execution uses Copilot CLI's background agent mode (`mode: background`)
- [ ] If a parallel item fails, only that item is retried; others continue
- [ ] `state/progress.md` shows wall-clock time savings vs. sequential estimate
- [ ] Documented in `docs/usage.md` under "Running a Sprint"

**Status:** `pending`

---

### FM-004: Code Review / Quality Gate Agent

**Priority:** Must Have
**Research basis:** Benjamin Abt (GitHub Copilot custom agents, 2026), GitHub docs —
*"A security agent should only check vulnerabilities; keep agents focused on a single
responsibility."* A dedicated quality gate before tests catches structural issues early,
reducing expensive test-fix cycles.

**Description:**
Add a new `code-reviewer` agent (`.github/agents/code-reviewer.agent.md`) invoked by the
Scrum Master between the Programmer and Tester steps. The agent runs automated checks and
produces a structured review. If the review fails, the Programmer is given the review
output and fixes before tests run. This front-loads cheap static checks, saving the
heavier test-run cycles for structurally sound code.

**Review checks (in order):**
1. `ruff check src/ tests/ --output-format=json` — lint errors
2. `mypy src/ --output=json` — type errors (strict mode)
3. Secret pattern scan — no API keys, tokens, or passwords in source
4. Import hygiene — no circular imports, no `from x import *`
5. Complexity check — no function exceeds cyclomatic complexity 10 (`ruff C901`)

**Acceptance Criteria:**
- [ ] `.github/agents/code-reviewer.agent.md` created with the review protocol above
- [ ] Agent writes `state/handoffs/<sprint_id>/code-reviewer.json` with per-check results
- [ ] Scrum Master invokes code-reviewer after Programmer, before Tester
- [ ] On review failure, Programmer is re-invoked with structured review (not Tester)
- [ ] On review pass, `code_review_done = 1` set in `sprint_items`
- [ ] New `code_reviews` table in `state/fleet.db` (item_id, check, result, details)
- [ ] AGENTS.md updated with code-reviewer entry
- [ ] Documented in `docs/architecture.md`

**Status:** `pending`

---

### FM-005: Cross-Sprint Context Briefing (Agent Memory Injection)

**Priority:** Must Have
**Research basis:** ReAct (Reason+Act loop), LangChain memory patterns, Anthropic —
*"Equip agents with short- and long-term memory for persistent context."* Agents starting
fresh each invocation is the primary cause of inconsistent naming, duplicated modules,
and ADR drift across sprints.

**Description:**
Currently each agent receives only the immediate sprint item details in its invocation prompt.
The Scrum Master must construct a rich **context brief** from `fleet.db` before each agent
delegation. This brief is a compact Markdown section injected at the top of every delegation
prompt, giving agents awareness of: existing modules, previous ADRs, common patterns used,
and known failure modes from past fix cycles. The brief is built from structured DB queries,
not from reading all files again.

**Context brief sections:**
- **Module map** — list of existing `src/` modules and their public APIs (from `modules` table)
- **Active ADRs** — last 5 ADR titles from `state/decisions.md`
- **Known pitfalls** — top 3 failure types from `test_runs` in this project
- **Naming conventions** — extracted from the first ADR (package name, class naming style)
- **Sprint context** — current sprint number, items done so far, items remaining

**Acceptance Criteria:**
- [ ] New `modules(name, path, public_api_summary, updated_at)` table in `state/fleet.db`
- [ ] Programmer agent updates `modules` table after each successful implementation
- [ ] `scripts/build-context-brief.sh` (or Python helper) generates the context brief Markdown
- [ ] Scrum Master calls context-brief builder before each delegation and prepends to prompt
- [ ] Context brief is capped at 800 tokens (enforced by the builder script)
- [ ] Integration test: verify brief contains module map after one completed sprint item
- [ ] Documented in `docs/architecture.md` under "Agent Memory"

**Status:** `pending`

---

### FM-006: CI/CD Integration via GitHub Actions

**Priority:** Must Have
**Research basis:** Dev.to (Copilot CLI in GitHub Actions, 2025) — *"Embed agents in CI/CD
using GitHub Actions so they can make qualitative checks before human review."*
Manual CLI launches break the autonomous operation promise and prevent unattended operation.

**Description:**
Add two GitHub Actions workflows to `.github/workflows/`:

1. **`fleet-sprint.yml`** — `workflow_dispatch` trigger. Inputs: `sprint_size` (int, default 3).
   Installs Copilot CLI, initializes fleet, runs the Scrum Master agent autonomously.
   Posts a sprint summary as a workflow summary and as a GitHub issue comment.

2. **`fleet-verify.yml`** — triggered on `push` to `main` and `pull_request`. Changes to
   `project/` trigger a test run (`uv run pytest --cov`) and post results as a PR check.
   Fails the check if coverage drops below 80%.

**Acceptance Criteria:**
- [ ] `.github/workflows/fleet-sprint.yml` created and documented
- [ ] `.github/workflows/fleet-verify.yml` created and documented
- [ ] `fleet-sprint.yml` uses GitHub-hosted runner (ubuntu-latest)
- [ ] Both workflows use repository secrets for API keys (documented in `docs/setup.md`)
- [ ] `fleet-sprint.yml` posts sprint summary to GitHub Actions job summary
- [ ] `fleet-verify.yml` posts coverage percentage as a PR status check
- [ ] `docs/setup.md` has a new "CI/CD Setup" section explaining required secrets
- [ ] README updated with CI/CD badge

**Status:** `pending`

---

### FM-007: Sprint Retrospective Agent

**Priority:** Must Have
**Research basis:** AutoGen Bench, Anthropic multi-agent research — *"Adaptive feedback loops:
agents capture incidents, learn from failures, and improve their repair policies."*
Without retrospectives, the fleet cannot improve between sprints.

**Description:**
Add a new `retrospective` agent (`.github/agents/retrospective.agent.md`) invoked by the
Scrum Master after all sprint items are done. The agent queries `fleet.db` for the completed
sprint's metrics, identifies patterns, and produces two outputs: (1) a `state/retrospective.md`
file with findings, and (2) concrete prompt improvement suggestions written as comments
directly into the relevant `.github/agents/*.agent.md` files.

**Retrospective analysis includes:**
- Fix cycle count per item (items needing >2 cycles flagged as "high friction")
- Most common failure types (from `test_runs.failure_type`)
- Coverage trend (this sprint vs. previous sprint average)
- Blocked items and their blockers
- Wall-clock time per item (from agent-log.ndjson timestamps)
- Suggested prompt improvements (3-5 concrete suggestions)

**Acceptance Criteria:**
- [ ] `.github/agents/retrospective.agent.md` created
- [ ] Agent reads `sprints`, `sprint_items`, `test_runs`, `code_reviews` tables
- [ ] `state/retrospective.md` written with structured findings in Markdown table format
- [ ] Agent appends a `<!-- RETRO: <suggestion> -->` comment to relevant `.agent.md` files
- [ ] Scrum Master invokes retrospective as final step of every sprint
- [ ] `state/progress.md` links to the retrospective for each completed sprint
- [ ] AGENTS.md updated with retrospective agent entry

**Status:** `pending`

---

### FM-008: Cost & Token Budget Tracking

**Priority:** Must Have
**Research basis:** CrewAI cost management, multi-LLM architecture guide —
*"Estimate and monitor LLM API/token usage as multi-agent workflows scale."*
Untracked LLM costs can make fleet sprints unexpectedly expensive, undermining
confidence in autonomous operation.

**Description:**
Add a lightweight cost tracking layer. Each agent estimates token usage for its primary
LLM calls using per-model rate cards defined in `.github/agents/models.yaml`. Usage is
logged to a `budget_events` table. The Scrum Master checks accumulated cost before each
delegation and warns (in `state/progress.md`) when 80% of the sprint budget is consumed.
The sprint budget is configurable per sprint via the invocation prompt.

**Rate card (stored in models.yaml, approximate 2025 pricing per 1K tokens):**
```yaml
openai/gpt-4o:      { input: 0.0025, output: 0.010 }
anthropic/claude-3-5-sonnet: { input: 0.003, output: 0.015 }
google/gemini-2.0-flash:     { input: 0.0001, output: 0.0004 }
```

**Acceptance Criteria:**
- [ ] `.github/agents/models.yaml` created with rate cards for ≥5 common models
- [ ] New `budget_events(id, sprint_id, agent, model, tokens_in, tokens_out, cost_usd, ts)` table
- [ ] Each agent includes a `<!-- BUDGET: est. ~N tokens -->` comment in its output
- [ ] Scrum Master reads budget_events and emits a warning in `state/progress.md` at 80% usage
- [ ] `scripts/fleet-status.sh` shows total sprint cost (estimated USD) in its output
- [ ] Sprint budget configurable: default $5.00, overridable in invocation prompt
- [ ] `docs/usage.md` section "Cost Management" documents the budget system

**Status:** `pending`

---

### FM-009: Structured Agent Handoff Protocol (Handoff Contracts)

**Priority:** Must Have
**Research basis:** Microsoft Multi-Agent Reference Architecture — *"Standardize inter-agent
messaging and policy enforcement for auditability and governance."* Silent failures where
an agent marks itself `done` without completing work are a critical reliability gap.

**Description:**
Formalize agent handoffs with a lightweight JSON contract. Before marking itself done in
`fleet.db`, each agent must write a handoff file to `state/handoffs/<sprint_id>/<agent>.json`.
The next agent in the chain reads and validates this file before starting work. If the file
is missing or invalid, the agent raises a structured error to the Scrum Master rather than
proceeding silently. This prevents cascading failures from undetected partial completions.

**Handoff contract schema:**
```json
{
  "agent": "programmer",
  "sprint_id": "sprint-1",
  "item_id": "PO-001",
  "status": "done",
  "summary": "Implemented ToolRegistry in core/registry.py",
  "outputs": ["src/osint_app/core/registry.py", "tests/test_registry.py"],
  "caveats": ["TODO: add async support in future sprint"],
  "timestamp": "2026-03-22T10:00:00Z"
}
```

**Acceptance Criteria:**
- [ ] `state/handoffs/` directory created (gitignored as runtime artifact)
- [ ] All 6 existing agents updated to write a handoff JSON before marking done
- [ ] Each agent validates the preceding agent's handoff before starting
- [ ] Validation failure raises a structured error with handoff file path and missing fields
- [ ] Scrum Master logs handoff validation failures to `state/agent-log.ndjson`
- [ ] `scripts/fleet-status.sh` shows handoff chain status per sprint item
- [ ] Schema documented in `docs/architecture.md` under "Handoff Protocol"

**Status:** `pending`

---

### FM-010: Multi-Model Agent Configuration

**Priority:** Must Have
**Research basis:** Collabnix multi-LLM architecture (2025), Anthropic — *"Each agent role
benefits from different model capabilities: fast/cheap for simple tasks, powerful for
complex reasoning."* Using the same model for all agents wastes money on simple tasks
and underserves complex ones.

**Description:**
Add `.github/agents/models.yaml` mapping each agent role to a preferred LLM model.
The Scrum Master reads this config and passes a `model_hint` in each delegation prompt.
Agents include the model hint in their Copilot CLI invocation context. This allows
cost/quality optimization: use a fast cheap model for the Tester (which mostly runs
shell commands), a mid-tier model for the Programmer, and the most capable model
for the Architect where design quality matters most.

**Recommended defaults (balancing cost and quality):**
```yaml
architect:    anthropic/claude-sonnet-4-5   # Complex reasoning, ADR writing
programmer:   openai/gpt-4o                 # Solid coder, good at Python
code-reviewer: google/gemini-2-flash        # Fast, cheap, good at static analysis
tester:       google/gemini-2-flash         # Mostly shell execution, minimal LLM needed
docs-writer:  openai/gpt-4o-mini            # Good writing, cost-effective
retrospective: anthropic/claude-sonnet-4-5  # Pattern recognition, analytical
scrum-master: openai/gpt-4o                 # Coordination, structured delegation
```

**Acceptance Criteria:**
- [ ] `.github/agents/models.yaml` created with model assignments for all 7 agent roles
- [ ] Models.yaml documents why each model was chosen for each role
- [ ] Scrum Master reads models.yaml and includes `Preferred model: <model>` in delegation prompt
- [ ] Any agent can be overridden by the user at invocation time
- [ ] `budget_events` table (FM-008) records which model was actually used per invocation
- [ ] `docs/setup.md` documents how to change model assignments
- [ ] README mentions model configurability as a key feature

**Status:** `pending`

