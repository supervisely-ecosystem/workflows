# Main releases

To enable app releases you need to add `.github/workflows/release.yml` file into your app repository.

These env vars must be configured on the GitHub Actions runner:

- `SUPERVISELY_PROD_SERVER_ADDRESS`
- `SUPERVISELY_PROD_API_TOKEN`
- `SUPERVISELY_GITHUB_ACCESS_TOKEN`

```yaml
name: Supervisely release
run-name: Supervisely ${{ github.repository }} app release
on:
  release:
    types: [published]
    branches:
      - main
      - master
jobs:
  Supervisely-Release:
    uses: supervisely-ecosystem/workflows/.github/workflows/common.yml@master
    with:
      SLUG: "${{ github.repository }}"
      RELEASE_VERSION: "${{ github.event.release.tag_name }}"
      RELEASE_TITLE: "${{ github.event.release.name }}"
      IGNORE_SLY_RELEASES: 1
      RELEASE_WITH_SLUG: 1
      CHECK_PREV_RELEASES: 1
      SUBAPP_PATHS: "__ROOT_APP__, subapp"
```

`SUBAPP_PATHS` - list of sub app paths, separated by comma. If you don't have sub apps, just leave `__ROOT_APP__`.

### Examples:

1. Sub apps located in `/train` and `/serve` folders

```yaml
SUBAPP_PATHS: "train, serve"
```

2. Main app only

```yaml
SUBAPP_PATHS: "__ROOT_APP__"
```

# Branch releases

To enable branch app releases you need to add `.github/workflows/release_branch.yml` file into your app repository.
Each time there is a push to a branch, a new release with release version and release name equal to the branch name will be created.

These env vars must be configured on the GitHub Actions runner:

- `SUPERVISELY_PROD_SERVER_ADDRESS`
- `SUPERVISELY_PROD_API_TOKEN`
- `SUPERVISELY_GITHUB_ACCESS_TOKEN`
- `SUPERVISELY_DEV_API_TOKEN`
- `SUPERVISELY_PRIVATE_DEV_API_TOKEN`

```yaml
name: Supervisely release
run-name: Supervisely ${{ github.repository }} app release
on:
  push:
    branches-ignore:
      - main
      - master
jobs:
  Supervisely-Release:
    uses: supervisely-ecosystem/workflows/.github/workflows/common.yml@master
    with:
      SLUG: "${{ github.repository }}"
      RELEASE_VERSION: "${{ github.ref_name }}"
      RELEASE_DESCRIPTION: "'${{ github.ref_name }}' branch release"
      RELEASE_TYPE: "release-branch"
      SUBAPP_PATHS: "__ROOT_APP__, subapp"
```

`SUBAPP_PATHS` - list of sub app paths, separated by comma. If you don't have sub apps, just leave `__ROOT_APP__`.

### Examples:

1. Sub apps located in `/train` and `/serve` folders

```yaml
SUBAPP_PATHS: "train, serve"
```

2. Main app only

```yaml
SUBAPP_PATHS: "__ROOT_APP__"
```
