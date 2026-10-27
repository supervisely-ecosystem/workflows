"""build_image_from_template.yml "Resolve requirements file" (M-8, local part)."""

import pytest

from workflow_runner import run_step

STEP = ("build_image_from_template.yml", "build-and-push", "Resolve requirements file")


def resolve(tmp_path, files, requested="dev_requirements.txt"):
    for name in files:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("six\n")
    proc, exported = run_step(*STEP, tmp_path, inputs={"requirements_file": requested})
    return proc, exported.get("REQUIREMENTS_FILE")


def test_default_input_uses_dev_requirements(tmp_path):
    proc, resolved = resolve(tmp_path, ["dev_requirements.txt"])
    assert proc.returncode == 0 and resolved == "dev_requirements.txt"


def test_default_input_keeps_legacy_root_requirements_precedence(tmp_path):
    proc, resolved = resolve(tmp_path, ["dev_requirements.txt", "requirements.txt"])
    assert proc.returncode == 0 and resolved == "requirements.txt"


def test_explicit_requirements_file_wins_over_root_requirements(tmp_path):
    """A multi-app repo passing serve/dev_requirements.txt got the root requirements.txt."""
    proc, resolved = resolve(
        tmp_path, ["serve/dev_requirements.txt", "requirements.txt"], requested="serve/dev_requirements.txt"
    )
    assert proc.returncode == 0 and resolved == "serve/dev_requirements.txt"


def test_no_requirements_file_builds_with_an_empty_one(tmp_path):
    """An app without any requirements file could not build, so it could not release."""
    proc, resolved = resolve(tmp_path, [])
    assert proc.returncode == 0, proc.stderr
    assert resolved == "sly_empty_requirements.txt"
    assert (tmp_path / resolved).read_text() == ""


def test_missing_explicit_file_still_fails(tmp_path):
    proc, resolved = resolve(tmp_path, [], requested="serve/dev_requirements.txt")
    assert proc.returncode == 1
    assert "serve/dev_requirements.txt" in proc.stderr
