"""`compression` / `compression_level` inputs of build_image.yml and build_image_from_template.yml.

Callers that do not pass them (every caller uses these workflows @master) or pass gzip must run
exactly what master cc76879 ran. zstd appends the exporter options of the platform's own images
(zstd level 7, forced, OCI media types) to buildctl's --output and makes skopeo push the scanned
archive (cve_checks) as zstd OCI.
"""

import gzip
import hashlib
import io
import json
import shutil
import subprocess
import tarfile

import pytest

from workflow_runner import ROOT, fake_bin, run_step

BASE_COMMIT = "cc76879"
JOB = "build-and-push"
PREPARE = "Prepare layer compression"
ZSTD_OUTPUT = ",compression=zstd,compression-level=7,force-compression=true,oci-mediatypes=true"
CREDS = {"DOCKERHUB_USERNAME": "u", "DOCKERHUB_TOKEN": "t0k"}

BUILD_IMAGE = "build_image.yml"
BUILD_IMAGE_STEPS = [
    "Build Docker Image ${{ env.IMAGE_NAME }}:${{ inputs.tag_version }}",
    "Build Docker Image ${{ env.IMAGE_NAME }}:latest",
]
BUILD_IMAGE_INPUTS = {
    "tag_version": "1.2.3", "dockerfile_path": "docker/Dockerfile", "image_name": "",
    "sdk_version": "", "latest_tag": True,
}

TEMPLATE = "build_image_from_template.yml"
TEMPLATE_STEPS = [
    "Build image archive for checks",
    "Build and push Docker Image ${{ env.IMAGE_NAME }}:${{ env.TAG_VERSION }}",
    "Build and push Docker Image ${{ env.IMAGE_NAME }}:latest",
    "Push scanned image archive",
    "Tag and push latest from scanned image",
]
TEMPLATE_INPUTS = {
    "image_name": "", "tag_version": "6.74.34", "tag_ref_name": "",
    "dockerfile_template_path": "docker/hardened/Dockerfile.tmpl", "docker_target": "",
    "requirements_file": "dev_requirements.txt", "config_file": "config.json",
    "runtime_base_image": "", "extra_builder_libs": "", "no_cache_requirements": False,
    "build_cache": True, "skip_tag_check": False, "cve_checks": True, "latest_tag": True,
    "workflows_ref": "master",
}
TEMPLATE_ENV = {
    "IMAGE_NAME": "supervisely/my-app", "IMAGE_NAME_SAFE": "my-app",
    "TAG_VERSION": "6.74.34", "TAG_REF_NAME": "6.74.34",
    "DOCKERFILE_DIR": "docker/hardened", "DOCKERFILE_NAME": "Dockerfile.tmpl",
    "REQUIREMENTS_FILE": "dev_requirements.txt", "BUILD_SECRET_OPT": "",
}

CASES = (
    [(BUILD_IMAGE, step, BUILD_IMAGE_INPUTS, {"IMAGE_NAME": "supervisely/my-app"}) for step in BUILD_IMAGE_STEPS]
    + [(TEMPLATE, step, TEMPLATE_INPUTS, TEMPLATE_ENV) for step in TEMPLATE_STEPS]
)


@pytest.fixture(scope="module")
def base_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("base")
    (root / ".github" / "workflows").mkdir(parents=True)
    for wf in (BUILD_IMAGE, TEMPLATE):
        show = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{BASE_COMMIT}:.github/workflows/{wf}"],
            capture_output=True, text=True,
        )
        if show.returncode != 0:
            pytest.skip(f"commit {BASE_COMMIT} not available")
        (root / ".github" / "workflows" / wf).write_text(show.stdout)
    return root


def run(work, wf, step, inputs, env, secrets=None, workflow_root=ROOT):
    """Run `step` (after "Prepare layer compression", which the base commit does not have) with
    fake buildctl/skopeo/date; return (exit code, argv of every call)."""
    work.mkdir()
    log = work / "_argv"
    bin_dir = work / "_bin"
    for tool in ("buildctl", "skopeo"):
        fake_bin(bin_dir, tool, f'{{ echo "{tool}"; printf "%s\\n" "$@"; echo ---; }} >> {log}\n')
    fake_bin(bin_dir, "date", "echo 1700000000\n")
    common = dict(secrets=secrets or {}, github={"repository": "supervisely-ecosystem/my-app"},
                  fake_bin_dir=bin_dir, workflow_root=workflow_root)
    env = dict(env)
    if workflow_root == ROOT:
        proc, exported = run_step(wf, JOB, PREPARE, work, inputs=inputs, env=env, **common)
        if proc.returncode != 0:
            return proc.returncode, ""
        env.update(exported)
    proc, _ = run_step(wf, JOB, step, work, inputs=inputs, env=env, **common)
    argv = log.read_text().replace(str(work), "<WS>") if log.exists() else ""
    return proc.returncode, argv


def calls(argv):
    return [c.strip("\n").split("\n") for c in argv.split("---") if c.strip()]


def output_of(call):
    return call[call.index("--output") + 1]


@pytest.mark.parametrize("secrets", [{}, CREDS], ids=["no-creds", "creds"])
@pytest.mark.parametrize("compression", [None, "gzip"], ids=["not-passed", "gzip"])
@pytest.mark.parametrize("wf,step,inputs,env", CASES, ids=[f"{c[0]}:{c[1]}" for c in CASES])
def test_default_runs_what_master_ran(tmp_path, base_root, wf, step, inputs, env, compression, secrets):
    new_inputs = dict(inputs) if compression is None else dict(inputs, compression=compression, compression_level=7)
    before = run(tmp_path / "base", wf, step, inputs, env, secrets, workflow_root=base_root)
    after = run(tmp_path / "new", wf, step, new_inputs, env, secrets)
    assert before[0] == 0
    assert after == before


@pytest.mark.parametrize("step", BUILD_IMAGE_STEPS)
def test_zstd_build_image_output(tmp_path, step):
    inputs = dict(BUILD_IMAGE_INPUTS, compression="zstd", compression_level=7)
    rc, argv = run(tmp_path / "w", BUILD_IMAGE, step, inputs, {"IMAGE_NAME": "supervisely/my-app"})
    assert rc == 0
    tag = "latest" if step.endswith(":latest") else "1.2.3"
    assert [output_of(c) for c in calls(argv)] == [f"type=image,name=docker.io/supervisely/my-app:{tag},push=true{ZSTD_OUTPUT}"]


@pytest.mark.parametrize("tag", ["6.74.34", "latest"])
def test_zstd_template_push_output(tmp_path, tag):
    step = "Build and push Docker Image ${{ env.IMAGE_NAME }}:" + ("latest" if tag == "latest" else "${{ env.TAG_VERSION }}")
    inputs = dict(TEMPLATE_INPUTS, compression="zstd", compression_level=7)
    rc, argv = run(tmp_path / "w", TEMPLATE, step, inputs, TEMPLATE_ENV)
    assert rc == 0
    assert [output_of(c) for c in calls(argv)] == [f"type=image,name=docker.io/supervisely/my-app:{tag},push=true{ZSTD_OUTPUT}"]


def test_zstd_keeps_the_scanned_archive_as_it_was(tmp_path):
    inputs = dict(TEMPLATE_INPUTS, compression="zstd", compression_level=7)
    rc, argv = run(tmp_path / "w", TEMPLATE, "Build image archive for checks", inputs, TEMPLATE_ENV)
    assert rc == 0
    assert [output_of(c) for c in calls(argv)] == ["type=docker,name=supervisely/my-app:6.74.34,dest=image.tar"]


@pytest.mark.parametrize("secrets", [{}, CREDS], ids=["no-creds", "creds"])
def test_zstd_skopeo_pushes_the_scanned_archive_as_zstd_oci(tmp_path, secrets):
    inputs = dict(TEMPLATE_INPUTS, compression="zstd", compression_level=7)
    rc, argv = run(tmp_path / "w", TEMPLATE, "Push scanned image archive", inputs, TEMPLATE_ENV, secrets)
    assert rc == 0
    creds = ["--dest-creds", "u:t0k"] if secrets else []
    assert calls(argv) == [[
        "skopeo", "copy", *creds,
        "--format", "oci", "--dest-compress-format", "zstd", "--dest-compress-level", "7",
        "docker-archive:image.tar", "docker://docker.io/supervisely/my-app:6.74.34",
    ]]


def test_compression_level_is_passed_on(tmp_path):
    inputs = dict(BUILD_IMAGE_INPUTS, compression="zstd", compression_level=3)
    rc, argv = run(tmp_path / "w", BUILD_IMAGE, BUILD_IMAGE_STEPS[0], inputs, {"IMAGE_NAME": "supervisely/my-app"})
    assert rc == 0
    assert output_of(calls(argv)[0]).endswith(",compression=zstd,compression-level=3,force-compression=true,oci-mediatypes=true")


@pytest.mark.parametrize("wf", [BUILD_IMAGE, TEMPLATE])
@pytest.mark.parametrize(
    "compression,level",
    [("brotli", 7), ("ZSTD", 7), ("zstd", 0), ("zstd", 23), ("zstd", ""), ("zstd", "7,push=false")],
)
def test_bad_compression_inputs_fail_before_any_build(tmp_path, wf, compression, level):
    proc, exported = run_step(
        wf, JOB, PREPARE, tmp_path, inputs={"compression": compression, "compression_level": level},
    )
    assert proc.returncode == 1
    assert exported == {}


def _docker_archive(path, gzip_layer):
    layer = io.BytesIO()
    with tarfile.open(fileobj=layer, mode="w") as tar:
        data = b"hello\n"
        info = tarfile.TarInfo("hello.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    layer_tar = layer.getvalue()
    diff_id = "sha256:" + hashlib.sha256(layer_tar).hexdigest()
    config = json.dumps({
        "architecture": "amd64", "os": "linux", "config": {},
        "rootfs": {"type": "layers", "diff_ids": [diff_id]},
    }).encode()
    config_name = hashlib.sha256(config).hexdigest() + ".json"
    manifest = json.dumps([{"Config": config_name, "RepoTags": ["my-app:6.74.34"], "Layers": ["layer.tar"]}]).encode()
    files = {config_name: config, "layer.tar": gzip.compress(layer_tar) if gzip_layer else layer_tar,
             "manifest.json": manifest}
    with tarfile.open(path, "w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return diff_id


@pytest.mark.skipif(shutil.which("skopeo") is None, reason="skopeo not installed")
@pytest.mark.parametrize("gzip_layer", [False, True], ids=["plain-layer", "gzip-layer"])
def test_real_skopeo_writes_zstd_oci_from_a_docker_archive(tmp_path, gzip_layer):
    """The skopeo flags of the zstd push, run for real into a local OCI layout."""
    proc, exported = run_step(
        TEMPLATE, JOB, PREPARE, tmp_path, inputs={"compression": "zstd", "compression_level": 7},
    )
    assert proc.returncode == 0, proc.stderr
    diff_id = _docker_archive(tmp_path / "image.tar", gzip_layer)
    copy = subprocess.run(
        ["skopeo", "--insecure-policy", "copy", *exported["SKOPEO_COMPRESSION_OPT"].split(),
         f"docker-archive:{tmp_path / 'image.tar'}", f"oci:{tmp_path / 'oci'}:6.74.34"],
        capture_output=True, text=True,
    )
    assert copy.returncode == 0, copy.stderr

    def blob(digest):
        return (tmp_path / "oci" / "blobs" / "sha256" / digest.split(":", 1)[1]).read_bytes()

    index = json.loads((tmp_path / "oci" / "index.json").read_text())
    manifest = json.loads(blob(index["manifests"][0]["digest"]))
    assert manifest["mediaType"] == "application/vnd.oci.image.manifest.v1+json"
    [layer] = manifest["layers"]
    assert layer["mediaType"] == "application/vnd.oci.image.layer.v1.tar+zstd"
    assert blob(layer["digest"])[:4] == b"\x28\xb5\x2f\xfd"  # zstd frame magic
    assert json.loads(blob(manifest["config"]["digest"]))["rootfs"]["diff_ids"] == [diff_id]
