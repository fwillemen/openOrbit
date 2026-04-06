"""Tests that validate the GitHub Actions CI workflow has the required structure."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOW_PATH = Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:  # type: ignore[type-arg]
    """Load the CI workflow YAML."""
    assert WORKFLOW_PATH.exists(), f"CI workflow not found at {WORKFLOW_PATH}"
    with WORKFLOW_PATH.open() as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    return data  # type: ignore[return-value]


def test_workflow_loads(workflow: dict) -> None:  # type: ignore[type-arg]
    """Workflow file is valid YAML and non-empty."""
    assert workflow


def test_required_jobs_present(workflow: dict) -> None:  # type: ignore[type-arg]
    """lint, typecheck, and test jobs must all exist."""
    jobs = workflow.get("jobs", {})
    assert "lint" in jobs, "Missing 'lint' job"
    assert "typecheck" in jobs, "Missing 'typecheck' job"
    assert "test" in jobs, "Missing 'test' job"


def _get_triggers(workflow: dict) -> dict:  # type: ignore[type-arg]
    """Return the triggers dict, handling PyYAML parsing 'on' as boolean True."""
    return workflow.get(True, workflow.get("on", {}))  # type: ignore[arg-type]


def test_trigger_push_main(workflow: dict) -> None:  # type: ignore[type-arg]
    """Workflow triggers on push to main."""
    triggers = _get_triggers(workflow)
    push = (triggers.get("push") or {})
    branches = push.get("branches", [])
    assert "main" in branches, "push trigger must include 'main' branch"


def test_trigger_pull_request(workflow: dict) -> None:  # type: ignore[type-arg]
    """Workflow triggers on pull_request events."""
    triggers = _get_triggers(workflow)
    assert "pull_request" in triggers, "pull_request trigger must be defined"


def _python_versions_in_job(job: dict) -> list[str]:  # type: ignore[type-arg]
    """Extract all python-version values used in setup-python steps."""
    versions: list[str] = []
    for step in job.get("steps", []):
        uses = step.get("uses", "")
        if "setup-python" in uses:
            version = step.get("with", {}).get("python-version")
            if version:
                versions.append(str(version))
    return versions


def test_python_312_lint(workflow: dict) -> None:  # type: ignore[type-arg]
    """lint job uses Python 3.12."""
    versions = _python_versions_in_job(workflow["jobs"]["lint"])
    assert "3.12" in versions, f"lint job must use Python 3.12, found: {versions}"


def test_python_312_typecheck(workflow: dict) -> None:  # type: ignore[type-arg]
    """typecheck job uses Python 3.12."""
    versions = _python_versions_in_job(workflow["jobs"]["typecheck"])
    assert "3.12" in versions, f"typecheck job must use Python 3.12, found: {versions}"


def test_python_312_test(workflow: dict) -> None:  # type: ignore[type-arg]
    """test job uses Python 3.12."""
    versions = _python_versions_in_job(workflow["jobs"]["test"])
    assert "3.12" in versions, f"test job must use Python 3.12, found: {versions}"


def test_coverage_threshold_enforced(workflow: dict) -> None:  # type: ignore[type-arg]
    """test job must enforce 80% coverage minimum."""
    steps = workflow["jobs"]["test"].get("steps", [])
    pytest_steps = [s for s in steps if "pytest" in s.get("run", "")]
    assert pytest_steps, "No pytest step found in test job"
    combined = " ".join(s.get("run", "") for s in pytest_steps)
    assert "--cov-fail-under=80" in combined, (
        "test job must enforce --cov-fail-under=80"
    )
