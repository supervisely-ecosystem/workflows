import os
from pathlib import Path
import sys
import git

from giturlparse import parse

from release_everything import (
    cd,
    delete_repo,
    get_slug,
    get_subapp_path,
    parse_ecosystem_repository_page,
    get_repo_url,
)
from release_everything import SUPERVISELY_ECOSYSTEM_REPOSITORY_V2_URL


def http_to_ssh(url: str) -> str:
    p = parse(url)
    return p.url2ssh


def set_subapp_paths(workflow: str, subapps: list[str]) -> str:
    lines = workflow.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("      SUBAPP_PATHS: "):
            lines[i] = '      SUBAPP_PATHS: "' + ", ".join(subapps) + '"'
    return "\n".join(lines)


if __name__ == "__main__":
    org = "supervisely-ecosystem"
    apps_repository_url = sys.argv[1]
    if apps_repository_url == "0":
        apps_repository_url = SUPERVISELY_ECOSYSTEM_REPOSITORY_V2_URL
    try:
        for_prod = int(sys.argv[2]) == 1
    except:
        for_prod = False
    common_workflow_path = (
        ".github/workflows/release.yml"
        if for_prod
        else ".github/workflows/release_dev.yml"
    )

    app_urls = parse_ecosystem_repository_page(apps_repository_url)
    app_urls = [
        (url.replace(".www", "").replace("/tree/master", "").replace("/tree/main", ""))
        for url in app_urls
    ]

    apps = {}
    for app_url in app_urls:
        repo_url = get_repo_url(app_url)
        subapp_path = get_subapp_path(app_url)
        if repo_url in apps:
            apps[repo_url].append(subapp_path)
        else:
            apps[repo_url] = [subapp_path]

    print(apps)

    with open(common_workflow_path, "r") as f:
        common_workflow = f.read()

    org = "supervisely-ecosystem"
    for repo_url, subapps in apps.items():
        slug = get_slug(repo_url)
        delete_repo()
        print("Cloning repository:", repo_url)
        repo = git.Repo.clone_from(http_to_ssh("https://" + repo_url), "repo")
        print("Done cloning repository:", repo_url)
        print("subapps:", subapps)
        with cd(Path(os.getcwd()).joinpath("repo")):
            app_workflow = set_subapp_paths(common_workflow, subapps)
            Path(common_workflow_path).parent.mkdir(exist_ok=True, parents=True)
            with open(common_workflow_path, "w") as f:
                f.write(app_workflow)
            index = repo.index
            index.add([common_workflow_path])
            if index.diff("HEAD"):
                index.commit(
                    f"Add release workflow for {'prod' if for_prod else 'dev'}"
                )
                try:
                    origin = repo.remote("origin")
                except:
                    origin = repo.create_remote("origin", http_to_ssh(repo_url))
                    origin.push()
            else:
                print("No changes to commit")
