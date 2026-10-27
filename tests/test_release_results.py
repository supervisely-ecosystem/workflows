"""How release.py interprets the server's answer to an upload (H-4)."""

import pytest

from conftest import FakeResponse


@pytest.fixture
def release_with(release_module, make_repo, monkeypatch):
    make_repo({"config.json": {"name": "x", "docker_image": "supervisely/base-py-sdk:6.73.410"}})
    monkeypatch.setattr(release_module.time, "sleep", lambda s: None)

    def _run(*responses):
        queue = list(responses)
        uploads = []

        def fake_release(**kwargs):
            uploads.append(kwargs)
            item = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(item, BaseException):
                raise item
            return item

        monkeypatch.setattr(release_module, "release", fake_release)
        import git

        result = release_module.do_release_with_retry(
            repo=git.Repo("."),
            server_address="https://dev.example",
            api_token="t",
            slug="org/x",
            subapp_path=None,
            release_version="v1.0.0",
            release_name="n",
            add_slug=True,
            repo_url="https://github.com/org/x",
            created_at=None,
            share=False,
        )
        return result, uploads

    return _run


def test_http_200_with_success_true_is_success(release_module, release_with):
    result, _ = release_with(FakeResponse(200, {"success": True}))
    assert release_module.print_results([result]) is True


def test_http_200_with_success_false_is_failure(release_module, release_with):
    """E1: the SDK CLI treats this as a failed release; release.py printed [OK]."""
    result, _ = release_with(
        FakeResponse(200, {"success": False, "details": {"message": "archive is invalid"}})
    )
    assert release_module.print_results([result]) is False


def test_http_200_without_json_body_is_failure(release_module, release_with):
    result, _ = release_with(FakeResponse(200, None, text="<html>proxy</html>"))
    assert "proxy" in result["Message"]
    assert release_module.print_results([result]) is False


def test_unrelated_already_exists_is_not_skipped(release_module, release_with):
    """E2: a slug clash used to be reported as [Skipped: already released] and green."""
    result, _ = release_with(
        FakeResponse(400, {"details": {"message": "module with this slug already exists in another team"}})
    )
    assert not result.get("Skipped")
    assert release_module.print_results([result]) is False


@pytest.mark.parametrize(
    "message",
    [
        "version v1.0.0 already exists",
        "Version 'v1.0.0' already exists",
        "release v1.0.0 already released",
    ],
)
def test_duplicate_version_is_skipped_as_success(release_module, release_with, message):
    result, uploads = release_with(FakeResponse(400, {"details": {"message": message}}))
    assert result["Skipped"] is True
    assert release_module.print_results([result]) is True
    assert len(uploads) == 1


def test_exception_text_mentioning_already_exists_is_not_a_duplicate(release_module):
    result = {"Status code": None, "Message": "version v1 already exists", "Success": False}
    assert release_module.is_already_released(result) is False
