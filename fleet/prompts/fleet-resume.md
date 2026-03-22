Use the scrum-master agent to resume the current sprint.

Read state/fleet.db to find the active sprint and any incomplete sprint items.
For each incomplete item, determine which step was last completed (architect/programmer/tester/docs)
and resume from the next step. Continue until the sprint is complete.

If there is no active sprint, read state/backlog.md and ask me how many features to include
in the next sprint before proceeding.
