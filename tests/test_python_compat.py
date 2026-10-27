import py_compile
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    "release.py",
    "release_models.py",
    "update_models.py",
    "get_inputs.py",
    "scripts/resolve_release_tag.py",
    "scripts/get_image_packages.py",
]


@pytest.mark.parametrize("script", SCRIPTS)
def test_scripts_compile_on_current_interpreter(script):
    py_compile.compile(str(ROOT / script), doraise=True)


@pytest.mark.parametrize("python", ["python3.10", "python3.11"])
def test_release_py_compiles_on_older_pythons(python):
    """The runner's .release_venv may be rebuilt from a distro Python (3.10 on Ubuntu 22.04)."""
    exe = shutil.which(python)
    if exe is None:
        pytest.skip(f"{python} not installed")
    result = subprocess.run(
        [exe, "-m", "py_compile", str(ROOT / "release.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
