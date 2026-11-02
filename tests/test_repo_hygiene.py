# SPDX-License-Identifier: Apache-2.0
"""Guard against publishing private sample snapshots (PLAN.md section 11)."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(),
    reason="needs a git checkout",
)
def test_no_private_samples_tracked() -> None:
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(  # noqa: S603
        [git, "ls-files", "tests/samples_private"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert result.stdout.strip() == ""


def test_samples_private_is_gitignored() -> None:
    lines = (ROOT / ".gitignore").read_text().splitlines()
    # No trailing slash: that form would not match a symlink to a private repo.
    assert "tests/samples_private" in lines
    assert "tests/samples_private/" not in lines
