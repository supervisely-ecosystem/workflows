"""build_image_from_template.yml "Validate tag in Docker Hub" (QUESTIONS 3.8)."""

import pytest

from workflow_runner import fake_bin, run_step

STEP = ("build_image_from_template.yml", "build-and-push", "Validate tag in Docker Hub")


@pytest.fixture
def tag_check(tmp_path):
    bin_dir = tmp_path / "bin"
    codes = tmp_path / "codes"
    calls = tmp_path / "curl_calls"
    sleeps = tmp_path / "sleeps"
    # fake curl: answer with the next HTTP code from the list; "fail" = no answer
    fake_bin(bin_dir, "curl", f"""
echo "$@" >> {calls}
code=$(head -n1 {codes}); sed -i.bak '1d' {codes}
if [ "$code" = "fail" ]; then printf '000'; exit 6; fi
printf '%s' "$code"
""")
    fake_bin(bin_dir, "sleep", f'echo "$1" >> {sleeps}\n')

    def _run(sequence, skip=False):
        codes.write_text("\n".join(sequence) + "\n")
        proc, exported = run_step(
            *STEP, tmp_path,
            inputs={"skip_tag_check": skip},
            env={"IMAGE_NAME": "supervisely/my-app", "TAG_VERSION": "6.74.34"},
            fake_bin_dir=bin_dir,
        )
        n_calls = len(calls.read_text().splitlines()) if calls.exists() else 0
        slept = sleeps.read_text().split() if sleeps.exists() else []
        return proc, exported, n_calls, slept

    return _run


def test_existing_tag(tag_check):
    proc, exported, n, slept = tag_check(["200"])
    assert proc.returncode == 0
    assert exported["TAG_EXISTS"] == "true"
    assert n == 1 and slept == []


def test_missing_tag(tag_check):
    proc, exported, n, _ = tag_check(["404"])
    assert proc.returncode == 0
    assert exported["TAG_EXISTS"] == "false"


@pytest.mark.parametrize("transient", ["429", "502", "503", "fail"])
def test_transient_answer_is_retried(tag_check, transient):
    """A single 429 used to fail the build job and therefore block the release."""
    proc, exported, n, slept = tag_check([transient, transient, "404"])
    assert proc.returncode == 0, proc.stderr
    assert exported["TAG_EXISTS"] == "false"
    assert n == 3
    assert slept == ["15", "30"]


def test_gives_up_after_five_attempts(tag_check):
    proc, exported, n, slept = tag_check(["429"] * 6)
    assert proc.returncode == 1
    assert "HTTP 429" in proc.stderr
    assert n == 5
    assert slept == ["15", "30", "45", "60"]
    assert "TAG_EXISTS" not in exported


def test_other_codes_fail_immediately(tag_check):
    proc, exported, n, slept = tag_check(["401"])
    assert proc.returncode == 1
    assert n == 1 and slept == []


def test_skip_input(tag_check):
    proc, exported, n, _ = tag_check(["500"], skip=True)
    assert proc.returncode == 0
    assert exported["TAG_EXISTS"] == "false"
    assert n == 0
