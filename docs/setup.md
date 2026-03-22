# Setup Guide

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| GitHub Copilot CLI | AI agent runtime | [Install docs](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli) |
| Python 3.12+ | Runtime (sqlite3 built-in) | [python.org](https://python.org) |
| `uv` | Python package management for built projects | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `git` | Version control | pre-installed on most systems |

---

## Option A: GitHub Template (Recommended)

1. Click **"Use this template"** on the [fleet repository](https://github.com/fwillemen/fleet)
2. Name your new repository and choose visibility
3. Clone your new repo:
   ```bash
   git clone https://github.com/<your-username>/<your-project>.git
   cd <your-project>
   ```

## Option B: Cookiecutter

```bash
pip install cookiecutter
cookiecutter gh:fwillemen/fleet --checkout cookiecutter
```

Follow the prompts (project name, description, GitHub username, Python version).

---

## First-Time Setup

### 1. Describe your goal

Edit `state/goal.md` — replace all `[FILL IN ...]` placeholders:

```
state/goal.md
├── Goal Statement   → What does this project do? (2–5 sentences)
├── Constraints      → Hard requirements the solution must satisfy
├── Non-Goals        → What is explicitly OUT of scope
├── Success Criteria → How will you know when it's done?
└── Technical Prefs  → Preferred libraries, APIs, patterns
```

### 2. Initialize state

```bash
bash scripts/init-state.sh
```

This sets up the SQLite database (`state/fleet.db`) used by agents to track work.

### 3. Launch Copilot CLI

```bash
copilot --allow-all --experimental
```

> **Tip:** `--allow-all` enables autonomous operation — agents won't ask for
> approval at each step. Remove it if you prefer to review every action.

### 4. Start the fleet

```
Use the product-owner agent to create a backlog
```

Then:

```
Use the scrum-master agent to build the top 5 features
```

---

## Resuming Across Sessions

```bash
copilot --continue
```

Or paste the contents of `fleet/prompts/fleet-resume.md` at the start of a new session.

---

## Model Configuration

The fleet supports assigning different LLM models to different agent roles via
`.github/agents/models.yaml`. This lets you balance cost and quality.

### Changing Model Assignments

Edit `.github/agents/models.yaml` and update the `model` field for any role:

```yaml
models:
  architect:
    model: "anthropic/claude-opus-4"  # Upgrade to Opus for complex projects
```

### Available Models (examples)
| Model | Best for | Cost tier |
|-------|----------|-----------|
| `anthropic/claude-sonnet-4-5` | Complex reasoning, design | Medium |
| `openai/gpt-4o` | Coding, coordination | Medium |
| `openai/gpt-4o-mini` | Documentation, simple tasks | Low |
| `google/gemini-2.0-flash` | Fast checks, shell execution | Very low |

### Secrets Required
Add these to your repository secrets (Settings → Secrets → Actions):
| Secret | Purpose |
|--------|---------|
| `ANTHROPIC_API_KEY` | Claude models |
| `OPENAI_API_KEY` | GPT models |
| `OPENROUTER_API_KEY` | OpenRouter (multi-provider) |

### CI/CD Setup
The `fleet-sprint.yml` workflow reads `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and
`OPENROUTER_API_KEY` from repository secrets. Set these before running fleet sprints
via GitHub Actions.

---

## CI/CD Setup

Fleet provides two GitHub Actions workflows:

### fleet-sprint.yml — Run a sprint autonomously
Trigger: `Actions → Fleet Sprint → Run workflow`
Inputs:
- `sprint_size`: Number of features to build (default: 3)
- `budget_usd`: Maximum cost budget in USD (default: 5.00)

### fleet-verify.yml — Verify coverage on push/PR
Trigger: Any push to `main` or PR that modifies `project/`
- Runs ruff, mypy, pytest with coverage
- Fails if coverage < 80%
- Posts coverage percentage to PR summary

Both workflows require the API key secrets listed in the Model Configuration section.
