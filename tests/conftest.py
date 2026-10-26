"""Shared fixtures for the offline test-suite.

Nothing here talks to a network: the Supervisely SDK helpers that release.py
imports are replaced by stubs (unless the real SDK is installed, in which case
the tests still mock every function that would do I/O), and GitHub / HTTP calls
are patched in each test.
"""

import contextlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_supervisely_stub():
    try:
        import supervisely.cli.release.release  # noqa: F401
        import supervisely.io.fs  # noqa: F401
        import supervisely.api.api  # noqa: F401
        import supervisely.api.module_api  # noqa: F401

        return
    except ImportError:
        pass

    def module(name):
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod

    def not_mocked(*args, **kwargs):
        raise AssertionError("SDK network helper called without a mock")

    @contextlib.contextmanager
    def cd(new_path=None, add_to_path=False):
        old = os.getcwd()
        if new_path is not None:
            os.chdir(new_path)
        try:
            yield
        finally:
            os.chdir(old)

    def get_appKey(repo, sub_app_path, repo_url):
        return f"key:{repo_url}:{sub_app_path}"

    module("supervisely")
    module("supervisely.cli")
    module("supervisely.cli.release")
    rel = module("supervisely.cli.release.release")
    rel.cd = cd
    rel.delete_directory = lambda path: None
    rel.get_app_from_instance = not_mocked
    rel.get_appKey = get_appKey
    rel.get_created_at = lambda repo, tag: None
    rel.upload_archive = not_mocked

    module("supervisely.io")
    fs = module("supervisely.io.fs")
    fs.dir_exists = os.path.isdir
    fs.list_files_recursively = lambda d, *a, **k: [
        os.path.join(r, f) for r, _, files in os.walk(d) for f in files
    ]
    fs.remove_dir = lambda d: None

    module("supervisely.api")
    api_mod = module("supervisely.api.api")

    class Api:
        def __init__(self, server_address, token):
            self.app = types.SimpleNamespace(get_list_ecosystem_modules=not_mocked)

    api_mod.Api = Api
    module_api = module("supervisely.api.module_api")

    class ApiField:
        ID = "id"
        SORT = "sort"
        SORT_ORDER = "sort_order"

    module_api.ApiField = ApiField


_install_supervisely_stub()


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code, body=None, text=None):
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("No JSON object could be decoded")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code}")


@pytest.fixture
def make_repo(tmp_path, monkeypatch):
    """Create a git repo with the given files, chdir into it, return git.Repo."""
    import git

    def _make(files):
        repo_dir = tmp_path / "app"
        repo_dir.mkdir()
        for rel, content in files.items():
            p = repo_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content if isinstance(content, str) else json.dumps(content))
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True, env=env)
        subprocess.run(
            ["git", "commit", "-q", "-m", "init"], cwd=repo_dir, check=True, env=env
        )
        monkeypatch.chdir(repo_dir)
        return git.Repo(repo_dir)

    return _make


@pytest.fixture
def release_module():
    import release

    return release
