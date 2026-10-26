"""GitHub releases created without notes have body == None (M-1)."""

from types import SimpleNamespace

import pytest


@pytest.fixture
def github_release_body(release_module, monkeypatch):
    def _set(body):
        release = SimpleNamespace(body=body)
        repo = SimpleNamespace(get_release=lambda tag: release)
        monkeypatch.setattr(
            release_module, "Github", lambda *a, **k: SimpleNamespace(get_repo=lambda slug: repo)
        )

    return _set


def test_null_body_does_not_crash_validation_gate(release_module, github_release_body, monkeypatch):
    """export-to-coco v1.0.9-v1.1.4 and import-images v1.2.3 have "body": null."""
    monkeypatch.delenv("SKIP_INSTANCE_VERSION_VALIDATION", raising=False)
    github_release_body(None)
    assert release_module.need_validate_instance_version("release", "tok", "org/app", "v1.0.0") is True


def test_skip_marker_in_body_still_works(release_module, github_release_body, monkeypatch):
    monkeypatch.delenv("SKIP_INSTANCE_VERSION_VALIDATION", raising=False)
    github_release_body("notes\nskip_sdk_version_validation\n")
    assert release_module.need_validate_instance_version("release", "tok", "org/app", "v1.0.0") is False


def test_call_sites_tolerate_none_even_if_fetch_returns_it(release_module, monkeypatch):
    """Audit repro B3 patches fetch_release_description itself to return None."""
    monkeypatch.delenv("SKIP_INSTANCE_VERSION_VALIDATION", raising=False)
    monkeypatch.setattr(release_module, "fetch_release_description", lambda *a: None)
    assert release_module.need_validate_instance_version("release", "tok", "org/app", "v1.0.0") is True
