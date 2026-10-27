"""docker/hardened/Dockerfile.tmpl must not leave pip in the image (M-7).

These tests do real `docker build`s (Debian packages and PyPI wheels are
downloaded, nothing is pushed). They are skipped unless RUN_DOCKER_TESTS=1.
A stand-in for supervisely/base-py-sdk-hardened is built locally from
python:3.14-slim-bookworm with a pip-less venv in /opt/venv, tagged
supervisely/sly-workflows-test-base:local and removed afterwards.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docker" / "hardened" / "Dockerfile.tmpl"
BASE = "supervisely/sly-workflows-test-base"
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DOCKER_TESTS") != "1" or shutil.which("docker") is None,
    reason="set RUN_DOCKER_TESTS=1 (needs docker and network) to run",
)


def docker(*args, cwd=None):
    return subprocess.run(["docker", *args], cwd=cwd, capture_output=True, text=True)


@pytest.fixture(scope="module")
def base_image(tmp_path_factory):
    d = tmp_path_factory.mktemp("base")
    (d / "Dockerfile").write_text(
        "FROM python:3.14-slim-bookworm\n"
        "RUN python -m venv --without-pip /opt/venv\n"
    )
    r = docker("build", "-q", "-t", f"{BASE}:local", ".", cwd=d)
    assert r.returncode == 0, r.stderr
    yield f"{BASE}:local"
    docker("image", "rm", "-f", f"{BASE}:local")


def build_app(tmp_path, requirements):
    (tmp_path / "dev_requirements.txt").write_text(requirements)
    shutil.copy(TEMPLATE, tmp_path / "Dockerfile.tmpl")
    tag = f"sly-workflows-test/app:{tmp_path.name.lower()}"
    r = docker(
        "build", "-q", "-f", "Dockerfile.tmpl",
        "--build-arg", "RUNTIME_BASE_IMAGE=sly-workflows-test-base",
        "--build-arg", "tag_ref_name=local",
        "-t", tag, ".", cwd=tmp_path,
    )
    assert r.returncode == 0, r.stderr
    return tag


def run_in(tag, script):
    return docker("run", "--rm", "--entrypoint", "sh", tag, "-c", script)


PIP_PRESENT = "ls /opt/venv/bin/pip* /opt/venv/lib/python*/site-packages/pip* 2>/dev/null | wc -l"


def test_comment_only_requirements_leave_no_pip(base_image, tmp_path):
    """export-to-coco:6.74.34 shipped pip 26.2.1 in its top layer."""
    tag = build_app(tmp_path, "# supervisely==6.73.542\n")
    try:
        assert run_in(tag, PIP_PRESENT).stdout.strip() == "0"
    finally:
        docker("image", "rm", "-f", tag)


def test_real_requirements_installed_and_pip_removed(base_image, tmp_path):
    tag = build_app(tmp_path, "six==1.16.0\n")
    try:
        assert run_in(tag, "/opt/venv/bin/python -c 'import six; print(six.__version__)'").stdout.strip() == "1.16.0"
        assert run_in(tag, PIP_PRESENT).stdout.strip() == "0"
    finally:
        docker("image", "rm", "-f", tag)


def test_empty_requirements_file_builds(base_image, tmp_path):
    """The workflow now substitutes an empty file when an app has no requirements file."""
    tag = build_app(tmp_path, "")
    try:
        assert run_in(tag, PIP_PRESENT).stdout.strip() == "0"
    finally:
        docker("image", "rm", "-f", tag)
