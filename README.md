Files under `templates/` are copied into app repositories; they are not called from here. The
reusable workflows that app repositories call live in `.github/workflows/`.

# Main releases

To enable app releases you need to add `.github/workflows/release.yml` file into your app repository
(copy `templates/release.yml`; manual publishing: `templates/publish.yml`).

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

To enable branch app releases you need to add `.github/workflows/release_branch.yml` file into your app repository
(copy `templates/release_branch.yml`, or `templates/build_release_branch.yml` to build a test image first).
Each time there is a push to a branch, a new release with release version and release name equal to the branch name will be created.
Optional behavior: set `BUILD_TEST_IMAGE_ON_RELEASE: "true"` to build a test image before the branch release.
The image tag is `test-<first 8 hex of sha256>` of the files in `TEST_IMAGE_FILES` (concatenated, missing files skipped),
and `config.json` must name exactly `supervisely/<repo>:test-<hash>`; on a mismatch the job fails and prints the value
to set. The image is built only when that tag is not on Docker Hub yet. A tag per content matters: agents start images
with pull policy "if not present", so an image rebuilt under a tag they already have (the old `:test`) never reaches them.
Pin a git SDK dependency by commit, not by branch, so that a new SDK commit changes the hash.

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

env:
  BUILD_TEST_IMAGE_ON_RELEASE: "false"
  # Files the test image is built from. Their content names the image tag: test-<sha256[:8]>.
  TEST_IMAGE_FILES: "dev_requirements.txt requirements.txt docker/hardened/Dockerfile.tmpl"

jobs:
  Test-Image-Tag:
    runs-on: ubuntu-latest
    outputs:
      enabled: ${{ steps.tag.outputs.enabled }}
      build: ${{ steps.tag.outputs.build }}
      tag: ${{ steps.tag.outputs.tag }}
    steps:
      - uses: actions/checkout@v6
        with:
          persist-credentials: false

      # One tag per content: agents start images with pull policy "if not present", so a rebuilt
      # image under a tag an agent already has (the old ":test") never reaches it.
      - name: Resolve test image tag
        id: tag
        run: |
          if [ "$BUILD_TEST_IMAGE_ON_RELEASE" != "true" ]; then
            echo "enabled=false" >> "$GITHUB_OUTPUT"
            echo "Test image build before branch release is disabled"
            exit 0
          fi
          echo "enabled=true" >> "$GITHUB_OUTPUT"

          HASH=$(for f in $TEST_IMAGE_FILES; do [ -f "$f" ] && cat "$f"; done | sha256sum | cut -c1-8)
          TAG="test-$HASH"
          REPO=$(echo "${GITHUB_REPOSITORY#*/}" | tr '[:upper:]' '[:lower:]')
          EXPECTED="supervisely/$REPO:$TAG"
          CONFIGURED=$(python3 -c 'import json; print(json.load(open("config.json")).get("docker_image", ""))')
          echo "tag=$TAG" >> "$GITHUB_OUTPUT"

          case "$CONFIGURED" in
            *:test*)
              if [ "$CONFIGURED" != "$EXPECTED" ]; then
                echo "::error file=config.json::config.json has docker_image \"$CONFIGURED\"; for the current $TEST_IMAGE_FILES set it to \"$EXPECTED\""
                exit 1
              fi
              echo "build=true" >> "$GITHUB_OUTPUT"
              echo "Test image: $EXPECTED (built only if the tag is not on Docker Hub yet)"
              ;;
            *)
              echo "build=false" >> "$GITHUB_OUTPUT"
              echo "config.json uses $CONFIGURED, not a test image; nothing to build"
              ;;
          esac

  Build-Test-Image:
    needs: Test-Image-Tag
    if: ${{ needs.Test-Image-Tag.outputs.enabled == 'true' && needs.Test-Image-Tag.outputs.build == 'true' }}
    uses: supervisely-ecosystem/workflows/.github/workflows/build_image_from_template.yml@master
    with:
      tag_version: ${{ needs.Test-Image-Tag.outputs.tag }}
      # an existing tag already has this content, so the build is skipped
      skip_tag_check: false
      # with the SDK pinned to a commit in dev_requirements.txt, name the runtime base tag explicitly:
      # tag_ref_name: "6.74.46"

  Supervisely-Release-Branch:
    needs:
      - Test-Image-Tag
      - Build-Test-Image
    if: ${{ always() && needs.Test-Image-Tag.result == 'success' && (needs.Test-Image-Tag.outputs.build != 'true' || needs.Build-Test-Image.result == 'success') }}
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

# Models Release and Updates

## Configuration Discovery Rules

For neural network applications, the workflow automatically determines **framework** and **models file path** using the following rules:

### 1. Environment Variables Priority

If `FRAMEWORK` and `MODELS_PATH` variables are already set in workflow inputs, they are used without searching for configuration.

### 2. Train Folder Search

If variables are not set, the script searches for the `train` folder in the following order:

1. **Path**: `supervisely_integration/train/`
2. **Path**: `train/` (in repository root)

### 3. Parsing config.json

The `config.json` file must exist in the found `train` folder with the following structure:

```json
{
  "framework": {
    "name": "SparseInst"
  },
  "files": {
    "models": "models/models.json"
  }
}
```

Extracted fields:

- `framework.name` → environment variable `FRAMEWORK`
- `files.models` → environment variable `MODELS_PATH`

### 4. Usage in Workflow

The extracted values automatically become available in subsequent workflow steps via environment variables.
