import json
import os
import sys
from typing import List, Union

import dotenv
import requests
from supervisely.api.api import Api
from supervisely.api.module_api import ApiField

dotenv.load_dotenv(os.path.expanduser("~/supervisely.env"))

api = Api()
server_address = os.environ["SERVER_ADDRESS"]
api_token = os.environ["API_TOKEN"]
models_path = os.environ.get("MODELS_PATH", "")
det_models_path = os.environ.get("DET_MODELS_PATH", "")
seg_models_path = os.environ.get("SEG_MODELS_PATH", "")
pose_models_path = os.environ.get("POSE_MODELS_PATH", "")
framework = os.environ["FRAMEWORK"]


MODEL_KEY_MAPPING = {
    "Model": "name",
    "model_name": "name",
    "framework": "framework",
    ("meta", "task_type"): "task",
    "architecture": "architecture",
    "pretrained": "pretrained",
    "modality": "modality",
    "num_classes": "numClasses",
    "size": "size",
    "Params(M)": "paramsM",
    "Params (M)": "paramsM",
    "GFLOPs": "GFLOPs",
    "serve_module_id": "serveModuleId",
    "train_module_id": "trainModuleId",
    "tags": "tags",
    "runtimes": "runtimes",
    "files": "files",
    "speed_tests": "speedTests",
    "evaluation": "evaluation",
    "task": "task",
}


def get_value(data: dict, keys: Union[str, List[str]]):
    if isinstance(keys, str):
        return data.get(keys)
    else:
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value



def api_call(api_method, endpoint, params=None, data=None):
    call_function = requests.post if api_method == "post" else requests.get
    url = server_address.rstrip("/") + "/public/api/v3/" + endpoint.lstrip("/")
    headers = {
        "x-api-key": api_token,
    }
    r = call_function(url, params=params, data=data, headers=headers)
    try:
        r.raise_for_status()
    except Exception:
        print(f"Error calling API method {api_method} on endpoint {endpoint}")
        print(f"Response: {r.text}")
        raise
    return r.json()

def get(method, params=None, data=None):
    return api_call("get", method, params=params, data=data)

def post(method, params=None, data=None):
    return api_call("post", method, params=params, data=data)


def get_list_all_pages(method, data):
    if ApiField.SORT not in data:
        data[ApiField.SORT] = ApiField.ID
        data[ApiField.SORT_ORDER] = "asc"

    first_response = get(method, data=data)
    total = first_response["total"]
    per_page = first_response["perPage"]
    pages_count = first_response["pagesCount"]

    results = first_response["entities"]

    if pages_count == 1 and len(results) == total:
        pass
    else:
        for page_idx in range(2, pages_count + 1):
            temp_resp = get(method, {**data, "page": page_idx, "per_page": per_page})
            temp_items = temp_resp.json()["entities"]
            results.extend(temp_items)

        if len(results) != total:
            raise RuntimeError(
                "Method {!r}: error during pagination, some items are missed".format(method)
            )

    return results


def model_config_to_request(model_config: dict) -> dict:
    data = {}
    for k, api_k in MODEL_KEY_MAPPING.items():
        value = get_value(model_config, k)
        if value is not None:
            data[api_k] = value
    return data


def list_models():
    data = {
        "localModels": server_address != "https://app.supervisely.com",
    }
    return get_list_all_pages("ecosystem.models.list", data=data)


def add_model(parameters: dict):
    required_keys = ["name", "framework", "task"]
    defaults = {"modality": "image"}
    data = model_config_to_request(parameters)
    for key, value in defaults.items():
        if key not in data:
            data[key] = value
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys:
        raise ValueError(f"Missing required parameters: {missing_keys}")
    return post("ecosystem.models.add", data=data)


def update_model(model_id: int, parameters: dict):
    data = model_config_to_request(parameters)
    data["id"] = model_id
    return post(f"ecosystem.models.update", data=data)


def find_serve_and_train_modules():
    try:
        modules = api.app.get_list_ecosystem_modules(categories=[f"framework:{framework}"], categories_operation="and")
        serve_module = next((m for m in modules if "serve" in m["config"]["categories"]))
        train_module = next((m for m in modules if "train" in m["config"]["categories"]))
    except StopIteration:
        raise RuntimeError(f"Could not find serve or train modules for framework {framework}")
    return serve_module, train_module


def read_models():
    serve, train = find_serve_and_train_modules()
    models = []
    if models_path != "":
        models.extend(json.load(open(models_path, "r")))
    if det_models_path != "":
        det_models = json.load(open(det_models_path, "r"))
        for model in det_models:
            model["task"] = "object detection"
            models.append(model)
    if seg_models_path != "":
        print("Segmentation models are not supported yet.")
        # seg_models = json.load(open(seg_models_path, "r"))
        # for model in seg_models:
        #     model["task"] = "semantic_segmentation"
        #     models.append(model)
    if pose_models_path != "":
        print("Pose estimation models are not supported yet.")
        # pose_models = json.load(open(pose_models_path, "r"))
        # for model in pose_models:
        #     model["task"] = "pose_estimation"
        #     models.append(model)
    for model in models:
        model["framework"] = framework
        model["serve_module_id"] = serve["id"]
        model["train_module_id"] = train["id"]
    return models


def main():
    if models_path == "" or framework == "":
        print("Models path or framework is not set. Models will not be added.")
        sys.exit(0)
    try:
        models = read_models()
    except RuntimeError as e:
        if str(e).startswith("Could not find serve or train modules"):
            print(f"Error: {e}")
            print("Cannot find serve or train modules for the specified framework.")
            print("This may mean that the apps are not yet published")
            sys.exit(0)
    existing_models = list_models()
    existing_model_names = {model["name"] for model in existing_models}
    models_to_add = []
    models_to_add_names = []
    for model in models:
        model_name = get_value(model, "Model")
        if model_name not in existing_model_names:
            models_to_add.append(model)
            models_to_add_names.append(model_name)
    print()
    print("Existing models:", existing_model_names)
    if not models_to_add:
        print("No new models to add.")
        return
    print("Models to add:  ", models_to_add_names)
    print()

    success = True
    for model in models_to_add:
        try:
            response = add_model(model)
            print(f"Added model: {model['Model']} with ID {response['id']}")
        except Exception as e:
            success = False
            print(f"Failed to add model {model['Model']}: {e}")
    
    if success:
        print("All models added successfully.")
    else:
        print("Some models failed to add. Please check the logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
