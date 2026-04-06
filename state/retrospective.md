# Sprint 5 Retrospective — 2026-04-06

## Sprint Summary

| Metric | Value |
|--------|-------|
| Items Delivered | 5/5 |
| Items Blocked | 0 |
| Fix Cycles | 0 (all items passed first time) |
| Sprint Status | ✅ COMPLETED |
| Budget Used | $0.00 / $5.00 |
| Sprint Duration | ~58 minutes (17:27 → 18:25 UTC) |

## Items Delivered

| ID | Title | Tests | Coverage | Notes |
|----|-------|-------|----------|-------|
| PO-017 | Tier 3 News RSS Scraper | 36 | 92% (news.py) | Extended `PublicFeedScraper`; ADR-015 |
| PO-026 | CI/CD Pipeline | 8 | N/A | GitHub Actions — lint / typecheck / test jobs; ADR-012 |
| PO-038 | Bluesky Social Scraper | 35 | 87% (bluesky.py) | Anonymous AT Protocol public API; ADR-013 |
| PO-039 | Mastodon Social Scraper | 28 | 93% (mastodon.py) | Link-header pagination; ADR not recorded |
| PO-034 | Launch Event FTS5 Search | 10 (+32 run) | N/A | `?q=` endpoint, expanded FTS5 schema, migration guard; ADR-021 |

## What Went Well

1. **Zero fix cycles** — All 5 items passed code review and testing on the first attempt, a sprint-best result.
2. **Strong coverage** — Every new module exceeded the 80% floor: news.py 92%, mastodon.py 93%, bluesky.py 87%.
3. **Consistent OSINT classification** — All Tier 3 scrapers (RSS, Bluesky, Mastodon) correctly set `source_tier=3`, `evidence_type=media`, `claim_lifecycle=rumor`, `event_kind=inferred` without drift.
4. **FTS5 schema migration is future-proof** — The column-count guard in `init_db_schema()` allows the FTS table to be extended again without a manual migration step.
5. **CI/CD now enforces quality gates** — GitHub Actions runs lint + mypy + pytest on every push and PR, closing the gap between agent-local checks and repository-wide enforcement.
6. **Sprint pace** — All 5 items completed in under 1 hour from sprint start.

## Delivery Notes

### PO-017 — Tier 3 News RSS Scraper
- Extends `PublicFeedScraper` (the existing public feed adapter), keeping the scraper surface area minimal.
- 36 tests cover feed parsing, keyword filtering, deduplication, and error handling.
- Code reviewer caught an unused `asyncio` import and added a `type: ignore[override]` on `parse()` to match the pattern established in sibling scrapers — small but consistent house-keeping.

### PO-026 — CI/CD Pipeline (GitHub Actions)
- Three parallel jobs: `lint` (ruff), `typecheck` (mypy strict), `test` (pytest --cov ≥80%).
- Triggers on push to `main` and all pull requests.
- Test validation required a workaround: PyYAML parses the YAML key `on` as boolean `True`, so the test uses `workflow.get(True)` not `workflow['on']`.

### PO-038 — Bluesky Social Scraper
- Uses `public.api.bsky.app` with no credentials — entirely anonymous.
- Searches 5 keywords × 5 tracked accounts; deduplicates by post URI before upsert.
- 35 tests; 87% coverage. Rate limit: 1 req / 3 s (~30 s per full run), `refresh_interval_hours=2`.

### PO-039 — Mastodon Social Scraper
- Fetches public hashtag timelines from configurable instance (`MASTODON_INSTANCE`, default `mastodon.social`).
- Follows `Link: <...>; rel="next"` pagination with a `MAX_PAGES_PER_HASHTAG=2` guard.
- HTML stripped via `re.sub` before keyword filtering. 28 tests; 93% coverage.
- Slug: `sha1('mastodon|{url}')[:12]` prefixed with `mastodon-`.

### PO-034 — Launch Event FTS5 Full-Text Search
- FTS5 table expanded from 3 columns to 6 (`name`, `description`, `provider`, `vehicle`, `location`, `slug`).
- Three triggers (INSERT / UPDATE / DELETE) keep the FTS index in sync automatically.
- `GET /v1/launches?q=` routes to `fts_search()` when present; returns 400 if combined with cursor pagination.
- Migration guard in `init_db_schema()` detects old schema by column count and rebuilds automatically.

## Coverage by Module

| Module | Coverage |
|--------|---------|
| `scrapers/news.py` | 92% |
| `scrapers/bluesky.py` | 87% |
| `scrapers/mastodon.py` | 93% |
| `.github/workflows/ci.yml` | Validated via YAML test (8 tests) |
| `api/v1/launches.py` (FTS additions) | Covered by 10 new FTS tests |
| Overall suite (pre-sprint baseline) | 93% |

## Improvements for Next Sprint

1. **Record ADR numbers in fleet.db `decisions` table for every sprint item** — PO-039 and PO-034 logged ADRs in agent logs but did not insert rows into the `decisions` table, creating a gap in the audit trail.
2. **Add `budget_events` instrumentation to Scrum Master delegations** — Two consecutive sprints (4 and 5) recorded zero budget rows; cost visibility is blind.
3. **Bluesky coverage gap (87%)** — Just above the floor; the programmer or tester should note which branches are uncovered and add targeted tests in the next related sprint.
4. **Social scraper abstraction** — Bluesky and Mastodon share very similar `_is_relevant` / slug / attribution patterns. A `SocialScraper` base class (between `BaseScraper` and the two implementations) would reduce duplication for any future social signal scrapers.
5. **FTS search: add `?q=` + tier-filter combination** — Currently `?q=` and `?tier=` can be combined (tier filter applies inside `fts_search()`), but this is not tested end-to-end and not documented in the API reference.
6. **CI workflow: add artifact upload for coverage HTML** — Engineers can't inspect coverage details without re-running locally. `actions/upload-artifact` on the test job would surface this in the PR.

## Action Items

| # | Item | Owner | Priority |
|---|------|-------|---------|
| 1 | Add `SocialScraper` base class to reduce Bluesky/Mastodon duplication | Architect + Programmer | Medium |
| 2 | Wire `budget_events` recording into Scrum Master agent delegations | Scrum Master | High |
| 3 | Insert `decisions` rows for every ADR (PO-039, PO-034 missing) | Programmer / Scrum Master | Medium |
| 4 | Add coverage HTML artifact upload to CI workflow | Programmer | Low |
| 5 | Test and document `?q=` + `?tier=` combination in API reference | Docs Writer | Low |

## Remaining Backlog

```sql
SELECT COUNT(*) FROM backlog_items WHERE status='pending';
-- ~11 pending items remain after Sprint 5 completions
```

---

# Sprint 4 Retrospective — 2026-04-06

## Sprint Summary

| Metric | Value |
|--------|-------|
| Items Delivered | 4/4 |
| Items Blocked | 0 |
| Sprint Status | ✅ COMPLETED |
| Budget Used | $0.00 / $5.00 |
| Test Runs Logged | 5 |

## Items Delivered

| ID | Title | Key Achievement |
|----|-------|----------------|
| PO-027 | Fix notams.py SyntaxError | Critical syntax error fixed, all 422+ tests passing |
| PO-028 | Source Tier & Claim Lifecycle Schema | 6 new DB columns, all scrapers updated, 13 migration tests |
| PO-029 | Provenance API Evidence Chain | GET /v1/launches/{slug}/evidence, 100% module coverage |
| PO-016 | Admin Health Monitoring Endpoints | 3 admin endpoints, 100% module coverage, auth tests |

## Test Coverage

| Module | Coverage |
|--------|---------|
| `api/v1/evidence.py` | 100% |
| `api/v1/admin.py` | 100% |
| `models/api.py` | 100% |
| `models/db.py` | 100% |
| Overall new code | 100% |

## What Went Well

1. **Parallel delivery** — PO-029 and PO-016 were built concurrently, reducing wall-clock time
2. **Test-first discipline** — All new modules achieved 100% line coverage
3. **Schema migration pattern** — Idempotent ALTER TABLE pattern in db.py is reusable across future sprints
4. **Auth reuse** — `require_admin` dependency cleanly secured all admin endpoints without duplication

## What Could Be Improved

1. **DB checkpoint after each agent** — Write sprint_items flags immediately after each sub-agent returns to enable idempotent resumption
2. **Scrape trigger stub** — POST /admin/sources/{id}/refresh returns 202 but doesn't trigger real scrape; real job queue needed in future sprint
3. **Test suite speed** — Full test suite takes 2+ minutes; consider pytest-xdist parallelization
4. **Budget tracking gap** — No budget_events were recorded for Sprint 4 agents; budget instrumentation should be wired into each agent delegation

## Action Items

| # | Item | Priority |
|---|------|---------|
| 1 | Implement real job queue for /admin/sources/{id}/refresh | Medium |
| 2 | Add pytest-xdist for parallel test execution | Low |
| 3 | Add `evidence_url` to paginated list response (currently only on detail endpoint) | Low |
| 4 | Wire budget_events recording into Scrum Master agent delegations | Medium |

## Remaining Backlog

16 pending items remain in the backlog.

```sql
SELECT COUNT(*) FROM backlog_items WHERE status='pending';
-- Result: 16
```
