"""Packaging metadata assertions for the built wheel."""

import shutil
import subprocess
import zipfile
from email import message_from_string
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet

PROJECT_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required to build the wheel")


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory) -> Path:
    """Build a wheel from the project source and return its path."""
    out_dir = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out_dir), str(PROJECT_ROOT)],
        check=True,
        capture_output=True,
    )
    wheels = list(out_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"
    return wheels[0]


def _wheel_metadata(wheel: Path, name: str) -> str:
    with zipfile.ZipFile(wheel) as archive:
        (path,) = [n for n in archive.namelist() if n.endswith(f".dist-info/{name}")]
        return archive.read(path).decode()


def test_wheel_filename_is_python3_only(built_wheel):
    """The wheel is tagged py3, not the default py2.py3."""
    tag = built_wheel.stem.split("-")[2]
    assert tag == "py3", f"unexpected python tag in {built_wheel.name}"


def test_wheel_tags_exclude_python2(built_wheel):
    """No Tag line in WHEEL advertises Python 2 compatibility."""
    tags = [
        line.split(":", 1)[1].strip()
        for line in _wheel_metadata(built_wheel, "WHEEL").splitlines()
        if line.startswith("Tag:")
    ]
    assert tags == ["py3-none-any"]


def test_wheel_requires_python_declares_310_floor(built_wheel):
    """METADATA advertises a Python floor of 3.10 to installers."""
    requires_python = message_from_string(_wheel_metadata(built_wheel, "METADATA"))["Requires-Python"]
    assert requires_python is not None, "wheel METADATA has no Requires-Python field"

    specifier = SpecifierSet(requires_python)
    assert "3.10" in specifier
    assert "3.12" in specifier
    assert "3.9" not in specifier
    assert "2.7" not in specifier
