"""Static checks of the reusable workflow files."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
# caller templates, copied into app repositories
TEMPLATES = sorted((ROOT / "templates").glob("*.yml"))

# refs of supervisely-ecosystem/workflows that are known to exist / be safe
ALLOWED_WORKFLOWS_REFS = {None, "master", "${{ inputs.workflows_ref }}"}


def load(path):
    return yaml.safe_load(path.read_text())


@pytest.mark.parametrize("path", WORKFLOWS + TEMPLATES, ids=lambda p: p.name)
def test_workflow_is_valid_yaml(path):
    data = load(path)
    # PyYAML (YAML 1.1) reads the `on:` key as boolean True
    assert "jobs" in data and (True in data or "on" in data)


def _steps(data):
    for job in data["jobs"].values():
        for step in job.get("steps", []) or []:
            yield step


@pytest.mark.parametrize("path", WORKFLOWS + TEMPLATES, ids=lambda p: p.name)
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


REUSABLE = [
    "common.yml",
    "build_image.yml",
    "build_image_from_template.yml",
    "sync_models_common.yml",
    "update_models_common.yml",
]


@pytest.mark.parametrize("name", REUSABLE)
def test_reusable_workflows_use_a_read_only_token(name):
    """M-10: the release job's GITHUB_TOKEN had write-all and stayed in .git/config."""
    data = _workflow(name)
    assert data.get("permissions") == {"contents": "read"}
    for step in _steps(data):
        if step.get("uses", "").startswith("actions/checkout"):
            assert (step.get("with") or {}).get("persist-credentials") is False, step


@pytest.mark.parametrize("name", ["build_image.yml", "build_image_from_template.yml"])
def test_inputs_and_secrets_are_not_interpolated_into_scripts(name):
    """M-10: ${{ inputs.* }} / ${{ secrets.* }} inside run: is a shell-injection vector."""
    for step in _steps(_workflow(name)):
        script = step.get("run", "")
        assert "${{ inputs." not in script, step.get("name")
        assert "${{ secrets." not in script, step.get("name")


def test_templates_do_not_run_in_this_repository():
    """L-8: templates in .github/workflows ran on every push to this repository."""
    names = {p.name for p in WORKFLOWS}
    assert not names & {"release.yml", "release_branch.yml", "build_release_branch.yml", "publish.yml"}
    assert {p.name for p in TEMPLATES} >= {"release.yml", "release_branch.yml", "build_release_branch.yml"}


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_templates_call_this_repo_at_master(path):
    """build_release_branch.yml called the builder @build-test-image, a deleted branch."""
    for job in load(path)["jobs"].values():
        uses = job.get("uses", "")
        if uses.startswith("supervisely-ecosystem/workflows/"):
            assert uses.endswith("@master"), (path.name, uses)


RUNNER_TOKENS = [
    "SUPERVISELY_PROD_API_TOKEN",
    "SUPERVISELY_DEV_API_TOKEN",
    "SUPERVISELY_PRIVATE_DEV_API_TOKEN",
    "SUPERVISELY_GITHUB_ACCESS_TOKEN",
    "SUPERVISELY_SDK_GITHUB_ACCESS_TOKEN",
]


@pytest.mark.parametrize("name", ["common.yml", "sync_models_common.yml", "update_models_common.yml"])
def test_runner_jobs_mask_tokens_first(name):
    """C-1 (option A): tokens from the runner environment are not GitHub secrets, so not masked."""
    for job in _workflow(name)["jobs"].values():
        if job.get("runs-on") != "gha-runner-supervisely-ecosystem":
            continue
        first = job["steps"][0]
        assert first.get("name") == "Mask release credentials", name
        assert "::add-mask::" in first["run"]
        for token in RUNNER_TOKENS:
            assert token in first["run"], (name, token)
