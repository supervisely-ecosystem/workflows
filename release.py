import datetime
import json
import os
import random
import re
import string
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Dict, List, Literal

import git
from github import ContentFile, Github, GithubException, GitRelease
from supervisely.cli.release.release import (cd, delete_directory,
                                             get_app_from_instance, get_appKey,
                                             get_created_at, upload_archive)
from supervisely.io.fs import dir_exists, list_files_recursively, remove_dir


class ReleaseType:
    RELEASE = "release"
    RELEASE_BRANCH = "release-branch"
    PUBLISH = "publish"


def version_tuple(version: str):
    return tuple(map(int, version.lstrip("v").split(".")))


def compare_semver(version1: str, version2: str):
    if version_tuple(version1) > version_tuple(version2):
        return 1
    if version_tuple(version1) < version_tuple(version2):
        return -1
    return 0


def is_valid_version(version: str):
    return re.fullmatch("v\d+\.\d+\.\d+", version) != None


def gh_release_is_published(release: GitRelease.GitRelease):
    return not (release.prerelease or release.draft)


def get_config(app_path):
    app_path = Path(os.getcwd()) if app_path is None else Path(app_path)
    with open(app_path.joinpath("config.json"), "r") as f:
        config = json.load(f)
    return config


def get_readme(app_path):
    app_path = Path(os.getcwd()) if app_path is None else Path(app_path)
    try:
        with open(app_path.joinpath("README.md"), "r", encoding="utf_8") as f:
            readme = f.read()
        return readme
    except:
        return ""


def get_modal_template(config):
    modal_template = ""
    if "modal_template" in config:
        if config["modal_template"] != "":
            modal_template_path = Path(config["modal_template"])
            if not modal_template_path.exists() or not modal_template_path.is_file():
                raise FileNotFoundError(f"FileNotFoundError: {modal_template_path}")
            with open(modal_template_path, "r") as f:
                modal_template = f.read()
    return modal_template


def get_app_name(config: dict):
    app_name = config.get("name", None)
    return app_name


def parse_subapp_paths(subapps_paths: str) -> List[str]:
    return [p.strip(" ").strip("/") for p in subapps_paths.split(",")]


def remove_scheme(server_address):
    if server_address.startswith("http://"):
        return server_address[len("http://") :]
    if server_address.startswith("https://"):
        return server_address[len("https://") :]
    return server_address


def print_results(results):
    success_count = sum(1 for res in results if res["Status code"] == 200)
    print(f"Total: {len(results)} releases. Success: {success_count}/{len(results)}")
    if success_count != len(results):
        print("Results:")
        print(
            f'{"Result".ljust(10)}{"Release".ljust(30)}{"App name".ljust(20)}{"App path".ljust(20)}{"Status code".ljust(15)}Message'
        )
        for result in results:
            success = "[OK]" if result["Status code"] == 200 else "[FAIL]"
            app_path = result["App path"]
            if app_path is None:
                app_path = "__ROOT_APP__"
            line = (
                success.ljust(10)
                + f'{str(result["Release"]).ljust(28)[:28]}  '
                + f'{str(result["App name"]).ljust(18)[:18]}  '
                + f'{str(result["App path"]).ljust(18)[:18]}  '
                + str(result["Status code"]).ljust(15)
                + str(result["Message"])
            )
            print(line)
    print()
    return success_count == len(results)

def archive_application(repo: git.Repo, config, slug, archive_only_config=False):
    archive_folder = "".join(random.choice(string.ascii_letters) for _ in range(5))
    os.mkdir(archive_folder)
    file_paths = [
        Path(line.decode("utf-8")).absolute()
        for line in subprocess.check_output(
            "git ls-files --recurse-submodules", shell=True
        ).splitlines()
    ]
    if slug is None:
        app_folder_name = config["name"].lower()
    else:
        app_folder_name = slug.split("/")[1].lower()
    app_folder_name = re.sub("[ \/]", "-", app_folder_name)
    app_folder_name = re.sub("[\"'`,\[\]\(\)]", "", app_folder_name)
    working_dir_path = Path(repo.working_dir).absolute()
    should_remove_dir = None
    if config.get("type", "app") == "client_side_app":
        gui_folder_path = config["gui_folder_path"]
        gui_folder_path = working_dir_path / gui_folder_path
        if not dir_exists(gui_folder_path):
            should_remove_dir = gui_folder_path
            # if gui folder is empty, need to render it
            with cd(str(working_dir_path), add_to_path=True):
                exec(open("sly_sdk/render.py", "r").read(), {"__name__": "__main__"})
                file_paths.extend(
                    [Path(p).absolute() for p in list_files_recursively(str(gui_folder_path))]
                )
        archive_path = archive_folder + "/archive.tar"
        write_mode = "w"
    else:
        archive_path = archive_folder + "/archive.tar.gz"
        write_mode = "w:gz"
    if archive_only_config:
        file_paths = [p for p in file_paths if "config.json" in p.name]
    with tarfile.open(archive_path, write_mode) as tar:
        for path in file_paths:
            if path.is_file():
                tar.add(
                    path.absolute(),
                    Path(app_folder_name).joinpath(path.relative_to(working_dir_path)),
                )
    if should_remove_dir is not None:
        # remove gui folder if it was rendered
        remove_dir(should_remove_dir)
    return archive_path


def release(
    server_address,
    api_token,
    appKey,
    repo: git.Repo,
    config,
    readme,
    release_name,
    release_version,
    modal_template="",
    slug=None,
    user_id=None,
    subapp_path="",
    created_at=None,
    share_app=False,
    archive_only_config=False,
):
    if created_at is None:
        created_at = get_created_at(repo, release_version)
    archive_path = archive_application(repo, config, slug, archive_only_config)
    release = {
        "name": release_name,
        "version": release_version,
    }
    if created_at is not None:
        release["createdAt"] = created_at
    try:
        response = upload_archive(
            archive_path,
            server_address,
            api_token,
            appKey,
            release,
            config,
            readme,
            modal_template,
            slug,
            user_id,
            subapp_path,
            share_app,
        )
    finally:
        delete_directory(os.path.dirname(archive_path))
    return response


def do_release(
    repo,
    server_address,
    api_token,
    slug,
    subapp_path,
    release_version,
    release_name,
    add_slug,
    repo_url,
    created_at,
    share,
    archive_only_config=False
):
    app_name = "Unknown"
    try:
        appKey = get_appKey(repo, subapp_path, repo_url)
        config = get_config(subapp_path)
        readme = get_readme(subapp_path)
        modal_template = get_modal_template(config)
        app_name = get_app_name(config)

        if share:
            try:
                app = get_app_from_instance(appKey, api_token, server_address)
                share = app is None
            except:
                share = False

        response = release(
            server_address=server_address,
            api_token=api_token,
            appKey=appKey,
            repo=repo,
            config=config,
            readme=readme,
            release_version=release_version,
            release_name=release_name,
            modal_template=modal_template,
            slug=slug if add_slug else None,
            created_at=created_at,
            subapp_path=subapp_path,
            share_app=share,
            archive_only_config=archive_only_config
        )

        return {
            "App name": app_name,
            "App path": subapp_path,
            "Release": f"{release_version} ({release_name})",
            "Status code": response.status_code,
            "Message": response.json(),
        }

    except Exception as e:
        return {
            "App name": app_name,
            "App path": subapp_path,
            "Release": f"{release_version} ({release_name})",
            "Status code": None,
            "Message": str(e),
        }


def check_app_is_published(
    prod_server_address: str,
    prod_api_token: str,
    app_key: str,
):
    if prod_server_address is None:
        err_msg = "Prod server address is not set, cannot check if app is released."
        return None, err_msg
    if prod_api_token is None:
        err_msg = "Prod api token is not set, cannot check if app is released."
        return None, err_msg
    try:
        prod_app = get_app_from_instance(app_key, prod_api_token, prod_server_address)
    except PermissionError:
        err_msg = f'Could not access "{prod_server_address}". Permission denied.'
        return None, err_msg
    except ConnectionError:
        err_msg = f'Could not access "{prod_server_address}". Connection Error.'
        return None, err_msg
    return prod_app is not None, None


def add_tag(repo: git.Repo, tag_name: str, tag_message: str, commit_sha):
    if tag_name in repo.tags:
        print("Tag already exists")
        return False
    subprocess.run(["git", "config", "user.name", '"${GITHUB_ACTOR}"'])
    subprocess.run(
        ["git", "config", "user.email", '${GITHUB_ACTOR}@users.noreply.github.com"']
    )
    repo.create_tag(tag_name, message=tag_message, ref=commit_sha)
    repo.git.push("origin", tag_name)
    return True


def get_GitHub_releases(
    github_access_token: str, slug: str, include_sly_releases: bool = False
):
    def is_valid(tag_name: str, include_sly_releases: bool = False):
        if include_sly_releases:
            if tag_name.startswith("sly-release-"):
                tag_name = tag_name[len("sly-release-") :]
        return is_valid_version(tag_name)

    GH = Github(github_access_token)
    gh_repo = GH.get_repo(slug)
    gh_releases = [
        r
        for r in gh_repo.get_releases()
        if is_valid(r.tag_name, include_sly_releases) and gh_release_is_published(r)
    ]
    gh_releases.reverse()
    return gh_releases


def run_release(
    dev_server_address: str,
    prod_server_address: str,
    private_dev_api_token: str,
    prod_api_token: str,
    repo: git.Repo,
    repo_url: str,
    slug: str,
    subapp_paths: List[str],
    release_version: str,
    release_description: str,
    archive_only_config = False
):
    if not is_valid_version(release_version):
        print("Release version is not valid. Should be in semver format (v1.2.3).")
        return 1

    results = []
    for subapp_path in subapp_paths:
        app_key = get_appKey(repo, subapp_path, repo_url)
        is_published, err_msg = check_app_is_published(
            prod_server_address=prod_server_address,
            prod_api_token=prod_api_token,
            app_key=app_key,
        )
        if err_msg is None:
            if is_published:
                server_address = prod_server_address
                api_token = prod_api_token
                share = False
            else:
                server_address = dev_server_address
                api_token = private_dev_api_token
                share = True
            if subapp_path is None:
                print(
                    f"Releasing root app to {remove_scheme(server_address)}...".ljust(
                        53
                    ),
                    end=" ",
                )
            else:
                print(
                    (
                        f'Releasing subapp at "{subapp_path}" to {remove_scheme(server_address)}'[
                            :50
                        ]
                        + "..."
                    ).ljust(53),
                    end=" ",
                )
            results.append(
                do_release(
                    repo=repo,
                    server_address=server_address,
                    api_token=api_token,
                    slug=slug,
                    subapp_path=subapp_path,
                    release_version=release_version,
                    release_name=release_description,
                    add_slug=True,
                    repo_url=repo_url,
                    created_at=None,
                    share=share,
                    archive_only_config=archive_only_config
                )
            )
            if results[-1]["Status code"] == 200:
                print("  [OK]\n")
                # maybe add sly-release-tag
                # if not is_published:
                #     try:
                #         tag_name = "sly-release-" + release_version
                #         created = add_tag(
                #             repo=repo,
                #             tag_name=tag_name,
                #             tag_message=release_description,
                #             commit_sha=repo.git.rev_parse("HEAD", short=True),
                #         )
                #         if created:
                #             print("Created tag: ", tag_name)
                #     except:
                #         print(
                #             f'!!! Could not create tag "{tag_name}" Please add this tag manaully to avoid errors in future.'
                #         )
            else:
                print("[Fail]\n")
        else:
            if subapp_path is None:
                print(
                    "Releasing root app Failed...".ljust(
                        53
                    ),
                    end=" ",
                )
            else:
                print(
                    (
                        f'Releasing subapp at "{subapp_path}" Failed'[
                            :50
                        ]
                        + "..."
                    ).ljust(53),
                    end=" ",
                )
            print("[Fail]\n")
            try:
                config = get_config(subapp_path)
                app_name = get_app_name(config)
            except:
                app_name = "Unknown"
            results.append(
                {
                    "App name": app_name,
                    "App path": subapp_path,
                    "Release": f"{release_version} ({release_description})",
                    "Status code": None,
                    "Message": err_msg,
                }
            )
    return 0 if print_results(results) else 1


def run_release_branch(
    dev_server_address: str,
    prod_server_address: str,
    dev_api_token: str,
    private_dev_api_token: str,
    prod_api_token: str,
    repo: git.Repo,
    repo_url: str,
    slug: str,
    subapp_paths: List[str],
    release_version: str,
    release_description: str,
    archive_only_config = False,
):
    if is_valid_version(release_version):
        print("Branch name is not valid. Should not be in semver format (v1.2.3).")
        return 1
    if release_version in ["master", "main"]:
        print('Branch name should not be "master" or "main".')
        return 1
    timestamp = repo.head.commit.committed_date
    created_at = datetime.datetime.utcfromtimestamp(timestamp).isoformat()
    results = []
    for subapp_path in subapp_paths:
        app_key = get_appKey(repo, subapp_path, repo_url)
        is_published, err_msg = check_app_is_published(
            prod_server_address=prod_server_address,
            prod_api_token=prod_api_token,
            app_key=app_key,
        )
        if err_msg is None:
            if is_published:
                server_address = dev_server_address
                api_token = dev_api_token
                share = False
            else:
                server_address = dev_server_address
                api_token = private_dev_api_token
                share = True
            if subapp_path is None:
                print(
                    f"Releasing root app to {remove_scheme(server_address)}...".ljust(
                        53
                    ),
                    end=" ",
                )
            else:
                print(
                    (
                        f'Releasing subapp at "{subapp_path}" to {remove_scheme(server_address)}'[
                            :50
                        ]
                        + "..."
                    ).ljust(53),
                    end=" ",
                )
            results.append(
                do_release(
                    repo=repo,
                    server_address=server_address,
                    api_token=api_token,
                    slug=slug,
                    subapp_path=subapp_path,
                    release_version=release_version,
                    release_name=release_description,
                    add_slug=True,
                    repo_url=repo_url,
                    created_at=created_at,
                    share=share,
                    archive_only_config=archive_only_config,
                )
            )
            if results[-1]["Status code"] == 200:
                print("  [OK]\n")
            else:
                print("[Fail]\n")

        else:
            if subapp_path is None:
                print(f"Releasing root app to {server_address}...".ljust(53), end=" ")
            else:
                print(
                    (
                        f'Releasing subapp at "{subapp_path}" to {server_address}'[:50]
                        + "..."
                    ).ljust(53),
                    end=" ",
                )
            print("[Fail]\n")
            try:
                config = get_config(subapp_path)
                app_name = get_app_name(config)
            except:
                app_name = "Unknown"
            results.append(
                {
                    "App name": app_name,
                    "App path": subapp_path,
                    "Release": f"{release_version} ({release_description})",
                    "Status code": None,
                    "Message": err_msg,
                }
            )
    return 0 if print_results(results) else 1


def publish(
    prod_server_address: str,
    prod_api_token: str,
    repo: git.Repo,
    repo_url: str,
    slug: str,
    subapp_paths: List[str],
    gh_releases: List[GitRelease.GitRelease],
    archive_only_config=False,
):
    """
    Creates a release for every release in the repository.
    """
    all_success = True
    for subapp_path in subapp_paths:
        app_key = get_appKey(repo, subapp_path, repo_url)

        if subapp_path is None:
            print("Publishing root app...".ljust(53), end=" ")
        else:
            print(
                (f'Publishing subapp at "{subapp_path}"'[:50] + "...").ljust(53),
                end=" ",
            )

        is_published, err_msg = check_app_is_published(
            prod_server_address=prod_server_address,
            prod_api_token=prod_api_token,
            app_key=app_key,
        )
        if err_msg is not None or is_published:
            print("[Fail]\n")
            try:
                config = get_config(subapp_path)
                app_name = get_app_name(config)
            except:
                app_name = "Unknown"
            message = "App is already published to production. This action only works for apps that are not published to production."
            print_results(
                [
                    {
                        "App name": app_name,
                        "App path": subapp_path,
                        "Release": "All",
                        "Status code": None,
                        "Message": message if err_msg is None else err_msg,
                    }
                ]
            )
            continue

        results = []
        success = False
        for gh_release in gh_releases:
            repo.git.checkout(gh_release.tag_name)
            release_version = gh_release.tag_name
            if release_version.startswith("sly-release-"):
                release_version = release_version[len("sly-release-") :]
            results.append(
                do_release(
                    repo=repo,
                    server_address=prod_server_address,
                    api_token=prod_api_token,
                    slug=slug,
                    subapp_path=subapp_path,
                    release_version=release_version,
                    release_name=gh_release.title,
                    add_slug=True,
                    repo_url=repo_url,
                    created_at=None,
                    share=False,
                    archive_only_config=archive_only_config,
                )
            )
            # if any of the releases is successful, consider the whole app release successful
            success = success or results[-1]["Status code"] == 200
        if success:
            print("  [OK]\n")
        else:
            print("[Fail]\n")

        # if all of the apps released successfully, consider the whole release successful
        all_success = all_success and success
        print_results(results)
    return 0 if all_success else 1


def fetch_versions_json(github_access_token):
    GH = Github(github_access_token)
    repo = GH.get_repo("supervisely/supervisely")
    versions_json = repo.get_contents("versions.json", ref="master")
    return json.loads(versions_json.decoded_content.decode("utf-8"))


def fetch_docker_images(github_access_token):
    GH = Github(github_access_token)
    repo = GH.get_repo("supervisely/supervisely")
    docker_images_dirs = repo.get_contents("docker_images")
    images = []
    for item in docker_images_dirs:
        item: ContentFile.ContentFile
        if item.type == "dir":
            images.append(item.name.replace("_", "-"))
    return images


def fetch_release_description(github_access_token, slug, release_version):
    GH = Github(github_access_token)
    gh_repo = GH.get_repo(slug)
    gh_release = gh_repo.get_release(release_version)
    return gh_release.body


def get_sdk_versions_range(instance_version: str, versions_json: Dict):
    sorted_versions = sorted(versions_json.items(), key=lambda x: version_tuple(x[0]))
    min_sdk = None
    max_sdk = None
    for inst_ver, sdk_ver in sorted_versions:
        if compare_semver(instance_version, inst_ver) >= 0:
            min_sdk = sdk_ver
        if compare_semver(instance_version, inst_ver) < 0:
            max_sdk = sdk_ver
            break
    return min_sdk, max_sdk


def is_valid_versions(instace_version: str, sdk_version: str, versions_json: Dict):
    return True
    min_sdk, max_sdk = get_sdk_versions_range(instace_version, versions_json)
    if min_sdk is None:
        return compare_semver(sdk_version, max_sdk) < 0
    return compare_semver(sdk_version, min_sdk) >= 0 and (max_sdk is None or compare_semver(sdk_version, max_sdk) < 0)


def validate_instance_version(github_access_token: str, subapp_paths: List[str], slug:str, release_version: str):
    # fetch versions.json
    try:
        versions_json = fetch_versions_json(github_access_token)
        print("INFO: Versions info:")
        print(json.dumps(versions_json, indent=4))
    except Exception:
        print("ERROR: versions.json not found in supervisely/supervisely repository.")
        raise
    release_description = fetch_release_description(github_access_token, slug, release_version)
    # fetch docker_images
    try:
        standard_docker_images = fetch_docker_images(github_access_token)
        standard_docker_images = ["base-py-sdk", *standard_docker_images]
        print(f"INFO: Standard docker images: {', '.join(standard_docker_images)}")
    except Exception:
        print("ERROR: docker_images not found in supervisely/supervisely repository.")
        raise
    for subapp_path in subapp_paths:
        subapp_name = subapp_path if subapp_path else "root"
        print("INFO: Validating subapp:", subapp_name)
        try:
            config = get_config(subapp_path)
        except Exception:
            print(f"ERROR: Config file not found in subapp {subapp_name}")
            raise
        if config.get("type", None) == "collection":
            print(f"INFO: App {subapp_name} is a collection. Skipping validation.")
            continue
        if config.get("type", None) == "project":
            print(f"INFO: App {subapp_name} is a project. Skipping validation.")
            continue
        if config.get("type", None) == "client_side_app":
            print(f"INFO: App {subapp_name} is a client_side_app. Skipping validation.")
            continue
        # check requirements.txt
        if Path("" if subapp_path is None else "", "requirements.txt").exists():
            print(f"ERROR: requirements.txt file found in subapp {subapp_name}.")
            print("ERROR: Usage of requirements.txt is not allowed. Please, include all dependencies in the Dockerfile and remove requirements.txt")
            raise RuntimeError(f"requirements.txt file found in subapp: {subapp_name}")
        if "instance_version" not in config and "min_instance_version" not in config:
            print(f"ERROR: instance_version key not found in {subapp_name}. This key must be provided, check out the docs: https://developer.supervisely.com/app-development/basics/app-json-config/config.json#instance_version")
            raise RuntimeError(f"instance_version key not found in {subapp_name}")
        instance_version = config.get("instance_version", config.get("min_instance_version"))
        print(f"INFO: instance_version: {instance_version}")
        if "docker_image" not in config:
            print(f"ERROR: docker_image key not found in {subapp_name}. This key must be provided, check out the docs: https://developer.supervisely.com/app-development/basics/app-json-config/config.json#docker_image")
            raise RuntimeError(f"docker_image key not found in {subapp_name}")
        docker_image = config["docker_image"].replace("supervisely/", "")
        print(f"INFO: docker_image: {docker_image}")
        image_name, image_version = docker_image.split(":")
        if image_name in standard_docker_images:
            print(f"INFO: Docker image {image_name} is in the list of standard docker images.")
            print(f"INFO: Assuming that the version of the docker image ({image_version}) is a version of the supervisely Python SDK.")
            sdk_version = image_version
        else:
            print(f"INFO: Docker image {image_name} is not in the list of standard docker images.")
            try:
                print("INFO: Looking for SDK version in docker image labels")
                skopeo_result = subprocess.run(["skopeo", "inspect", f"docker://docker.io/supervisely/{image_name}:{image_version}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if skopeo_result.returncode != 0:
                    raise RuntimeError(f"skopeo inspect failed with code {skopeo_result.returncode}: {skopeo_result.stderr.decode('utf-8')}")
                inspect_data = json.loads(skopeo_result.stdout.decode("utf-8").strip())
                labels = inspect_data["Labels"]
                sdk_version = None
                for key in ("python_sdk_version", "python-sdk-version", "supervisely-sdk-version", "supervisely_sdk_version"):
                    if key in labels:
                        sdk_version = labels[key]
                        break
                if sdk_version is None:
                    raise RuntimeError(f"python_sdk_version not found in the docker image labels. Labels: {', '.join(labels.keys())}")
                sdk_version = sdk_version.split("+")[0].split("-")[0] # remove build metadata
            except Exception as e:
                print(f"INFO: python_sdk_version not found in the docker image labels. Error: {e}")
                print("INFO: When using custom docker images, you must provide the python_sdk_version in the docker image labels, example: python_sdk_version=6.73.10")
                print("INFO: Will read release description to find the appropriate SDK version.")
                print("INFO: Release description:", release_description)
                if release_description.find("python_sdk_version") == -1:
                    print("ERROR: python_sdk_version not found in the release description.")
                    print("ERROR: When using custom docker images, you must provide the python_sdk_version in the release description, example: python_sdk_version: 6.73.10")
                    raise RuntimeError("python_sdk_version not found in the release description.")
                sdk_version = release_description.split("python_sdk_version:")[1].strip(" \n")
        print(f"INFO: SDK version to check: {sdk_version}")
        # validate version
        if not is_valid_versions(instance_version, sdk_version, versions_json):
            min_sdk_ver, max_sdk_ver = get_sdk_versions_range(instance_version, versions_json)
            print(f"ERROR: Supervisely server version {instance_version} is incompatible with SDK version {sdk_version}")
            print(f"ERROR: for version {instance_version} SDK version should be in range [{min_sdk_ver} : {max_sdk_ver})")
            raise ValueError(f"ERROR: Server version {instance_version} is incompatible with SDK version {sdk_version}")
        print(f"INFO: SDK version {sdk_version} is valid for Instance version {instance_version}")

def need_validate_instance_version(release_type: str, github_access_token: str, slug: str, release_version: str):
    if release_type != ReleaseType.RELEASE:
        return False
    if os.getenv("SKIP_INSTANCE_VERSION_VALIDATION", False) in [1, "1", "true", "True", True]:
        return False
    release_description = fetch_release_description(github_access_token, slug, release_version)
    if release_description.find("skip_sdk_version_validation") != -1:
        return False
    return True


def validate_docker_image(subapp_paths):
    if os.getenv("SKIP_IMAGE_VALIDATION", False) in [1, "1", "true", "True", True]:
        return
    for subapp_path in subapp_paths:
        subapp_name = subapp_path if subapp_path else "root"
        print("INFO: Validating subapp:", subapp_name)
        try:
            config = get_config(subapp_path)
        except Exception:
            print(f"ERROR: Config file not found in subapp {subapp_name}")
            raise
        if config.get("type", None) in ["project", "collection", "client_side_app"]:
            return
        docker_image = config["docker_image"].replace("supervisely/", "")
        skopeo_result = subprocess.run(["skopeo", "inspect", f"docker://docker.io/supervisely/{docker_image}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if skopeo_result.returncode != 0:
            raise RuntimeError(f"skopeo inspect failed with code {skopeo_result.returncode}: {skopeo_result.stderr.decode('utf-8')}")


def run(
    dev_server_address: str,
    prod_server_address: str,
    dev_api_token: str,
    private_dev_api_token: str,
    prod_api_token: str,
    slug: str,
    subapp_paths: List[str],
    github_access_token: str,
    release_version: str,
    release_description: str,
    release_type: Literal[
        "release", "release-branch", "publish"
    ],
    include_sly_releases=False,
    archive_only_config=False,
):
    """
    slug - Slug of the app. Example: "supervisely-ecosystem/test-app"
    subapp_paths - List of paths to a directory with config.json.
                   For root app = "__ROOT_APP__" or "" or None.
                   Example: ["__ROOT_APP__", "serve/app"]
    api_token - API token of the releasing user.
    server_address - Server address of the instance where to release.
    github_access_token - Github access token of the releasing user.
    prod_api_token - API token of production instance user.
    prod_server_address - Server address of the production instance.
    release_version - Version of the release. In semver format for version release
                      Branch name for branch releases.
                      Example: "v1.0.0" or "test-branch"
    release_description - Description of the release.
    release_type - Type of the release. One of "release", "release-branch", "publish"
    """

    release_types = [ReleaseType.RELEASE, ReleaseType.RELEASE_BRANCH, ReleaseType.PUBLISH]
    if release_type not in release_types:
        print(f"Unknown release type. Should be one of {release_types}")
        return 1

    subapp_paths = [None if p in ["", "__ROOT_APP__"] else p for p in subapp_paths]

    print("Slug:\t\t\t", slug)
    print(
        "Subapp Paths:\t\t", ["__ROOT_APP__" if p is None else p for p in subapp_paths]
    )
    print("Release Version:\t", release_version)
    print("Release Description:\t", release_description)
    print()

    if release_description.isspace() or release_description is None:
        print("Release description cannot be empty.")
        return 1

    repo = git.Repo()
    try:
      remote_name = repo.active_branch.tracking_branch().remote_name
      remote = repo.remote(remote_name)
      repo_url = remote.url
    except:
      repo_url = f"https://github.com/{slug}"
      print(f"Cannot define remote branch. Set repo_url to {repo_url}")

    try:
        validate_docker_image(subapp_paths)
    except:
        print("Error validating docker image. Check that docker image config is correct.")
        return 1

    if need_validate_instance_version(release_type, github_access_token, slug, release_version):
        try:
            validate_instance_version(github_access_token, subapp_paths, slug, release_version)
        except Exception as e:
            print("Error validating instance version")
            return 1

    if release_type == ReleaseType.RELEASE:
        return run_release(
            dev_server_address=dev_server_address,
            prod_server_address=prod_server_address,
            private_dev_api_token=private_dev_api_token,
            prod_api_token=prod_api_token,
            repo=repo,
            repo_url=repo_url,
            slug=slug,
            subapp_paths=subapp_paths,
            release_version=release_version,
            release_description=release_description,
            archive_only_config=archive_only_config,
        )

    if release_type == ReleaseType.RELEASE_BRANCH:
        return run_release_branch(
            dev_server_address=dev_server_address,
            prod_server_address=prod_server_address,
            dev_api_token=dev_api_token,
            private_dev_api_token=private_dev_api_token,
            prod_api_token=prod_api_token,
            repo=repo,
            repo_url=repo_url,
            slug=slug,
            subapp_paths=subapp_paths,
            release_version=release_version,
            release_description=release_description,
            archive_only_config=archive_only_config,
        )

    if release_type == ReleaseType.PUBLISH:
        try:
            gh_releases = get_GitHub_releases(
                github_access_token, slug, include_sly_releases
            )
        except GithubException as e:
            print(f"Error connecting to Github. Could not publish app: {e}")
            return 1
        return publish(
            prod_server_address=prod_server_address,
            prod_api_token=prod_api_token,
            repo=repo,
            repo_url=repo_url,
            slug=slug,
            subapp_paths=subapp_paths,
            gh_releases=gh_releases,
            archive_only_config=archive_only_config,
        )

    return 1


def main():
    dev_server_address = os.getenv("DEV_SERVER_ADDRESS", None)
    prod_server_address = os.getenv("PROD_SERVER_ADDRESS", None)
    dev_api_token = os.getenv("DEV_API_TOKEN", None)
    private_dev_api_token = os.getenv("PRIVATE_DEV_API_TOKEN", None)
    prod_api_token = os.getenv("PROD_API_TOKEN", None)
    slug = os.getenv("SLUG", None)
    subapp_paths = parse_subapp_paths(os.getenv("SUBAPP_PATHS", []))
    github_access_token = os.getenv("GH_ACCESS_TOKEN", None)
    release_version = os.getenv("RELEASE_VERSION", None)
    release_description = os.getenv("RELEASE_DESCRIPTION", None)
    archive_only_config = os.getenv("ARCHIVE_ONLY_CONFIG", False)
    archive_only_config = archive_only_config in [1, "1", "true", "True", True]

    release_type = os.getenv("RELEASE_TYPE", None)

    sys.exit(
        run(
            dev_server_address=dev_server_address,
            prod_server_address=prod_server_address,
            dev_api_token=dev_api_token,
            private_dev_api_token=private_dev_api_token,
            prod_api_token=prod_api_token,
            slug=slug,
            subapp_paths=subapp_paths,
            github_access_token=github_access_token,
            release_version=release_version,
            release_description=release_description,
            release_type=release_type,
            archive_only_config=archive_only_config,
        )
    )


if __name__ == "__main__":
    main()
