"""build_image.yml: inputs moved from ${{ }} interpolation to env (M-10) must not
change what the steps execute. Same approach as test_template_env_refactor.py."""

import subprocess

import pytest

from workflow_runner import ROOT, fake_bin, run_step

WF = "build_image.yml"
BASE_COMMIT = "09ca757"
STEPS = [
    "Info",
    "Set tags",
    "Get SDK version",
    "Build Docker Image ${{ env.IMAGE_NAME }}:${{ inputs.tag_version }}",
    "Build Docker Image ${{ env.IMAGE_NAME }}:latest",
]
INPUT_SETS = {
    "sdk-input": {"tag_version": "1.2.3", "dockerfile_path": "docker/Dockerfile", "image_name": "",
                  "sdk_version": "6.73.450", "latest_tag": True},
    "label-in-file": {"tag_version": "1.2.3", "dockerfile_path": "docker/Dockerfile", "image_name": "custom",
                      "sdk_version": "", "latest_tag": False},
}


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


def run_variant(tmp_path, workflow_root, step, inputs):
    work = tmp_path / ("base" if workflow_root != ROOT else "new")
    work.mkdir()
    (work / "docker").mkdir()
    # trailing newline present, so the M-9 change does not affect the comparison
    (work / "docker" / "Dockerfile").write_text("FROM scratch\nLABEL python_sdk_version=6.73.1\n")
    log = work / "_argv"
    bin_dir = work / "_bin"
    fake_bin(bin_dir, "buildctl", f'{{ printf "%s\\n" "$@"; echo ---; }} >> {log}\n')
    proc, exported = run_step(
        WF, "build-and-push", step, work, inputs=inputs,
        env={"IMAGE_NAME": "supervisely/my-app"},
        github={"repository": "supervisely-ecosystem/my-app"},
        fake_bin_dir=bin_dir, workflow_root=workflow_root,
    )
    argv = log.read_text().replace(str(work), "<WS>") if log.exists() else ""
    dockerfile = (work / "docker" / "Dockerfile").read_text().strip().splitlines()
    outputs = (work / "_github_output").read_text()
    return proc.returncode, proc.stdout, exported, argv, dockerfile, outputs


@pytest.mark.parametrize("input_set", sorted(INPUT_SETS))
@pytest.mark.parametrize("step", STEPS)
def test_step_behaviour_unchanged(tmp_path, base_root, step, input_set):
    before = run_variant(tmp_path, base_root, step, INPUT_SETS[input_set])
    after = run_variant(tmp_path, ROOT, step, INPUT_SETS[input_set])
    assert before[0] == 0
    # M-9 adds a blank line before the appended LABEL; ignore blank lines
    norm = lambda r: r[:4] + ([l for l in r[4] if l.strip()],) + r[5:]
    assert norm(after) == norm(before)
