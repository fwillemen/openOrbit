Use the scrum-master agent to load the top [N] items from the backlog into a sprint and complete them autonomously.

Replace [N] with the number of features you want built (e.g. 3, 5).

The scrum-master will:
1. Read state/backlog.md and state/fleet.db to find the top-N pending items
2. Create a sprint and load those items
3. For each item, coordinate:
   - Architect: designs the solution and writes an ADR to state/decisions.md
   - Programmer: implements the feature with full tests
   - Tester: runs pytest --cov (loops back to Programmer if coverage < 80% or failures)
   - Docs Writer: documents the completed feature in docs/
4. Update state/sprint.md and state/progress.md throughout
5. Report sprint completion with coverage stats and remaining backlog

Check progress at any time: bash scripts/fleet-status.sh
