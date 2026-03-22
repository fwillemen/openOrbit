# Project Goal

> Fill in this file before running `scripts/init-state.sh`.
> The Product Owner and all agents read this file as their primary input.

---

## Goal Statement

Build a modern, powerful API service that tracks and analyzes launch events worldwide, including space launches (satellites, rockets) and publicly observable military-related launches, using OSINT (Open Source Intelligence). The system aggregates data from publicly available sources, normalizes it, and exposes it through a clean, developer-friendly API similar to RocketLaunch Live. Over time, the platform should evolve from simple scraping of known sources to more advanced correlation and inference based on patterns and multiple signals. The primary user value is providing a centralized, reliable dataset for dashboards, analytics, and situational awareness of global launch activity.

---

## Constraints

* Must be implemented in Python 3.12+
* Must expose a REST API (JSON-based)
* Must rely strictly on publicly available (OSINT) data sources
* Must NOT use or simulate classified, restricted, or real-time military intelligence
* Must avoid real-time tactical or sensitive predictions
* Must be deployable as a lightweight service (Docker-compatible)
* Must handle rate limiting and respectful scraping of external sources
* Must be modular to allow adding new data sources over time

---

## Non-Goals

* Real-time detection or prediction of sensitive military operations
* Use of restricted intelligence sources
* Building a full frontend application (API-first focus)
* High-confidence prediction of undisclosed or covert launches
* Weapon targeting or actionable defense applications

---

## Success Criteria

* [ ] API returns structured launch data (date, provider, location, type: civilian/military/public reports)
* [ ] System aggregates and normalizes multiple OSINT sources (≥3 sources)
* [ ] Launch events include metadata such as confidence level and source attribution
* [ ] Basic inference layer exists (e.g. pattern-based or multi-source correlation)
* [ ] API is stable, documented, and usable for dashboards and analytics

---

## Technical Preferences

* Language: Python 3.12+
* Package manager: uv
* Framework: FastAPI
* Database: SQLite (initial) → optional PostgreSQL later
* Scraping: httpx + BeautifulSoup / selectolax
* Scheduling: APScheduler or cron-based jobs
* Data format: JSON (REST API)
* Containerization: Docker

---

## Context / Background

* Reference API to emulate: https://www.rocketlaunch.live/api
* Initial sources:

  * Space agency websites (NASA, ESA, etc.)
  * Commercial launch providers
  * Public NOTAMs / maritime warnings
  * News and OSINT aggregators
* Approach:

  * Phase 1: scrape structured public launch schedules
  * Phase 2: aggregate multiple OSINT signals
  * Phase 3: add inference and confidence scoring
* Goal is to enable dashboards, analytics, and insights into global launch activity (civilian and publicly reported military-related)
