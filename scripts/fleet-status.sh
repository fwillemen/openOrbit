#!/usr/bin/env bash
# scripts/fleet-status.sh
# Displays current fleet state summary from state/fleet.db
# Requires: python3 (uses built-in sqlite3 module)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DB_PATH="$REPO_ROOT/state/fleet.db"

if [ ! -f "$DB_PATH" ]; then
  echo "⚠️  state/fleet.db not found. Run: bash scripts/init-state.sh"
  exit 1
fi

python3 - "$DB_PATH" <<'PYEOF'
import sqlite3, os, sys

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

print()
print("📊 Fleet Status")
print("===============")

# Backlog summary
print()
print("📋 Backlog")
rows = conn.execute("""
    SELECT priority,
           COUNT(*) as total,
           SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done,
           SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
           SUM(CASE WHEN status='in_sprint' THEN 1 ELSE 0 END) as in_sprint
    FROM backlog_items
    GROUP BY priority
    ORDER BY CASE priority
        WHEN 'Must Have' THEN 1
        WHEN 'Should Have' THEN 2
        WHEN 'Could Have' THEN 3
        ELSE 4
    END
""").fetchall()
if rows:
    print(f"  {'Priority':<15} {'Total':>5} {'Done':>5} {'Pending':>8} {'In Sprint':>10}")
    print(f"  {'-'*15} {'-'*5} {'-'*5} {'-'*8} {'-'*10}")
    for r in rows:
        print(f"  {r['priority']:<15} {r['total']:>5} {r['done']:>5} {r['pending']:>8} {r['in_sprint']:>10}")
else:
    print("  No backlog items yet.")

# Active sprint
print()
print("🏃 Active Sprint")
sprint = conn.execute("SELECT id, name FROM sprints WHERE status='active' LIMIT 1").fetchone()
if not sprint:
    print("  No active sprint.")
else:
    rows = conn.execute("""
        SELECT item_id, item_title, priority, item_status,
               architect_done, programmer_done, tester_done, docs_done,
               fix_cycles, final_coverage_pct
        FROM current_sprint_status
    """).fetchall()
    if rows:
        print(f"  {sprint['name']}")
        print(f"  {'Item':<10} {'Title':<30} {'Status':<14} {'A':>2} {'P':>2} {'T':>2} {'D':>2} {'Cov':>6} {'Fixes':>6}")
        print(f"  {'-'*10} {'-'*30} {'-'*14} {'-'*2} {'-'*2} {'-'*2} {'-'*2} {'-'*6} {'-'*6}")
        for r in rows:
            cov = f"{r['final_coverage_pct']:.0f}%" if r['final_coverage_pct'] else "-"
            print(f"  {r['item_id']:<10} {r['item_title'][:29]:<30} {r['item_status']:<14} "
                  f"{'✅' if r['architect_done'] else '⏳':>2} "
                  f"{'✅' if r['programmer_done'] else '⏳':>2} "
                  f"{'✅' if r['tester_done'] else '⏳':>2} "
                  f"{'✅' if r['docs_done'] else '⏳':>2} "
                  f"{cov:>6} {r['fix_cycles']:>6}")

# Overall progress
print()
print("📈 Overall Progress")
r = conn.execute("""
    SELECT
        (SELECT COUNT(*) FROM backlog_items) as total_items,
        (SELECT COUNT(*) FROM backlog_items WHERE status='done') as completed,
        (SELECT COUNT(*) FROM sprints WHERE status='completed') as sprints_done,
        (SELECT COUNT(*) FROM test_runs WHERE passed=1) as tests_passed,
        (SELECT ROUND(AVG(coverage_pct),1) FROM test_runs WHERE passed=1) as avg_coverage_pct
    FROM (SELECT 1)
""").fetchone()
print(f"  Backlog items:    {r['completed']}/{r['total_items']} completed")
print(f"  Sprints done:     {r['sprints_done']}")
print(f"  Test runs passed: {r['tests_passed']}")
print(f"  Avg coverage:     {r['avg_coverage_pct'] or '-'}%")
print()

# Agent log summary
import os, json as _json
log_path = os.path.join(os.path.dirname(db_path), "agent-log.ndjson")
if os.path.exists(log_path):
    print()
    print("📝 Recent Agent Events (last 10)")
    with open(log_path) as f:
        events = [_json.loads(l) for l in f if l.strip()]
    for ev in events[-10:]:
        status_icon = "✅" if ev.get("outcome") == "pass" else ("❌" if ev.get("outcome") == "fail" else "⏳")
        print(f"  {status_icon} [{ev.get('ts','')[:19]}] {ev.get('agent','?'):15} {ev.get('action','?')[:40]}")

# Cost summary
try:
    cost_rows = conn.execute("""
        SELECT agent, SUM(cost_usd) as total_cost, SUM(tokens_in+tokens_out) as total_tokens
        FROM budget_events
        WHERE sprint_id = (SELECT id FROM sprints WHERE status='active' LIMIT 1)
        GROUP BY agent ORDER BY total_cost DESC
    """).fetchall()
    if cost_rows:
        print()
        print("💰 Sprint Cost Estimate")
        total = 0.0
        for r in cost_rows:
            print(f"  {r['agent']:<20} ${r['total_cost']:.4f}  ({r['total_tokens']} tokens)")
            total += r['total_cost']
        print(f"  {'TOTAL':<20} ${total:.4f}")
except Exception:
    pass

conn.close()
PYEOF

# Show pixelated agent dashboard (interactive terminals only, graceful skip)
if [ -t 1 ]; then
  echo ""
  python3 "$SCRIPT_DIR/fleet-viz.py" "$DB_PATH" 2>/dev/null || true
fi
