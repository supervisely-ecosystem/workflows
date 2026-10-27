"""Rebuilt images of the same SDK get a suffixed tag (6.74.34-1); see PROPOSALS.md item 5 and audit L-4."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_sdk_version import VERSIONS  # noqa: F401  (same versions.json stub)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "resolve_release_tag.py"


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("6.74.34", "6.74.34"),
        ("6.74.34-1", "6.74.34"),
        ("6.74.34-rc.2", "6.74.34"),
        ("v6.73.10", "6.73.10"),
        ("test-d65a8bc", None),
        ("latest", None),
        ("6.74", None),
    ],
)
def test_sdk_version_from_image_tag(release_module, tag, expected):
    assert release_module.sdk_version_from_image_tag(tag) == expected


@pytest.mark.parametrize(
    "docker_image",
    ["supervisely/x:6.73.250-1", "supervisely/base-py-sdk:6.73.250-1"],
)
def test_suffixed_image_tag_passes_the_sdk_gate(release_module, make_repo, monkeypatch, capsys, docker_image):
    """Before: 6.73.250-1 became 6.73.2501 (caller image) or crashed int('250-1') (standard image)."""
    make_repo({"config.json": {"name": "x", "docker_image": docker_image, "instance_version": "6.12.5"}})
    monkeypatch.setattr(release_module, "fetch_versions_json", lambda token=None: VERSIONS)
    monkeypatch.setattr(release_module, "fetch_docker_images", lambda token=None: ["base-py-sdk"])
    monkeypatch.setattr(release_module, "fetch_release_description", lambda *a: "")
    release_module.validate_instance_version("tok", [None], "org/x", "v1.0.0")
    assert "SDK version to check: 6.73.250" in capsys.readouterr().out


def _resolve(tmp_path, docker_image, *args):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"docker_image": docker_image}))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--config", str(config), "--requirements", str(tmp_path / "none.txt"), *args],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    return result.returncode, result.stdout.strip()


@pytest.mark.parametrize(
    "docker_image,args,expected",
    [
        ("supervisely/x:6.74.34", [], "6.74.34"),
        ("supervisely/x:6.74.034", [], "6.74.34"),
        ("supervisely/x:6.74.34-1", [], "6.74.34-1"),
        ("supervisely/x:6.74.34-1", ["--strip-suffix"], "6.74.34"),
        ("supervisely/x:6.74.34", ["--strip-suffix"], "6.74.34"),
    ],
)
def test_resolve_release_tag_keeps_or_strips_the_suffix(tmp_path, docker_image, args, expected):
    """Before: int('34-1') raised, the script fell back to requirements and failed."""
    assert _resolve(tmp_path, docker_image, *args) == (0, expected)


def test_resolve_release_tag_rejects_non_version_tags(tmp_path):
    code, _ = _resolve(tmp_path, "supervisely/x:test-d65a8bc")
    assert code == 1


def test_builder_strips_the_suffix_for_the_base_image():
    text = (ROOT / ".github" / "workflows" / "build_image_from_template.yml").read_text()
    ref_call = text.split("TAG_REF_NAME=$(python3 workflow/scripts/resolve_release_tag.py", 1)[1].split(")", 1)[0]
    assert "--strip-suffix" in ref_call
