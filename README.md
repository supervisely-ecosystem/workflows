To enable app releases you need to add `.github/workflows/release.yaml` file into your app repository.

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
    secrets:
      SUPERVISELY_API_TOKEN: "${{ secrets.SUPERVISELY_API_TOKEN }}"
      GH_ACCESS_TOKEN: "${{ secrets.GITHUB_TOKEN }}"
    with:
      SUPERVISELY_SERVER_ADDRESS: "${{ vars.SUPERVISELY_SERVER_ADDRESS }}"
      SLUG: "${{ github.repository }}"
      RELEASE_VERSION: "${{ github.event.release.tag_name }}"
      RELEASE_TITLE: "${{ github.event.release.name }}"
      SUBAPP_PATHS: "__ROOT_APP__, subapp"
```

SUBAPP_PATHS - list of subapp paths, separated by comma. If you don't have subapps, just leave `__ROOT_APP__`.
examples:
1. Subapps located in /train and /serve folders
```yaml
SUBAPP_PATHS: "train, serve"
```
2. Main app only
```yaml
SUBAPP_PATHS: "__ROOT_APP__"
```