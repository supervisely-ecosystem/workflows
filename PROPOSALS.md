# Proposals that need an owner/org decision

Companion to branch `audit-fixes-2026-10`. That branch fixes the findings that are local to this
repository. The items below change who holds credentials, what blocks a release, or what every
caller repo has to do, so they are not implemented. IDs refer to the audit
(`ecosystem-fleet/audits/workflows-audit.md`, origin/HEAD 09ca757) and to
`ecosystem-fleet/QUESTIONS.md`.

---

## 1. Release credentials come from the runner's environment (C-1)

**Problem.** `release.py`, `release_models.py` and `update_models.py` read
`SUPERVISELY_PROD_API_TOKEN`, the dev tokens and the GitHub PAT from the self-hosted runner host's
environment. These values are not GitHub secrets, so GitHub does not mask them in logs. Any job
that runs on `gha-runner-supervisely-ecosystem` (runner group `default`) can read them with
`run: env`. `common.yml` declares the secrets that ~1,100 caller jobs pass
(`SUPERVISELY_*_API_TOKEN: ${{ secrets.* }}` and `GH_ACCESS_TOKEN: ${{ secrets.GITHUB_TOKEN }}`)
but never uses them, so rotating a GitHub secret changes nothing.

**Options.**
- **A. Mitigate in place.** Add a first step to the release job that runs
  `echo "::add-mask::$SUPERVISELY_PROD_API_TOKEN"` for every token, and delete the unused
  `_token_info` helper. No behaviour change. This hides tokens in logs but not from other jobs.
- **B. Use the secrets callers already pass.** Map `secrets.*` into the env of the single
  `release.py` step. Fall back to the runner env only when the secret is empty.
- **C. Do it properly.** Put the tokens in a GitHub Environment with protection rules, give the
  release jobs a dedicated runner group restricted to `common.yml@refs/heads/master` ("selected
  workflows"), and remove the tokens from the runner host.

**Risk.** B can break every release at once. The org or repo secrets may be stale, may belong to a
different user or team, or may lack permissions, and a fallback only helps when the secret is
*empty*, not when it is wrong. `GH_ACCESS_TOKEN` is the caller's `GITHUB_TOKEN`, which can read the
repo's own releases (enough for `release.py`) but not other private repos. C needs an org admin
and runner changes.

**Recommendation.** Do A now. Before B, add a one-off check job (in one test repo) that prints
only whether `sha256(secret) == sha256(env)` for each token. Switch to B per token once the hashes
match. Then plan C.

## 2. The CVE gate blocks releases on base-image vulnerabilities (H-2)

**Problem.** With `cve_checks: true`, `build_image_from_template.yml` runs pip-audit over *every*
Python package in the built image and fails the job, and `Supervisely-Release` needs that job.
Vulnerabilities in `base-py-sdk-hardened` (the SDK's dependency tree) block apps whose authors
cannot fix them. In run 33847077845, export-to-coco had a comment-only requirements file and all
18 findings came from the base. The gate can also scan an image the app does not use (it builds
`supervisely/<repo>:<tag>` regardless of config.json, see item 5).

**Options.**
- **A.** Audit the base image (`supervisely/<RUNTIME_BASE_IMAGE>:<TAG_REF_NAME>`) in the same job
  and fail only on vulnerability IDs that the base does not have.
- **B.** Fail only on packages the app layer adds or changes: a different name or version than the
  base's syft inventory. Report the rest as warnings.
- **C.** Support an ignore file in the caller repo (`pip-audit --ignore-vuln ID`), with an owner
  and an expiry date per entry.
- **D.** Make the gate advisory (annotation plus artifact, never blocking).

**Risk.** A and B pull the base image and roughly double the scan time. B misses a vulnerable base
package that the app pins *to the same version*, which is acceptable because the base owner owns
that fix. C needs governance or it becomes "ignore everything". D removes the protection.

**Recommendation.** B (failing on introduced or changed packages) plus C with mandatory expiry.
The SDK/base pipeline should scan and fix the base images. Fix the image name first (item 5),
otherwise the gate keeps scanning the wrong image.

## 3. `branches:` under `on: release` is ignored, and the template's `target_commitish` check (M-6)

**Problem.** The README template, copied into 356 of 370 release workflows, uses
`on: release: … branches: [main, master]`. GitHub supports `branches` only for
push/pull_request/merge_group/workflow_run, so the key is silently ignored. Proof: export-to-coco
v2.2.6 had `target_commitish` = a SHA and released to prod (run 36438290945). The newer template
(`release.yml`) instead checks `target_commitish == 'main' || 'master'`. That check silently skips
releases created from a SHA, which is common in the org, and passes tags on feature-branch commits
whose `target_commitish` still says `master`.

**Options.**
- **A.** Document that any published release goes to production. Drop `branches:` and the
  `target_commitish` condition from the README and the templates.
- **B.** Gate centrally in `common.yml`: for `RELEASE_TYPE == release`, fail unless
  `git merge-base --is-ancestor <tag commit> origin/<default branch>` (default branch from
  `github.event.repository.default_branch`), with an explicit escape hatch (an input, or a marker
  in the release body) for intentional hotfix releases.
- **C.** Fix 356 caller workflows. They would still need B's logic, so this alone is not enough.

**Risk.** B starts failing releases from non-default branches that today go to prod, intentionally
or not. Teams that release from `release/*` branches need the escape hatch. A is honest but keeps
the hole open.

**Recommendation.** B with the escape hatch, announced in advance. Then update the README and the
templates (A's text changes) and roll out to callers opportunistically. Also switch the templates
to `types: [released]` (audit L-6) in the same pass.

## 4. Pinning callers to `@master`, and helper scripts always from master (M-11, H-1 follow-up)

**Problem.** 1,120 jobs call `common.yml@master`. `common.yml` and `sync_models_common.yml`
check out this repo with no `ref`, so even a caller pinned to a SHA runs today's `release.py`.
The repo has no tags. Every push to master changes release behaviour for ~430 apps at once.
Branches that callers still reference have been deleted (`runner-updates`, `build-test-image`).
MaskDINO and instance-performance-meter still point at `@runner-updates`.

**Options.**
- **A.** Add a `workflows_ref` input (default `master`) to `common.yml` and the models workflows
  and use it in every checkout, as `build_image_from_template.yml` already does.
- **B.** Publish semver tags (`v1.0.0`, plus a moving `v1`). Callers use `@v1`, and the helper
  checkout uses the same ref: either a `workflows_ref` default bumped in the tagging commit, or
  the OIDC `job_workflow_ref`/`job_workflow_sha` claim (needs `id-token: write`).
- **C.** Protect `master`: require a PR, a review, and CI running `pytest tests` (added on this
  branch) and actionlint. Forbid deleting branches or tags that callers reference.

**Risk.** B needs release discipline (moving `v1`, changelog), and callers have to migrate. Until
they do, `@master` keeps the current behaviour, which is not a regression. A alone gives
reproducibility only to callers who set the input.

**Recommendation.** C immediately (the tests now exist). Then A + B: tag `v1.0.0` after this branch
lands, make helper checkouts follow the tag, and move templates and new repos to `@v1`. Fix
MaskDINO and instance-performance-meter to `@master` (or `@v1`) now.

## 5. The per-app image tag does not cover dependency changes (QUESTIONS 3.6; related: H-5, M-8, QUESTIONS 3.7)

**Problem.** `build_image_from_template.yml` tags the per-app image with the SDK version from
config.json only, and skips the whole build when that tag exists on Docker Hub. A release that
changes `dev_requirements.txt` or the template but keeps the SDK version ships the *old* image, so
missing dependencies show up only at runtime. Related problems:
- The SDK check validates the *tag*, not the SDK inside the image (H-5). Template images carry no
  labels, and `release.py` treats the tag as the SDK version when it `startswith("6.7")`.
- The builder ignores the image *name* in config.json (M-8). export-to-coco builds
  `supervisely/export-to-coco:*` but runs `supervisely/import-export:*`.
- Apps on the bare hardened image still build a per-app image (QUESTIONS 3.7).
- `release.py` and `resolve_release_tag.py` cannot parse a suffixed tag: `6.74.34-1` becomes
  `6.74.341` in `release.py`, and `int("34-1")` fails in `resolve_release_tag.py` (audit L-4).

**Options.**
- **A. Content hash in the tag:** `<sdk>-<sha8(requirements + template + build args)>`. Tags stay
  immutable. config.json must name that tag, so CI computes it and fails `build-image` with "set
  docker_image to …" when config.json differs.
- **B. Label check, no rebuild:** stamp `sly.requirements_sha256` (and the real
  `python_sdk_version`) as image labels. When the tag already exists, `skopeo inspect` it. If the
  hash differs, fail with "dependencies changed; bump the image tag" (e.g. `6.74.34-2`) instead of
  silently skipping.
- **C. Rebuild and overwrite the same tag** when the hash differs or the files changed since the
  last release tag.

**Risk.** C makes tags mutable. Agents that already pulled `:<tag>` keep the old image unless they
always pull, and a rollback is impossible. That is the worst option. A and B both need suffix
support in `release.py`/`resolve_release_tag.py` first, otherwise the SDK gate breaks. A changes
developer workflow on every dependency change. B is cheaper but relies on developers bumping a
suffix.

**Recommendation.**
1. *Prerequisite (local, low risk):* accept `X.Y.Z[-suffix]` everywhere and strip the suffix for
   SDK checks.
2. Stamp labels at build: `python_sdk_version` read from the installed package (fail if it differs
   from the tag, closing H-5) and `sly.requirements_sha256`.
3. B as the default behaviour (detect and fail, never overwrite). Move to A if teams prefer an
   automatic tag.
4. Build only when config.json's `docker_image` is `supervisely/<image_name>`, and print a notice
   otherwise (M-8, QUESTIONS 3.7). Apply this to release-triggered builds only, because the manual
   "build app image" flow runs before config.json is switched.

---

## Also left out of the branch on purpose

- `build_release_branch.yml:68` still uses `@build-test-image`, a deleted branch. This file and
  `release_branch.yml` are caller *templates*, but they live in `.github/workflows` and trigger on
  every branch push in *this* repo (audit L-8). Fixing the ref would let more of their jobs start
  here (including an image build and a branch release when `docker/hardened/` changes, as on this
  branch). Move the templates to `templates/` first, then fix the ref. **Pushing this branch
  triggers both templates in this repo**; they currently fail at startup or on the checkout
  policy.
- Job-level `timeout-minutes` and timeouts on the SDK's own `requests.post` calls (M-3). Choose
  values per job (CUDA builds are long). `skopeo` now has a 300 s timeout.
- M-4 remainder: prove the prod address and token with `instance.version` before treating a 404
  from `ecosystem.info` as "not published, release to dev". Upload atomicity needs a server-side
  API.
- M-2 option: let dev branch releases continue (private-dev token) when production is down.
- Low findings not covered by the fixes: L-2 (an empty release title passes; enforcing it would
  block releases that work today), L-3, L-4 (see item 5), L-5, L-6/L-7 (template changes, see
  item 3), L-9, L-10, L-11, L-12.
