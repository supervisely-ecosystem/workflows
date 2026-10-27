"""release_models.py / update_models.py (M-12). HTTP is mocked; no server is contacted."""

import importlib
import json
import sys
from types import SimpleNamespace

import pytest

from conftest import FakeResponse

BASE_ENV = {
    "SUPERVISELY_PROD_SERVER_ADDRESS": "https://prod.example",
    "SUPERVISELY_PROD_API_TOKEN": "t",
    "FRAMEWORK": "YOLO",
    "MODELS_PATH": "",
    "DET_MODELS_PATH": "",
    "SEG_MODELS_PATH": "",
    "POSE_MODELS_PATH": "",
}


@pytest.fixture
def load(monkeypatch):
    def _load(name, **env):
        for k, v in {**BASE_ENV, **env}.items():
            monkeypatch.setenv(k, v)
        sys.modules.pop(name, None)
        return importlib.import_module(name)

    yield _load
    for name in ("release_models", "update_models"):
        sys.modules.pop(name, None)


def paged_get(entities, per_page=2):
    """Fake requests.get serving `entities` in pages; the page number is read from the body."""
    pages = [entities[i : i + per_page] for i in range(0, len(entities), per_page)] or [[]]

    def get(url, params=None, data=None, json=None, headers=None):
        page = (data or {}).get("page", 1)
        return FakeResponse(
            200,
            {"total": len(entities), "perPage": per_page, "pagesCount": len(pages), "entities": pages[page - 1]},
        )

    return get


@pytest.mark.parametrize("name", ["release_models", "update_models"])
def test_list_models_reads_all_pages(load, monkeypatch, name):
    """Pagination crashed with AttributeError: 'dict' object has no attribute 'json'."""
    mod = load(name)
    entities = [{"id": i, "name": f"m{i}", "framework": "YOLO"} for i in range(5)]
    monkeypatch.setattr(mod.requests, "get", paged_get(entities))
    result = mod.list_models() if name == "release_models" else mod.list_models("YOLO")
    assert [m["id"] for m in result] == [0, 1, 2, 3, 4]


def test_update_models_does_not_update_twice_when_seg_path_is_models_path(load, monkeypatch, tmp_path):
    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps([
            {"name": "YOLO-det-n", "task_type": "object detection"},
            {"name": "legacy-model"},
        ])
    )
    mod = load("update_models", MODELS_PATH=str(models_file), SEG_MODELS_PATH=str(models_file))
    existing = [
        {"id": 11, "name": "YOLO-det-n", "framework": "YOLO"},
        {"id": 12, "name": "legacy-model", "framework": "YOLO"},
    ]
    monkeypatch.setattr(mod.requests, "get", paged_get(existing, per_page=100))
    posts = []
    monkeypatch.setattr(
        mod.requests, "post", lambda url, **kw: posts.append(kw["json"]) or FakeResponse(200, {"success": True})
    )

    mod.main()

    assert sorted(p["id"] for p in posts) == [11, 12]
    by_id = {p["id"]: p for p in posts}
    assert by_id[11]["task"] == "object detection"
    assert "task" not in by_id[12]  # previously forced to "instance segmentation"


def test_release_models_does_not_add_twice_when_det_path_is_models_path(load, monkeypatch, tmp_path):
    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps([
            {"model_name": "YOLO-seg-n", "meta": {"task_type": "instance segmentation"}},
            {"model_name": "old-det"},
        ])
    )
    mod = load("release_models", MODELS_PATH=str(models_file), DET_MODELS_PATH=str(models_file))
    mod.api = SimpleNamespace(
        app=SimpleNamespace(
            get_list_ecosystem_modules=lambda **kw: [
                {"id": 1, "config": {"categories": ["serve"]}},
                {"id": 2, "config": {"categories": ["train"]}},
            ]
        )
    )
    monkeypatch.setattr(mod.requests, "get", paged_get([]))
    added = []
    monkeypatch.setattr(
        mod.requests,
        "post",
        lambda url, **kw: added.append(kw["json"]) or FakeResponse(200, {"id": len(added)}),
    )

    mod.main()

    assert sorted((a["name"], a["task"]) for a in added) == [
        ("YOLO-seg-n", "instance segmentation"),
        ("old-det", "object detection"),
    ]
