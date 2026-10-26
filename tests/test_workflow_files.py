"""Static checks of the reusable workflow files."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

# refs of supervisely-ecosystem/workflows that are known to exist / be safe
ALLOWED_WORKFLOWS_REFS = {None, "master", "${{ inputs.workflows_ref }}"}


def load(path):
    return yaml.safe_load(path.read_text())


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_is_valid_yaml(path):
    data = load(path)
    # PyYAML (YAML 1.1) reads the `on:` key as boolean True
    assert "jobs" in data and (True in data or "on" in data)


def _steps(data):
    for job in data["jobs"].values():
        for step in job.get("steps", []) or []:
            yield step


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_helper_checkout_uses_existing_ref(path):
    """H-1: update_models_common.yml checked out the deleted branch runner-updates."""
    for step in _steps(load(path)):
        uses = step.get("uses", "")
        with_ = step.get("with", {}) or {}
        if uses.startswith("actions/checkout") and with_.get("repository") == "supervisely-ecosystem/workflows":
            assert with_.get("ref") in ALLOWED_WORKFLOWS_REFS, (path.name, with_.get("ref"))
