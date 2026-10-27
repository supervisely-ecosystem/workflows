"""build_image.yml "Get SDK version" step (M-9)."""

import json
import shutil
import subprocess

import pytest

from workflow_runner import run_step

STEP = ("build_image.yml", "build-and-push", "Get SDK version")


def _run(tmp_path, dockerfile_text, sdk_version):
    (tmp_path / "docker").mkdir()
    dockerfile = tmp_path / "docker" / "Dockerfile"
    dockerfile.write_text(dockerfile_text)
    proc, _ = run_step(
        *STEP, tmp_path,
        inputs={"sdk_version": sdk_version, "dockerfile_path": "docker/Dockerfile", "tag_version": "1.0.0"},
    )
    assert proc.returncode == 0, proc.stderr
    return dockerfile.read_text()


@pytest.mark.parametrize(
    "last_line",
    [
        'RUN pip install supervisely[model-benchmark]==6.73.448',
        "ENV JINA_OPTOUT_TELEMETRY=1",
        '# ENTRYPOINT [ "python" ]',
    ],
)
def test_label_is_its_own_instruction_without_trailing_newline(tmp_path, last_line):
    """RT-DETR, serve-clip-as-service, ... end without a newline."""
    text = _run(tmp_path, f"FROM python:3.12\n{last_line}", "6.73.450")
    lines = text.splitlines()
    assert last_line in lines
    assert "LABEL supervisely-sdk-version=6.73.450" in lines


def test_existing_sdk_label_is_replaced(tmp_path):
    text = _run(tmp_path, "FROM python:3.12\nLABEL python_sdk_version=6.73.1\nRUN true\n", "6.73.450")
    assert "python_sdk_version=6.73.1" not in text
    assert text.splitlines()[-1] == "LABEL supervisely-sdk-version=6.73.450"


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")
def test_label_reaches_the_built_image(tmp_path):
    """Build a FROM-scratch image (no pull) and read the label back."""
    _run(tmp_path, "FROM scratch\nENV JINA_OPTOUT_TELEMETRY=1", "6.73.450")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        pytest.skip("docker daemon not running")
    tag = "sly-workflows-test/label-check:latest"
    build = subprocess.run(
        ["docker", "build", "-q", "-t", tag, "-f", "docker/Dockerfile", "."],
        cwd=tmp_path, capture_output=True, text=True,
    )
    try:
        assert build.returncode == 0, build.stderr
        cfg = json.loads(
            subprocess.run(["docker", "image", "inspect", tag], capture_output=True, text=True).stdout
        )[0]["Config"]
        assert cfg["Labels"] == {"supervisely-sdk-version": "6.73.450"}
        assert "JINA_OPTOUT_TELEMETRY=1" in cfg["Env"]
    finally:
        subprocess.run(["docker", "image", "rm", "-f", tag], capture_output=True)
