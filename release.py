import json
import os
from pathlib import Path
import sys
from datetime import datetime

import git
from github import Github

from supervisely.cli.release import release, get_appKey


def parse_subapp_paths(subapps_paths):
    return [p.lstrip(" ").rstrip(" ") for p in subapps_paths.split(",")]


def get_release_name(tag):
    if tag.tag is None:
        return tag.name
    else:
        return tag.tag.message


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


def get_modal_template(app_path, config):
    app_path = Path(os.getcwd()) if app_path is None else Path(app_path)
    modal_template = ""
    if "modal_template" in config:
        modal_template_path = app_path.joinpath(config["modal_template"])
        if not modal_template_path.exists() or not modal_template_path.is_file():
            raise FileNotFoundError(modal_template_path)
        with open(modal_template_path, "r") as f:
            modal_template = f.read()
    return modal_template


def get_app_name(config: dict):
    app_name = config.get("name", None)
    return app_name


def get_created_at(repo: git.Repo, tag_name: str):
    print("Searching for release date. Tag name:", tag_name)
    if tag_name is None:
        return None
    for tag in repo.tags:
        if tag.name == tag_name:
            if tag.tag is None:
                print("Tag is lightweight. Taking commit date")
                timestamp = tag.commit.committed_date
            else:
                timestamp = tag.tag.tagged_date
            print("timestamp: ", datetime.utcfromtimestamp(timestamp).isoformat())
            return datetime.utcfromtimestamp(timestamp).isoformat()
    return None


def print_results(results):
    print()
    success_count = sum(1 for res in results if res["Status code"] == 200)
    print(f"Total: {len(results)} releases. Success: {success_count}/{len(results)}")
    if success_count != len(results):
        print("Results:")
        print(
            f'{"Result".ljust(10)}{"Release".ljust(30)}{"App name".ljust(20)}{"App path".ljust(20)}{"Status code".ljust(15)}Message'
        )
        for result in results:
            success = "[OK]" if result["Status code"] == 200 else "[FAIL]"
            print(
                f"{success.ljust(10)}"
                f'{result["Release"].ljust(28)[:28] + "  "}'
                f'{result["App name"].ljust(18)[:18] + "  "}'
                f'{result["App path"].ljust(18)[:18] + "  "}'
                f'{str(result["Status code"]).ljust(15)}'
                f'{result["Message"]}'
            )


def release_sly_releases(
    repo: git.Repo, server_address, api_token, github_access_token, slug, subapp_paths
):
    GH = Github(github_access_token)
    gh_repo = GH.get_repo(slug)
    if gh_repo.get_releases().totalCount > 1:
        print("Not the first release, skipping sly-releases")
        return

    repo_url = f"https://github.com/{slug}"

    key = lambda tag: [int(x) for x in tag.name[13:].split(".")]
    sorted_tags = sorted(
        [tag for tag in repo.tags if tag.name.startswith("sly-release-v")], key=key
    )

    if len(sorted_tags) == 0:
        print("No sly releases")
        return []
    else:
        print("Releasing sly releases")
        results = []

    for tag in sorted_tags:
        tag: git.TagReference
        repo.git.checkout(tag)
        release_version = tag.name[12:]
        release_name = get_release_name(tag)
        created_at = get_created_at(repo, tag.name)

        print("Releasing sly-release. Tag:", f'"{tag.name}"')
        print("Release version:\t", release_version)
        print("Release title:\t\t", release_name)

        for path in subapp_paths:
            subapp_path = None if path == "__ROOT_APP__" else path

            appKey = get_appKey(repo, subapp_path, repo_url)
            config = get_config(subapp_path)
            readme = get_readme(subapp_path)
            modal_template = get_modal_template(subapp_path, config)

            app_name = get_app_name(config)
            if subapp_path is None:
                print("Releasing root app")
            else:
                print(f'Releasing subapp at "{path}"')
            print("App Name:\t\t", app_name)

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
                slug=slug,
                created_at=created_at,
            )

            results.append(
                {
                    "App name": app_name,
                    "App path": path,
                    "Release": f"{release_version} ({release_name})",
                    "Status code": response.status_code,
                    "Message": response.json(),
                }
            )

    if len(results) > 0:
        print_results(results)


def release_github(
    repo, server_address, api_token, slug, subapp_paths, release_version, release_name
):
    print()
    print("Releasing")
    print("Release version:\t", release_version)
    print("Release title:\t\t", release_name)

    repo_url = f"https://github.com/{slug}"
    results = []
    for path in subapp_paths:
        subapp_path = None if path == "__ROOT_APP__" else path
        appKey = get_appKey(repo, subapp_path, repo_url)
        config = get_config(subapp_path)
        readme = get_readme(subapp_path)
        modal_template = get_modal_template(subapp_path, config)

        app_name = get_app_name(config)
        if subapp_path is None:
            print("Releasing root app")
        else:
            print(f'Releasing subapp at "{path}"')
        print("App Name:\t\t", app_name)

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
            slug=slug,
            created_at=None,
        )

        results.append(
            {
                "App name": app_name,
                "App path": path,
                "Release": f"{release_version} ({release_name})",
                "Status code": response.status_code,
                "Message": response.json(),
            }
        )

    if len(results) > 0:
        print_results(results)


def run(
    slug,
    subapp_paths,
    server_address,
    api_token,
    github_access_token,
    release_version,
    release_title,
):
    if len(subapp_paths) == 0:
        subapp_paths = ["__ROOT_APP__"]

    repo = git.Repo()

    print("Server Address:\t\t", server_address)
    print("Api Token:\t\t", f"{api_token[:4]}****{api_token[-4:]}")
    print("Slug:\t\t\t", slug)

    release_sly_releases(
        repo,
        server_address=server_address,
        api_token=api_token,
        github_access_token=github_access_token,
        slug=slug,
        subapp_paths=subapp_paths,
    )

    release_github(
        repo,
        server_address=server_address,
        api_token=api_token,
        slug=slug,
        subapp_paths=subapp_paths,
        release_version=release_version,
        release_name=release_title,
    )


if __name__ == "__main__":
    slug = sys.argv[1]
    subapp_paths = parse_subapp_paths(sys.argv[2])
    api_token = os.getenv("API_TOKEN", None)
    server_address = os.getenv("SERVER_ADDRESS", None)
    github_access_token = os.getenv("GITHUB_ACCESS_TOKEN", None)
    release_version = os.getenv("RELEASE_VERSION", None)
    release_title = os.getenv("RELEASE_TITLE", None)
    run(
        slug=slug,
        subapp_paths=subapp_paths,
        server_address=server_address,
        api_token=api_token,
        github_access_token=github_access_token,
        release_version=release_version,
        release_title=release_title,
    )
