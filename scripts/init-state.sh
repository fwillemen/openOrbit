#!/usr/bin/env bash
# scripts/init-state.sh
# Initializes the fleet state database and validates setup.
# Requires: python3 (3.12+) — uses Python's built-in sqlite3 module (no sqlite3 CLI needed)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DB_PATH="$REPO_ROOT/state/fleet.db"
SCHEMA_PATH="$REPO_ROOT/state/schema.sql"
GOAL_PATH="$REPO_ROOT/state/goal.md"

echo ""
echo "🚀 Fleet Framework — Initialization"
echo "===================================="

# Check python3 is available (sqlite3 is built into Python stdlib)
if ! command -v python3 &>/dev/null; then
  echo "❌ python3 is required but not found."
  echo "   Install Python 3.12+: https://python.org"
  exit 1
fi

# Check goal.md has been filled in
if grep -q '\[FILL IN' "$GOAL_PATH"; then
  echo ""
  echo "⚠️  state/goal.md has not been filled in yet."
  echo ""
  echo "   Please edit state/goal.md and replace all [FILL IN ...] placeholders"
  echo "   with your actual project goal, constraints, and success criteria."
  echo ""
  echo "   Then re-run: bash scripts/init-state.sh"
  echo ""
  exit 1
fi

# Remove existing database if reinitializing
if [ -f "$DB_PATH" ]; then
  echo "ℹ️  Existing state/fleet.db found. Reinitializing..."
  rm "$DB_PATH"
fi

# Initialize the database using Python's built-in sqlite3 module
python3 - <<PYEOF
import sqlite3, sys
schema = open("$SCHEMA_PATH").read()
conn = sqlite3.connect("$DB_PATH")
conn.executescript(schema)
conn.commit()
tables = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
print(f"✅ state/fleet.db initialized with schema")
print(f"   Tables created: {tables}")
conn.close()
PYEOF

echo ""
echo "✅ Setup complete! Here's what to do next:"
echo ""
echo "   1. Launch Copilot CLI for autonomous operation:"
echo "      copilot --allow-all --experimental"
echo ""
echo "   2. Have Copilot create your product backlog from state/goal.md."
echo "      Paste the following prompt into Copilot CLI:"
echo ""
echo "   ┌─────────────────────────────────────────────────────────────────┐"
sed 's/^/   │  /' "$REPO_ROOT/fleet/prompts/fleet-start.md"
echo "   └─────────────────────────────────────────────────────────────────┘"
echo ""
echo "   3. Once the backlog is ready, start your first sprint."
echo "      Replace [N] with the number of features to build, then paste:"
echo ""
echo "   ┌─────────────────────────────────────────────────────────────────┐"
sed 's/^/   │  /' "$REPO_ROOT/fleet/prompts/fleet-sprint.md"
echo "   └─────────────────────────────────────────────────────────────────┘"
echo ""
echo "   💡 Check status at any time: bash scripts/fleet-status.sh"
echo "   🎨 Live agent dashboard:     python3 scripts/fleet-viz.py --watch"
echo ""

# Animated splash (interactive terminals only, graceful skip)
if [ -t 1 ]; then
  python3 "$SCRIPT_DIR/fleet-splash.py" 2>/dev/null || true
fi
