import subprocess

import pytest


def _skopeo(returncode):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, returncode, b"{}", b"manifest unknown")

    return calls, fake_run


@pytest.mark.parametrize("non_docker_type", ["project", "collection", "client_side_app"])
def test_non_docker_subapp_first_does_not_skip_later_subapps(
    release_module, make_repo, monkeypatch, non_docker_type
):
    """C-2: unet lists a collection root first; train/serve images were never checked."""
    make_repo(
        {
            "config.json": {"name": "root", "type": non_docker_type},
            "serve/config.json": {
                "name": "serve",
                "type": "app",
                "docker_image": "supervisely/does-not-exist:0.0.0",
            },
        }
    )
    calls, fake_run = _skopeo(returncode=1)
    monkeypatch.setattr(release_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="skopeo inspect failed"):
        release_module.validate_docker_image([None, "serve"])
    assert calls == [
        ["skopeo", "inspect", "docker://docker.io/supervisely/does-not-exist:0.0.0"]
    ]


def test_all_docker_subapps_are_inspected(release_module, make_repo, monkeypatch):
    make_repo(
        {
            "config.json": {"name": "root", "type": "collection"},
            "train/config.json": {"name": "t", "docker_image": "supervisely/unet:1.0.14"},
            "demo/config.json": {"name": "d", "type": "project"},
            "serve/config.json": {"name": "s", "docker_image": "supervisely/unet:1.0.14"},
        }
    )
    calls, fake_run = _skopeo(returncode=0)
    monkeypatch.setattr(release_module.subprocess, "run", fake_run)

    release_module.validate_docker_image([None, "train", "demo", "serve"])
    assert len(calls) == 2


def test_missing_docker_image_key_gives_clear_error(release_module, make_repo, monkeypatch):
    make_repo({"config.json": {"name": "root", "type": "app"}})
    calls, fake_run = _skopeo(returncode=0)
    monkeypatch.setattr(release_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="docker_image key not found"):
        release_module.validate_docker_image([None])
    assert calls == []
