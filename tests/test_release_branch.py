"""run_release_branch error handling (M-2)."""

from conftest import FakeResponse


def test_prod_check_failure_reports_cause_and_continues(release_module, make_repo, monkeypatch, capsys):
    """D1: the first subapp's failed prod check raised UnboundLocalError(server_address)."""
    repo = make_repo({"config.json": {"name": "root"}, "train/config.json": {"name": "train"}})
    checks = {"root": (None, "Permission denied"), "train": (False, None)}
    monkeypatch.setattr(release_module, "get_appKey", lambda repo, subapp, url: subapp or "root")
    monkeypatch.setattr(
        release_module,
        "check_app_is_published",
        lambda prod_server_address, prod_api_token, app_key: checks[app_key],
    )
    uploads = []

    def fake_release(**kwargs):
        uploads.append(kwargs["subapp_path"])
        return FakeResponse(200, {"success": True})

    monkeypatch.setattr(release_module, "release", fake_release)

    code = release_module.run_release_branch(
        "https://dev.example", "https://prod.example", "t", "t", "t", repo,
        "https://github.com/org/x", "org/x", [None, "train"], "feature-x", "desc",
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "Permission denied" in out
    assert uploads == ["train"]
