"""build_image_from_template.yml: moving inputs/secrets from ${{ }} interpolation
to environment variables (M-10) must not change what the steps execute.

Each step is run twice - as it is at origin/HEAD 09ca757 and as it is now - with
fake buildctl/skopeo/date that record their argv, and the recordings are compared.
"""

import shutil
import subprocess

import pytest

from workflow_runner import ROOT, fake_bin, run_step

WF = "build_image_from_template.yml"
JOB = "build-and-push"
BASE_COMMIT = "09ca757"

INPUT_SETS = {
    "all-options": {
        "image_name": "", "tag_version": "6.74.34", "tag_ref_name": "",
        "dockerfile_template_path": "docker/hardened/Dockerfile.tmpl", "docker_target": "runtime",
        "requirements_file": "dev_requirements.txt", "config_file": "config.json",
        "runtime_base_image": "base-py-cuda-hardened", "extra_builder_libs": "libgl1 libglib2.0-0",
        "no_cache_requirements": True, "build_cache": True, "skip_tag_check": False,
        "cve_checks": True, "latest_tag": True, "workflows_ref": "master",
    },
    "defaults": {
        "image_name": "My-App", "tag_version": "", "tag_ref_name": "",
        "dockerfile_template_path": "docker/hardened/Dockerfile.tmpl", "docker_target": "",
        "requirements_file": "dev_requirements.txt", "config_file": "config.json",
        "runtime_base_image": "", "extra_builder_libs": "",
        "no_cache_requirements": False, "build_cache": False, "skip_tag_check": False,
        "cve_checks": False, "latest_tag": False, "workflows_ref": "master",
    },
}

STEPS = [
    "Info",
    "Prepare runtime base image",
    "Prepare tag version",
    "Prepare Dockerfile path",
    "Build image archive for checks",
    "Build and push Docker Image ${{ env.IMAGE_NAME }}:${{ env.TAG_VERSION }}",
    "Build and push Docker Image ${{ env.IMAGE_NAME }}:latest",
    "Push scanned image archive",
    "Tag and push latest from scanned image",
]


@pytest.fixture(scope="module")
def base_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("base")
    show = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{BASE_COMMIT}:.github/workflows/{WF}"],
        capture_output=True, text=True,
    )
    if show.returncode != 0:
        pytest.skip(f"commit {BASE_COMMIT} not available")
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / WF).write_text(show.stdout)
    return root


def run_variant(tmp_path, workflow_root, step, inputs, secrets):
    work = tmp_path / ("base" if workflow_root != ROOT else "new")
    work.mkdir()
    (work / "config.json").write_text('{"docker_image": "supervisely/my-app:6.74.34"}')
    (work / "dev_requirements.txt").write_text("six\n")
    (work / "docker" / "hardened").mkdir(parents=True)
    (work / "docker" / "hardened" / "Dockerfile.tmpl").write_text("FROM scratch\n")
    (work / ".venv_hardened" / "bin").mkdir(parents=True)
    (work / ".venv_hardened" / "bin" / "activate").write_text("")
    (work / "workflow" / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "resolve_release_tag.py", work / "workflow" / "scripts")
    log = work / "_argv"
    bin_dir = work / "_bin"
    for tool in ("buildctl", "skopeo"):
        fake_bin(bin_dir, tool, f'{{ echo "{tool}"; printf "%s\\n" "$@"; echo ---; }} >> {log}\n')
    fake_bin(bin_dir, "date", "echo 1700000000\n")
    env = {
        "IMAGE_NAME": "supervisely/my-app", "IMAGE_NAME_SAFE": "my-app",
        "TAG_VERSION": "6.74.34", "TAG_REF_NAME": "6.74.34",
        "DOCKERFILE_DIR": "docker/hardened", "DOCKERFILE_NAME": "Dockerfile.tmpl",
        "REQUIREMENTS_FILE": "dev_requirements.txt", "BUILD_SECRET_OPT": "",
    }
    if inputs["runtime_base_image"]:
        env["RUNTIME_BASE_IMAGE"] = inputs["runtime_base_image"]
    proc, exported = run_step(
        WF, JOB, step, work, inputs=inputs, env=env, secrets=secrets,
        github={"repository": "supervisely-ecosystem/My-App"},
        fake_bin_dir=bin_dir, workflow_root=workflow_root,
    )
    argv = log.read_text().replace(str(work), "<WS>") if log.exists() else ""
    return proc.returncode, proc.stdout.replace(str(work), "<WS>"), exported, argv


@pytest.mark.parametrize("secrets", [{}, {"DOCKERHUB_USERNAME": "u", "DOCKERHUB_TOKEN": "t0k"}], ids=["no-creds", "creds"])
@pytest.mark.parametrize("input_set", sorted(INPUT_SETS))
@pytest.mark.parametrize("step", STEPS)
def test_step_behaviour_unchanged(tmp_path, base_root, step, input_set, secrets):
    inputs = INPUT_SETS[input_set]
    before = run_variant(tmp_path, base_root, step, inputs, secrets)
    after = run_variant(tmp_path, ROOT, step, inputs, secrets)
    assert after == before
    assert before[0] == 0


def test_shell_metacharacters_in_inputs_are_not_executed(tmp_path, base_root):
    marker = tmp_path / "pwned"
    # breaks out of the double quotes the old script put around ${{ inputs.docker_target }}
    inputs = dict(INPUT_SETS["all-options"], docker_target=f'x"; touch {marker}; echo "')
    rc, _, _, argv = run_variant(
        tmp_path, ROOT, "Build and push Docker Image ${{ env.IMAGE_NAME }}:${{ env.TAG_VERSION }}",
        inputs, {},
    )
    assert not marker.exists()
    assert f'target=x";' in argv


def test_old_script_did_execute_injected_input(tmp_path, base_root):
    """Documents the problem fixed here, using the origin/HEAD 09ca757 workflow."""
    marker = tmp_path / "pwned"
    inputs = dict(INPUT_SETS["all-options"], docker_target=f'x"; touch {marker}; echo "')
    run_variant(
        tmp_path, base_root, "Build and push Docker Image ${{ env.IMAGE_NAME }}:${{ env.TAG_VERSION }}",
        inputs, {},
    )
    assert marker.exists()
