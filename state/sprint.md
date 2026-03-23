# Sprint 2 — 2025-01-23

**Goal:** Implement data normalization pipeline, REST API, all three OSINT scrapers, deduplication, attribution/confidence, background scheduler, inference layer, Docker deployment, and API hardening (rate limiting + pagination).

**Sprint Budget:** $5.00 USD (warn at $4.00)

---

## Dependency Groups

```
Group 1: PO-004 (foundation — no deps)
Group 2: PO-005, PO-006, PO-007 (parallel — all depend on PO-004)
Group 3: PO-008 (depends on Group 2)
Group 4: PO-009, PO-010, PO-012, PO-013 (parallel — various deps on Groups 2/3)
Group 5: PO-011 (depends on PO-008 + PO-009)
```

---

## In Progress

| ID | Feature | Status |
|----|---------|--------|
| PO-008 | Multi-Source Aggregation, Deduplication & Entity Merging | 🔨 Implementing |

---

## Queued

| ID | Feature | Depends On |
|----|---------|------------|
| PO-009 | Source Attribution, Confidence Scoring & Launch Type Classification | PO-008 |
| PO-010 | APScheduler Background Refresh Jobs & Respectful Scraping | PO-005, PO-006, PO-007 |
| PO-011 | Basic Inference & Multi-Source Correlation Layer | PO-008, PO-009 |
| PO-012 | Docker Deployment — Dockerfile & docker-compose | PO-004, PO-005 |
| PO-013 | API Rate Limiting, Pagination & Advanced Query Filtering | PO-005 |

---

## Completed This Sprint

| ID | Feature | Coverage |
|----|---------|----------|
| PO-004 | Data Normalization Pipeline & Canonical LaunchEvent Model | 100% normalizer, 96% model |
| PO-005 | REST API — Core Launch Listing & Detail Endpoints | 93% launches router |
| PO-006 | OSINT Scraper — Commercial Launch Providers (Source 2) | 84% commercial scraper |
| PO-007 | OSINT Scraper — Public NOTAMs & Maritime Advisories (Source 3) | 100% notam_parser, 90% scraper |

---

## Blocked

| ID | Feature | Blocker |
|----|---------|---------|

---

# Sprint 1 — 2026-03-22

## Goal
Deliver foundational infrastructure for openOrbit: bootstrap project structure, implement database layer, and build first OSINT scraper.

## Sprint Items (Sequential Execution)

### Dependency Chain
```
PO-001 (Bootstrap) → PO-002 (Database) → PO-003 (Scraper)
```

## In Progress
| ID | Feature | Status |
|----|---------|--------|

## Pending (Blocked by Dependencies)
| ID | Feature | Blocked By |
|----|---------|------------|

## Completed This Sprint
| ID | Feature | Coverage | Delivered |
|----|---------|----------|-----------|
| PO-001 | Project Bootstrap, Repository Structure & Configuration Management | 80% | ✅ Architecture, Implementation, Code Review, Tests, Docs |
| PO-002 | Core Database Schema & SQLite Persistence Layer | 87% | ✅ Architecture, Implementation, Code Review (1 fix cycle), Tests, Docs |
| PO-003 | OSINT Scraper — Space Agency Launch Schedules | 93% | ✅ Architecture, Implementation, Code Review, Tests, Docs |

## Blocked
| ID | Feature | Blocker |
|----|---------|---------|

---
**Sprint Budget:** $5.00 USD  
**Spent:** $0.00  
**Remaining:** $5.00
