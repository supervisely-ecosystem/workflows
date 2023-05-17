import os
from pathlib import Path
import re
import requests
from contextlib import contextmanager

import git
from github import Github
import shutil

from release import run


SUPERVISELY_ECOSYSTEM_REPOSITORY_V2_URL = "https://raw.githubusercontent.com/supervisely-ecosystem/repository/master/README_v2.md"


@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


def parse_ecosystem_repository_page(url):
    r = requests.get(url)
    content = r.content.decode("utf-8")
    results = [
        "https://github.com/" + res
        for res in re.findall(r"https://github.com/(.*)\n", content)
    ]
    return results


def get_slug(repo_url):
    return "/".join(repo_url.split("/")[1:])


def get_subapp_path(app_url: str):
    app_url = app_url.removeprefix("https://").removeprefix("http://")
    subapp_path = "/".join(app_url.split("/")[3:])
    return subapp_path if subapp_path else "__ROOT_APP__"


def get_repo_url(app_url: str):
    app_url = app_url.removeprefix("https://").removeprefix("http://")
    return "/".join(app_url.split("/")[:3])


def is_release_tag(tag_name):
    return re.match("v\d+\.\d+\.\d+", tag_name) != None


def sorted_releases(releases):
    key = lambda release: [int(x) for x in release.tag_name[1:].split(".")]
    return sorted(releases, key=key)


def clone_repo(slug):
    repo_dir = os.path.join(os.getcwd(), "repo")
    if os.path.exists(repo_dir):
        return git.Repo(repo_dir)
    else:
        return git.Repo.clone_from(slug, repo_dir)


def delete_repo():
    repo_dir = Path(os.getcwd()).joinpath("repo")
    if repo_dir.exists():
        shutil.rmtree(repo_dir)


def release_app(app_url):
    app_url = (
        app_url.replace(".www", "")
        .replace("/tree/master", "")
        .replace("/tree/main", "")
    )
    # app_url = "https://github.com/org/repo/path/to/subapp"
    repo_url = get_repo_url(app_url)
    subapp_path = get_subapp_path(app_url)
    slug = get_slug(repo_url)
    api_token = os.getenv("API_TOKEN", None)
    server_address = os.getenv("SERVER_ADDRESS", None)
    github_access_token = os.getenv("GITHUB_ACCESS_TOKEN", None)

    delete_repo()
    repo = clone_repo("https://github.com/" + slug)
    with cd(Path(os.getcwd()).joinpath("repo")):
        GH = Github(github_access_token)
        repo_name = repo_url.removeprefix("github.com/")
        gh_repo = GH.get_repo(repo_name)
        gh_releases = sorted_releases(
            [rel for rel in gh_repo.get_releases() if is_release_tag(rel.tag_name)]
        )

        print()
        print("App url:", app_url)
        print("Slug:", slug)
        print("Subapp path:", subapp_path)
        print("GH releases:", gh_releases)

        for gh_releases in gh_releases:
            release_version = gh_releases.tag_name
            release_name = gh_releases.title
            repo.git.checkout(release_version)
            run(
                slug=slug,
                subapp_paths=[subapp_path],
                server_address=server_address,
                api_token=api_token,
                github_access_token=github_access_token,
                release_version=release_version,
                release_title=release_name,
            )

    repo.git.clear_cache()


if __name__ == "__main__":
    app_urls = parse_ecosystem_repository_page(SUPERVISELY_ECOSYSTEM_REPOSITORY_V2_URL)
    for app_url in app_urls:
        release_app(app_url)
