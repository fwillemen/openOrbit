#!/usr/bin/env bash
# scripts/build-context-brief.sh
# Generates a compact context brief from fleet.db for agent delegation prompts.
# Output is capped at ~800 tokens of Markdown.
# Usage: bash scripts/build-context-brief.sh <db_path> [sprint_id]
set -e

DB_PATH="${1:-state/fleet.db}"
SPRINT_ID="${2:-}"

if [ ! -f "$DB_PATH" ]; then
  echo "⚠️  Database not found: $DB_PATH"
  exit 1
fi

python3 - "$DB_PATH" "$SPRINT_ID" <<'PYEOF'
import sqlite3, sys, json

db_path = sys.argv[1]
sprint_id = sys.argv[2] if len(sys.argv) > 2 else ""
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

lines = ["## 📋 Fleet Context Brief\n"]

# Module map
modules = conn.execute("SELECT name, path, public_api FROM modules ORDER BY name").fetchall()
if modules:
    lines.append("\n### Existing Modules\n")
    for m in modules:
        apis = json.loads(m['public_api']) if m['public_api'] else []
        api_str = ", ".join(apis[:5]) + ("…" if len(apis) > 5 else "")
        lines.append(f"- `{m['name']}` ({m['path']}): {api_str}\n")
else:
    lines.append("\n### Existing Modules\n- No modules registered yet.\n")

# Active ADRs (last 5)
adrs = conn.execute("""
    SELECT adr_number, title FROM decisions ORDER BY adr_number DESC LIMIT 5
""").fetchall()
if adrs:
    lines.append("\n### Architecture Decisions (last 5)\n")
    for a in adrs:
        lines.append(f"- ADR-{a['adr_number']}: {a['title']}\n")

# Common failure types
failures = conn.execute("""
    SELECT failure_type, COUNT(*) as cnt FROM test_runs
    WHERE failure_type IS NOT NULL
    GROUP BY failure_type ORDER BY cnt DESC LIMIT 3
""").fetchall()
if failures:
    lines.append("\n### Common Failure Patterns\n")
    for f in failures:
        lines.append(f"- `{f['failure_type']}` ({f['cnt']} occurrences)\n")

# Sprint context
sprint = conn.execute("""
    SELECT s.name, COUNT(si.id) as total,
           SUM(CASE WHEN si.status='done' THEN 1 ELSE 0 END) as done
    FROM sprints s JOIN sprint_items si ON si.sprint_id = s.id
    WHERE s.status='active' GROUP BY s.id
""").fetchone()
if sprint:
    lines.append(f"\n### Sprint Status\n")
    lines.append(f"- {sprint['name']}: {sprint['done']}/{sprint['total']} items done\n")

conn.close()

brief = "".join(lines)
# Cap at ~4000 chars (~800 tokens)
if len(brief) > 4000:
    brief = brief[:3950] + "\n… (truncated)\n"
print(brief)
PYEOF
