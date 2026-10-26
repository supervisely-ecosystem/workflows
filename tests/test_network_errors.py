"""Network robustness and retry policy (M-3)."""

import pytest
import requests

from conftest import FakeResponse


def _raise(exc):
    def f(*args, **kwargs):
        raise exc

    return f


def test_requests_connection_error_on_prod_check_is_reported(release_module, monkeypatch):
    """D4: requests.ConnectionError is not a built-in ConnectionError and escaped."""
    monkeypatch.setattr(
        release_module,
        "get_app_from_instance",
        _raise(requests.exceptions.ConnectionError("Name or service not known")),
    )
    is_published, err = release_module.check_app_is_published("https://prod.example", "t", "k")
    assert is_published is None
    assert "Connection Error" in err and "Name or service not known" in err


def test_run_release_with_unreachable_prod_returns_1(release_module, make_repo, monkeypatch, capsys):
    """D5: a DNS blip on the prod check aborted the release with a traceback."""
    repo = make_repo({"config.json": {"name": "x"}, "serve/config.json": {"name": "s"}})
    monkeypatch.setattr(
        release_module, "get_app_from_instance", _raise(requests.exceptions.Timeout("read timeout"))
    )
    code = release_module.run_release(
        "https://dev.example", "https://prod.example", "t", "t", repo,
        "https://github.com/org/x", "org/x", [None, "serve"], "v1.0.0", "d",
    )
    assert code == 1
    assert "read timeout" in capsys.readouterr().out


@pytest.fixture
def retry_run(release_module, make_repo, monkeypatch):
    sleeps = []
    monkeypatch.setattr(release_module.time, "sleep", sleeps.append)

    def _run(files, release_side_effect):
        repo = make_repo(files)
        calls = []

        def fake_release(**kwargs):
            calls.append(1)
            return release_side_effect(len(calls))

        monkeypatch.setattr(release_module, "release", fake_release)
        result = release_module.do_release_with_retry(
            repo=repo, server_address="s", api_token="t", slug="org/x", subapp_path=None,
            release_version="v1.0.0", release_name="n", add_slug=True,
            repo_url="https://github.com/org/x", created_at=None, share=False,
        )
        return result, calls, sleeps

    return _run


def test_deterministic_error_is_not_retried(retry_run):
    """E3: a missing config.json was retried 3x with 15 s of sleep."""
    result, calls, sleeps = retry_run({"README.md": "x"}, lambda n: FakeResponse(200, {"success": True}))
    assert result["Status code"] is None
    assert "config.json" in result["Message"]
    assert sleeps == []


def test_http_429_is_retried(retry_run):
    responses = {1: FakeResponse(429, {"error": "slow down"}), 2: FakeResponse(200, {"success": True})}
    result, calls, sleeps = retry_run({"config.json": {"name": "x"}}, responses.get)
    assert len(calls) == 2
    assert result["Status code"] == 200


def test_network_exception_is_retried(retry_run):
    def side_effect(n):
        if n < 3:
            raise requests.exceptions.ConnectionError("reset by peer")
        return FakeResponse(200, {"success": True})

    result, calls, sleeps = retry_run({"config.json": {"name": "x"}}, side_effect)
    assert len(calls) == 3
    assert sleeps == [5, 10]
    assert result["Status code"] == 200


def test_4xx_is_not_retried(retry_run):
    result, calls, sleeps = retry_run(
        {"config.json": {"name": "x"}}, lambda n: FakeResponse(400, {"details": {"message": "bad config"}})
    )
    assert len(calls) == 1
    assert sleeps == []
