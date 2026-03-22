-- Fleet Framework SQLite Schema
-- Initialize with: sqlite3 state/fleet.db < state/schema.sql

-- Product backlog items defined by the Product Owner
CREATE TABLE IF NOT EXISTS backlog_items (
    id                   TEXT PRIMARY KEY,  -- e.g. PO-001
    title                TEXT NOT NULL,
    description          TEXT NOT NULL,
    acceptance_criteria  TEXT NOT NULL,     -- newline-separated list
    priority             TEXT NOT NULL      -- Must Have | Should Have | Could Have | Won't Have
                         CHECK (priority IN ('Must Have', 'Should Have', 'Could Have', "Won't Have")),
    status               TEXT NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'in_sprint', 'done')),
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Sprints created by the Scrum Master
CREATE TABLE IF NOT EXISTS sprints (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,         -- e.g. "Sprint 1"
    goal_items_count INTEGER NOT NULL,      -- N items selected from backlog
    status           TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'completed', 'aborted')),
    started_at       TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at     TEXT
);

-- Sprint items — links backlog items to a sprint with per-item delivery state
CREATE TABLE IF NOT EXISTS sprint_items (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_id        INTEGER NOT NULL REFERENCES sprints(id),
    backlog_item_id  TEXT NOT NULL REFERENCES backlog_items(id),
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN (
                         'pending', 'designing', 'implementing',
                         'testing', 'fixing', 'documenting', 'done', 'blocked'
                     )),
    architect_done   INTEGER NOT NULL DEFAULT 0 CHECK (architect_done IN (0,1)),
    programmer_done  INTEGER NOT NULL DEFAULT 0 CHECK (programmer_done IN (0,1)),
    tester_done      INTEGER NOT NULL DEFAULT 0 CHECK (tester_done IN (0,1)),
    docs_done        INTEGER NOT NULL DEFAULT 0 CHECK (docs_done IN (0,1)),
    code_review_done INTEGER NOT NULL DEFAULT 0 CHECK (code_review_done IN (0,1)),
    fix_cycles       INTEGER NOT NULL DEFAULT 0,  -- number of programmer fix loops
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Architecture Decision Records written by the Architect
CREATE TABLE IF NOT EXISTS decisions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_item_id   INTEGER REFERENCES sprint_items(id),
    adr_number       INTEGER NOT NULL,      -- sequential ADR number
    title            TEXT NOT NULL,
    rationale        TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Test run results recorded by the Tester
CREATE TABLE IF NOT EXISTS test_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_item_id   INTEGER NOT NULL REFERENCES sprint_items(id),
    passed           INTEGER NOT NULL CHECK (passed IN (0,1)),
    coverage_pct     REAL,                  -- NULL if tests didn't run
    failure_details  TEXT,                  -- NULL on pass
    failure_type     TEXT,                  -- NULL on pass; one of: import-error, assertion-error, coverage-gap, type-error, syntax-error, fixture-error
    run_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Trigger to keep updated_at current on backlog_items
CREATE TRIGGER IF NOT EXISTS backlog_items_updated_at
    AFTER UPDATE ON backlog_items
BEGIN
    UPDATE backlog_items SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Trigger to keep updated_at current on sprint_items
CREATE TRIGGER IF NOT EXISTS sprint_items_updated_at
    AFTER UPDATE ON sprint_items
BEGIN
    UPDATE sprint_items SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- View: current sprint overview (for quick status queries)
CREATE VIEW IF NOT EXISTS current_sprint_status AS
SELECT
    s.id          AS sprint_id,
    s.name        AS sprint_name,
    s.status      AS sprint_status,
    bi.id         AS item_id,
    bi.title      AS item_title,
    bi.priority,
    si.status     AS item_status,
    si.architect_done,
    si.programmer_done,
    si.tester_done,
    si.docs_done,
    si.code_review_done,
    si.fix_cycles,
    (
        SELECT MAX(tr.coverage_pct)
        FROM test_runs tr
        WHERE tr.sprint_item_id = si.id AND tr.passed = 1
    )             AS final_coverage_pct
FROM sprints s
JOIN sprint_items si ON si.sprint_id = s.id
JOIN backlog_items bi ON bi.id = si.backlog_item_id
WHERE s.status = 'active'
ORDER BY si.id;

-- Agent event log (append-only, gitignored)
-- Written to state/agent-log.ndjson by each agent invocation.
-- Schema documented here for reference; actual file is NDJSON not SQL.
-- {ts, agent, sprint_id, item_id, step, action, outcome, tokens_est}

-- Budget events for cost tracking (FM-008)
CREATE TABLE IF NOT EXISTS budget_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_id   INTEGER REFERENCES sprints(id),
    agent       TEXT NOT NULL,
    model       TEXT NOT NULL,
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    cost_usd    REAL NOT NULL DEFAULT 0.0,
    ts          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Code reviews written by the code-reviewer agent (FM-004)
CREATE TABLE IF NOT EXISTS code_reviews (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_item_id INTEGER NOT NULL REFERENCES sprint_items(id),
    check_name     TEXT NOT NULL,
    result         TEXT NOT NULL CHECK (result IN ('pass', 'fail', 'skip')),
    details        TEXT,
    run_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Module registry maintained by the Programmer (FM-005)
CREATE TABLE IF NOT EXISTS modules (
    name             TEXT PRIMARY KEY,
    path             TEXT NOT NULL,
    public_api       TEXT,          -- JSON list of public function/class names
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Sprint dependency graph (FM-003)
CREATE TABLE IF NOT EXISTS sprint_deps (
    sprint_item_id      INTEGER NOT NULL REFERENCES sprint_items(id),
    depends_on_item_id  INTEGER NOT NULL REFERENCES sprint_items(id),
    PRIMARY KEY (sprint_item_id, depends_on_item_id)
);
