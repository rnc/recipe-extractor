# SPDX-License-Identifier: Apache-2.0
"""Code-quality checks that run as part of the test suite.

Inspired by cekit/tests/test_qa.py (same pattern: run the formatters via
subprocess so a plain `pytest` catches style regressions, not just CI).

We run black --check and ruff check against the repo root.  mypy is
intentionally excluded here; it is slower, needs the package installed, and is
already a separate CI step.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _tool_skip(name: str) -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        shutil.which(name) is None,
        reason=f"{name} not found on PATH",
    )


@_tool_skip("black")
def test_black() -> None:
    """black --check must report no formatting differences."""
    black = shutil.which("black")
    assert black is not None
    result = subprocess.run(  # noqa: S603
        [black, "--check", "--diff", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode:
        pytest.fail(
            f"black reported formatting differences:\n{result.stdout}\n{result.stderr}",
            pytrace=False,
        )


@_tool_skip("ruff")
def test_ruff() -> None:
    """ruff check must report no lint errors."""
    ruff = shutil.which("ruff")
    assert ruff is not None
    result = subprocess.run(  # noqa: S603
        [ruff, "check", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode:
        pytest.fail(
            f"ruff reported lint errors:\n{result.stdout}\n{result.stderr}",
            pytrace=False,
        )
