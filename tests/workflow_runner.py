"""Run a single `run:` step of a workflow file locally with bash.

Only what the tests need: `${{ ... }}` expressions of the form inputs.X,
env.X, secrets.X, github.X and github.event.inputs.X are substituted from the
given contexts (missing values become ""), job-level and step-level `env:` are
exported, and a directory of fake executables can be put first on PATH. The
script runs with `bash -e`, GitHub's default shell for `run:` on Linux.
"""

import os
import re
import stat
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPR = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")


def load_workflow(name, root=ROOT):
    return yaml.safe_load((Path(root) / ".github" / "workflows" / name).read_text())


def find_step(workflow, job, step_name):
    for step in workflow["jobs"][job]["steps"]:
        if step.get("name") == step_name:
            return step
    raise KeyError(step_name)


def render(text, contexts):
    def value(match):
        expr = match.group(1)
        parts = expr.split(".")
        if parts[0] == "github" and parts[1:3] == ["event", "inputs"]:
            ctx, key = contexts.get("github_event_inputs", {}), parts[3]
        elif parts[0] in ("inputs", "env", "secrets", "github") and len(parts) == 2:
            ctx, key = contexts.get(parts[0], {}), parts[1]
        else:
            raise ValueError(f"unsupported expression in test runner: {expr}")
        v = ctx.get(key, "")
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)

    return EXPR.sub(value, text)


def fake_bin(directory, name, script):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/bash\n" + script)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def run_step(workflow_name, job, step_name, workdir, inputs=None, env=None, secrets=None,
             github=None, fake_bin_dir=None, workflow_root=ROOT):
    workflow = load_workflow(workflow_name, workflow_root)
    step = find_step(workflow, job, step_name)
    workdir = Path(workdir)
    github_env = workdir / "_github_env"
    github_output = workdir / "_github_output"
    github_env.touch()
    github_output.touch()

    contexts = {
        "inputs": inputs or {},
        "secrets": secrets or {},
        "github": {"workspace": str(workdir), **(github or {})},
        "env": dict(env or {}),
    }
    shell_env = {
        "PATH": (f"{fake_bin_dir}:" if fake_bin_dir else "") + os.environ["PATH"],
        "HOME": str(workdir),
        "GITHUB_ENV": str(github_env),
        "GITHUB_OUTPUT": str(github_output),
        "GITHUB_WORKSPACE": str(workdir),
        "GITHUB_REPOSITORY": (github or {}).get("repository", "supervisely-ecosystem/my-app"),
        "RUNNER_TEMP": str(workdir / "_runner_temp"),
        **{k: str(v) for k, v in (env or {}).items()},
    }
    for block in (workflow.get("env"), workflow["jobs"][job].get("env"), step.get("env")):
        for key, val in (block or {}).items():
            rendered = render(str(val), contexts)
            shell_env[key] = rendered
            contexts["env"][key] = rendered

    script = render(step["run"], contexts)
    proc = subprocess.run(
        ["bash", "-e", "-c", script], cwd=workdir, env=shell_env, capture_output=True, text=True
    )
    exported = dict(
        line.split("=", 1) for line in github_env.read_text().splitlines() if "=" in line
    )
    return proc, exported
