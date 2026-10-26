"""publish(): exit code must reflect what reached production (H-3)."""

from types import SimpleNamespace

import pytest

from conftest import FakeResponse

OK = FakeResponse(200, {"success": True})
FAIL = FakeResponse(400, {"details": {"message": "archive is invalid"}})


@pytest.fixture
def setup(release_module, make_repo, monkeypatch):
    repo = make_repo({"config.json": {"name": "x"}, "serve/config.json": {"name": "s"}})
    repo.create_tag("v1.0.0")
    repo.create_tag("v1.1.0")
    gh_releases = [
        SimpleNamespace(tag_name="v1.0.0", title="first"),
        SimpleNamespace(tag_name="v1.1.0", title="second"),
    ]
    monkeypatch.setattr(release_module.time, "sleep", lambda s: None)

    def run(published, responses, subapps=(None,), err=None, releases=gh_releases):
        uploads = []
        queue = list(responses)

        def fake_release(**kwargs):
            uploads.append((kwargs["subapp_path"], kwargs["release_version"]))
            return queue.pop(0)

        monkeypatch.setattr(release_module, "release", fake_release)
        monkeypatch.setattr(
            release_module,
            "check_app_is_published",
            lambda prod_server_address, prod_api_token, app_key: (
                (None, err) if err else (published[app_key], None)
            ),
        )
        monkeypatch.setattr(
            release_module, "get_appKey", lambda repo, subapp, url: subapp or "root"
        )
        code = release_module.publish(
            "https://prod.example", "t", repo, "https://github.com/org/x", "org/x",
            list(subapps), releases,
        )
        return code, uploads

    return run


def test_all_releases_uploaded_exits_0(setup):
    code, uploads = setup({"root": False}, [OK, OK])
    assert code == 0
    assert uploads == [(None, "v1.0.0"), (None, "v1.1.0")]


def test_prod_unreachable_exits_1(setup):
    """D2: 'Could not access prod. Permission denied.' printed [Fail] but exited 0."""
    code, uploads = setup({}, [], err='Could not access "prod". Permission denied.')
    assert code == 1
    assert uploads == []


def test_already_published_only_app_exits_1(setup):
    """D3: publishing an app that is already on prod did nothing and exited 0."""
    code, uploads = setup({"root": True}, [])
    assert code == 1
    assert uploads == []


def test_one_of_two_releases_failing_exits_1(setup):
    """Previously one successful upload was enough for a green run."""
    code, _ = setup({"root": False}, [OK, FAIL])
    assert code == 1


def test_already_published_subapp_is_skipped_when_another_is_published(setup):
    code, uploads = setup({"root": True, "serve": False}, [OK, OK], subapps=(None, "serve"))
    assert code == 0
    assert uploads == [("serve", "v1.0.0"), ("serve", "v1.1.0")]


def test_transient_5xx_is_retried(setup):
    code, uploads = setup({"root": False}, [FakeResponse(503, {"error": "busy"}), OK, OK])
    assert code == 0
    assert len(uploads) == 3


def test_no_github_releases_exits_1(setup):
    code, uploads = setup({"root": False}, [], releases=[])
    assert code == 1
    assert uploads == []
