"""build_image_from_template.yml "Validate tag in Docker Hub" (QUESTIONS 3.8).

The tag is read from the registry with the credentials that push the image. Docker Hub's public
API answers 404 for every tag of a private repository, so the old anonymous check took existing
tags of private images for missing ones and rebuilt and overwrote them.
"""

import pytest

from workflow_runner import fake_bin, run_step

STEP = ("build_image_from_template.yml", "build-and-push", "Validate tag in Docker Hub")

MANIFEST_UNKNOWN = "reading manifest 6.74.34 in docker.io/supervisely/my-app: manifest unknown"
DENIED = "reading manifest 6.74.34 in docker.io/supervisely/my-app: requested access to the resource is denied"
TRANSIENT = {
    "429": "reading manifest 6.74.34 in docker.io/supervisely/my-app: toomanyrequests: You have reached your pull rate limit",
    "502": "reading manifest 6.74.34 in docker.io/supervisely/my-app: received unexpected HTTP status: 502 Bad Gateway",
    "network": 'pinging container registry registry-1.docker.io: Get "https://registry-1.docker.io/v2/": dial tcp: i/o timeout',
}


@pytest.fixture
def tag_check(tmp_path):
    bin_dir = tmp_path / "bin"
    answers = tmp_path / "answers"
    calls = tmp_path / "skopeo_calls"
    curl_calls = tmp_path / "curl_calls"
    sleeps = tmp_path / "sleeps"
    # fake skopeo: exit with the next "<code>|<stderr>" from the list (skopeo exits 2 when the
    # registry does not know the manifest)
    fake_bin(bin_dir, "skopeo", f"""
echo "$*" >> {calls}
line=$(head -n1 {answers}); sed -i.bak '1d' {answers}
code=${{line%%|*}}; msg=${{line#*|}}
if [ -n "$msg" ]; then echo "time=\\"2026-11-19T00:00:00Z\\" level=fatal msg=\\"$msg\\"" >&2; fi
exit "$code"
""")
    # the public Docker Hub API: 404 for any tag of a private repository
    fake_bin(bin_dir, "curl", f"""
echo "$@" >> {curl_calls}
printf '404'
""")
    fake_bin(bin_dir, "sleep", f'echo "$1" >> {sleeps}\n')

    def _run(sequence, skip=False, secrets=None):
        answers.write_text("\n".join(sequence) + "\n")
        proc, exported = run_step(
            *STEP, tmp_path,
            inputs={"skip_tag_check": skip},
            env={"IMAGE_NAME": "supervisely/my-app", "TAG_VERSION": "6.74.34"},
            secrets=secrets or {},
            fake_bin_dir=bin_dir,
        )
        argv = calls.read_text().splitlines() if calls.exists() else []
        slept = sleeps.read_text().split() if sleeps.exists() else []
        return proc, exported, argv, slept

    return _run


def test_existing_tag_of_a_private_image(tag_check):
    proc, exported, argv, slept = tag_check(["0|"])
    assert proc.returncode == 0, proc.stderr
    assert exported["TAG_EXISTS"] == "true", "an existing tag would be rebuilt and overwritten"
    assert len(argv) == 1 and slept == []
    assert "--raw docker://docker.io/supervisely/my-app:6.74.34" in argv[0]


def test_missing_tag(tag_check):
    proc, exported, argv, _ = tag_check([f"2|{MANIFEST_UNKNOWN}"])
    assert proc.returncode == 0, proc.stderr
    assert exported["TAG_EXISTS"] == "false"
    assert len(argv) == 1


def test_runner_credentials_by_default(tag_check):
    _, _, argv, _ = tag_check(["0|"])
    assert "--creds" not in argv[0]


def test_secrets_are_used_when_given(tag_check):
    _, exported, argv, _ = tag_check(["0|"], secrets={"DOCKERHUB_USERNAME": "u", "DOCKERHUB_TOKEN": "t0k"})
    assert exported["TAG_EXISTS"] == "true"
    assert "--creds u:t0k" in argv[0]


@pytest.mark.parametrize("transient", sorted(TRANSIENT))
def test_transient_answer_is_retried(tag_check, transient):
    """A single 429 used to fail the build job and therefore block the release."""
    answer = f"1|{TRANSIENT[transient]}"
    proc, exported, argv, slept = tag_check([answer, answer, f"2|{MANIFEST_UNKNOWN}"])
    assert proc.returncode == 0, proc.stderr
    assert exported["TAG_EXISTS"] == "false"
    assert len(argv) == 3
    assert slept == ["15", "30"]


def test_gives_up_after_five_attempts(tag_check):
    proc, exported, argv, slept = tag_check([f"1|{TRANSIENT['429']}"] * 6)
    assert proc.returncode == 1
    assert "toomanyrequests" in proc.stderr
    assert len(argv) == 5
    assert slept == ["15", "30", "45", "60"]
    assert "TAG_EXISTS" not in exported


@pytest.mark.parametrize("refusal", [DENIED, "unable to retrieve auth token: invalid username/password: unauthorized: incorrect username or password"])
def test_refused_credentials_fail_immediately(tag_check, refusal):
    """Never read as a missing tag: that is how existing tags got overwritten."""
    proc, exported, argv, slept = tag_check([f"1|{refusal}"])
    assert proc.returncode == 1
    assert "credentials" in proc.stderr
    assert len(argv) == 1 and slept == []
    assert "TAG_EXISTS" not in exported


def test_skip_input(tag_check):
    proc, exported, argv, _ = tag_check(["1|"], skip=True)
    assert proc.returncode == 0
    assert exported["TAG_EXISTS"] == "false"
    assert argv == []
