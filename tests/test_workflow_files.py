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


def _workflow(name):
    return load(ROOT / ".github" / "workflows" / name)


def test_update_models_common_uses_its_own_seg_input():
    """M-12: SEG_MODELS_PATH came from github.event.inputs.models_path, ignoring the input."""
    steps = list(_steps(_workflow("update_models_common.yml")))
    env = next(s["env"] for s in steps if s.get("name") == "Sync models")
    assert env["SEG_MODELS_PATH"] == "${{ inputs.SEG_MODELS_PATH }}"
    assert env["DET_MODELS_PATH"] == "${{ inputs.DET_MODELS_PATH }}"


@pytest.mark.parametrize(
    "name,key,dispatch_input",
    [
        ("update_models_manual.yml", "SEG_MODELS_PATH", "seg_models_path"),
        ("sync_models_manual.yml", "DET_MODELS_PATH", "det_models_path"),
    ],
)
def test_manual_templates_pass_legacy_paths_from_their_own_inputs(name, key, dispatch_input):
    data = _workflow(name)
    job = next(iter(data["jobs"].values()))
    assert job["with"][key] == "${{ github.event.inputs.%s }}" % dispatch_input
    assert job["with"]["MODELS_PATH"] == "${{ github.event.inputs.models_path }}"
