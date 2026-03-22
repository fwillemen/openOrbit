#!/usr/bin/env bash
# scripts/generate-audit.sh
# Generates state/audit.md from state/agent-log.ndjson for the last completed sprint.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_PATH="$REPO_ROOT/state/agent-log.ndjson"
AUDIT_PATH="$REPO_ROOT/state/audit.md"

if [ ! -f "$LOG_PATH" ]; then
  echo "⚠️  No agent log found at state/agent-log.ndjson"
  echo "   Run a sprint first to generate events."
  exit 1
fi

python3 - "$LOG_PATH" "$AUDIT_PATH" <<'PYEOF'
import sys, json, datetime

log_path = sys.argv[1]
audit_path = sys.argv[2]

with open(log_path) as f:
    events = [json.loads(l) for l in f if l.strip()]

if not events:
    print("No events found in agent log.")
    sys.exit(0)

# Group by sprint_id
from collections import defaultdict
sprints = defaultdict(list)
for ev in events:
    sprints[ev.get("sprint_id", "unknown")].append(ev)

now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
lines = [f"# Fleet Agent Audit Trail\n", f"> Generated: {now}\n\n"]

for sprint_id, evs in sprints.items():
    lines.append(f"## Sprint: {sprint_id}\n\n")
    lines.append(f"| Timestamp | Agent | Item | Action | Outcome | Tokens |\n")
    lines.append(f"|-----------|-------|------|--------|---------|--------|\n")
    for ev in evs:
        ts = ev.get("ts", "")[:19]
        agent = ev.get("agent", "?")
        item = ev.get("item_id", "-")
        action = ev.get("action", "?")[:50]
        outcome = ev.get("outcome", "?")
        tokens = ev.get("tokens_est", "-")
        icon = "✅" if outcome == "pass" else ("❌" if outcome == "fail" else "⏳")
        lines.append(f"| {ts} | {agent} | {item} | {action} | {icon} {outcome} | {tokens} |\n")
    lines.append("\n")

with open(audit_path, "w") as f:
    f.writelines(lines)

print(f"✅ Audit written to {audit_path}")
print(f"   {len(events)} events across {len(sprints)} sprint(s)")
PYEOF
