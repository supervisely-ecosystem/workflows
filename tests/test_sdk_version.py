"""SDK version discovery for the instance-compatibility gate (M-5)."""

import subprocess

import pytest

VERSIONS = {"6.10.0": "6.72.0", "6.12.0": "6.73.200", "6.14.0": "6.73.300"}


@pytest.fixture
def validate(release_module, make_repo, monkeypatch):
    """Run validate_instance_version for one root app with a custom image (no labels)."""

    def _run(body, docker_image="supervisely/custom-image:1.0.0", instance_version="6.11.8"):
        make_repo(
            {"config.json": {"name": "x", "docker_image": docker_image, "instance_version": instance_version}}
        )
        monkeypatch.setattr(release_module, "fetch_versions_json", lambda token=None: VERSIONS)
        monkeypatch.setattr(release_module, "fetch_docker_images", lambda token=None: ["base-py-sdk"])
        monkeypatch.setattr(release_module, "fetch_release_description", lambda *a: body)
        monkeypatch.setattr(
            release_module.subprocess,
            "run",
            lambda args, **kw: subprocess.CompletedProcess(args, 1, b"", b"no labels"),
        )
        return release_module.validate_instance_version("tok", [None], "org/x", "v1.0.0")

    return _run


@pytest.mark.parametrize(
    "body",
    [
        "Fixes\r\npython_sdk_version: 6.73.10\r\n- fixed X",  # A7: CRLF + more lines
        "python_sdk_version = 6.73.10",  # A8
        "python_sdk_version: v6.73.10\n",
        "python_sdk_version: 6.73.10",  # the documented form keeps working
    ],
)
def test_sdk_version_is_read_from_release_body(validate, body):
    validate(body)  # 6.73.10 is in [6.72.0, 6.73.200) for instance 6.11.8 -> no exception


def test_incompatible_sdk_version_in_body_is_rejected(validate):
    with pytest.raises(ValueError, match="incompatible"):
        validate("python_sdk_version: 6.73.250")


def test_missing_sdk_version_in_body_is_rejected(validate):
    with pytest.raises(RuntimeError, match="python_sdk_version not found"):
        validate("no version here")


def test_run_prints_the_cause_of_a_validation_error(release_module, make_repo, monkeypatch, capsys):
    """B4: the user saw only 'Error validating instance version'."""
    make_repo(
        {"config.json": {"name": "x", "docker_image": "supervisely/base-py-sdk:latest", "instance_version": "6.12.5"}}
    )
    monkeypatch.delenv("SKIP_INSTANCE_VERSION_VALIDATION", raising=False)
    monkeypatch.setattr(release_module, "validate_docker_image", lambda paths: None)
    monkeypatch.setattr(release_module, "fetch_release_description", lambda *a: "notes")
    monkeypatch.setattr(release_module, "fetch_versions_json", lambda token=None: VERSIONS)
    monkeypatch.setattr(release_module, "fetch_docker_images", lambda token=None: [])

    code = release_module.run(
        None, None, None, None, None, "org/x", ["__ROOT_APP__"], "t", "v1.0.0", "Title", "release"
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "Error validating instance version" in out
    assert "'latest'" in out
