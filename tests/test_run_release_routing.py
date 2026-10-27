"""run_release decides the target of every subapp before uploading anything (M-4)."""

import pytest

from conftest import FakeResponse


@pytest.fixture
def run_release(release_module, make_repo, monkeypatch):
    repo = make_repo(
        {
            "train/config.json": {"name": "train"},
            "serve/config.json": {"name": "serve"},
        }
    )
    monkeypatch.setattr(release_module, "get_appKey", lambda repo, subapp, url: subapp)
    # the app does not exist on dev yet -> do_release keeps share=True
    monkeypatch.setattr(release_module, "get_app_from_instance", lambda key, token, server: None)

    def _run(checks):
        uploads = []

        def fake_release(**kwargs):
            uploads.append((kwargs["subapp_path"], kwargs["server_address"], kwargs["share_app"]))
            return FakeResponse(200, {"success": True})

        monkeypatch.setattr(release_module, "release", fake_release)
        monkeypatch.setattr(
            release_module,
            "check_app_is_published",
            lambda prod_server_address, prod_api_token, app_key: checks[app_key],
        )
        code = release_module.run_release(
            "https://dev.example", "https://prod.example", "dev-t", "prod-t", repo,
            "https://github.com/org/x", "org/x", ["train", "serve"], "v2.0.0", "d",
        )
        return code, uploads

    return _run


def test_prod_check_failure_on_a_later_subapp_releases_nothing(run_release, capsys):
    """yolov8: train v2 reached prod while serve stayed on v1."""
    code, uploads = run_release({"train": (True, None), "serve": (None, "Connection Error")})
    assert code == 1
    assert uploads == []
    assert "Nothing was released" in capsys.readouterr().out


def test_routing_prod_and_dev(run_release, capsys):
    code, uploads = run_release({"train": (True, None), "serve": (False, None)})
    assert code == 0
    assert uploads == [
        ("train", "https://prod.example", False),
        ("serve", "https://dev.example", True),
    ]
    assert 'Subapp "serve" is not published on prod.example' in capsys.readouterr().out
