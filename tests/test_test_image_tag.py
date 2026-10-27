"""templates/build_release_branch.yml: the test image tag follows the content (item 6 of PROPOSALS.md)."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = yaml.safe_load((ROOT / "templates" / "build_release_branch.yml").read_text())
SCRIPT = next(s["run"] for s in TEMPLATE["jobs"]["Test-Image-Tag"]["steps"] if s.get("id") == "tag")
FILES = TEMPLATE["env"]["TEST_IMAGE_FILES"]


def run_tag_step(repo: Path, docker_image: str, enabled: str = "true"):
    (repo / "config.json").write_text(json.dumps({"docker_image": docker_image}))
    output = repo / "github_output"
    output.write_text("")
    env = dict(
        os.environ,
        BUILD_TEST_IMAGE_ON_RELEASE=enabled,
        TEST_IMAGE_FILES=FILES,
        GITHUB_REPOSITORY="supervisely-ecosystem/Import-COCO",
        GITHUB_OUTPUT=str(output),
    )
    result = subprocess.run(["bash", "-e", "-c", SCRIPT], cwd=repo, env=env, capture_output=True, text=True)
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
    return result, outputs


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "dev_requirements.txt").write_text("supervisely==6.74.46\n")
    return tmp_path


def expected_tag(*contents: bytes) -> str:
    return "test-" + hashlib.sha256(b"".join(contents)).hexdigest()[:8]


def test_matching_test_tag_builds(repo):
    tag = expected_tag(b"supervisely==6.74.46\n")
    result, out = run_tag_step(repo, f"supervisely/import-coco:{tag}")
    assert result.returncode == 0, result.stderr
    assert out == {"enabled": "true", "tag": tag, "build": "true"}


def test_old_mutable_test_tag_fails_with_the_value_to_set(repo):
    tag = expected_tag(b"supervisely==6.74.46\n")
    result, out = run_tag_step(repo, "supervisely/import-coco:test")
    assert result.returncode == 1
    assert f'"supervisely/import-coco:{tag}"' in result.stdout
    assert "build" not in out


def test_tag_changes_with_any_listed_file(repo):
    before = expected_tag(b"supervisely==6.74.46\n")
    (repo / "docker" / "hardened").mkdir(parents=True)
    (repo / "docker" / "hardened" / "Dockerfile.tmpl").write_text("FROM x\n")
    result, out = run_tag_step(repo, f"supervisely/import-coco:{before}")
    assert result.returncode == 1
    assert out["tag"] == expected_tag(b"supervisely==6.74.46\n", b"FROM x\n") != before


def test_release_image_is_not_built(repo):
    result, out = run_tag_step(repo, "supervisely/import-coco:6.74.46")
    assert result.returncode == 0
    assert out["build"] == "false"


def test_disabled(repo):
    result, out = run_tag_step(repo, "supervisely/import-coco:test", enabled="false")
    assert result.returncode == 0
    assert out == {"enabled": "false"}
