import re
import subprocess
import traceback
from typing import List, Literal
import os
import sys
import git
import datetime
import json
from pathlib import Path
from github import Github, GitRelease, GithubException

from supervisely.cli.release.run import hided
from supervisely.cli.release.release import release, get_appKey, get_app_from_instance


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
):
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
):
    if not is_valid_version(release_version):
        print("Release version is not valid. Should be in semver format (v1.2.3).")
        return 1

    results = []
    for subapp_path in subapp_paths:
        if subapp_path is None:
            print("Releasing root app...".ljust(53), end=" ")
        else:
            print(
                (f'Releasing subapp at "{subapp_path}"'[:50] + "...").ljust(53), end=" "
            )

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
        if subapp_path is None:
            print("Releasing root app...".ljust(53), end=" ")
        else:
            print(
                (f'Releasing subapp at "{subapp_path}"'[:50] + "...").ljust(53), end=" "
            )
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
                )
            )

        else:
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
        "private", "private-branch", "publish", "to-prod", "branch-to-dev"
    ],
    include_sly_releases=False,
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

    RELEASE = "release"
    RELEASE_BRANCH = "release-branch"
    PUBLISH = "publish"

    release_types = [RELEASE, RELEASE_BRANCH, PUBLISH]
    if release_type not in release_types:
        print(f"Unknown release type. Should be one of {release_types}")
        return 1

    subapp_paths = [None if p in ["", "__ROOT_APP__"] else p for p in subapp_paths]

    print("Server Address:\t\t", dev_server_address)
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
    repo_url = f"https://github.com/{slug}"

    if release_type == RELEASE:
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
        )

    if release_type == RELEASE_BRANCH:
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
        )

    if release_type == PUBLISH:
        try:
            gh_releases = get_GitHub_releases(
                github_access_token, slug, include_sly_releases
            )
        except GithubException as e:
            print("Error connecting to Github. Could not publish app.")
            return 1
        return publish(
            prod_server_address=prod_server_address,
            prod_api_token=prod_api_token,
            repo=repo,
            repo_url=repo_url,
            slug=slug,
            subapp_paths=subapp_paths,
            gh_releases=gh_releases,
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
    github_access_token = os.getenv("GITHUB_ACCESS_TOKEN", None)
    release_version = os.getenv("RELEASE_VERSION", None)
    release_description = os.getenv("RELEASE_DESCRIPTION", None)

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
        )
    )


if __name__ == "__main__":
    main()
