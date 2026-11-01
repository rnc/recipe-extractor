#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the project formatters (black) and linter (ruff) against the repo.

Inspired by cekit/support/run_formatter.py, adapted for this project's tool
stack (black + ruff; no isort, no flake8).

Usage:
    python scripts/run_formatters.py           # format in-place
    python scripts/run_formatters.py --check   # check only, exit non-zero if needed
    python scripts/run_formatters.py --check --diff  # also print a unified diff
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _find(name: str) -> str:
    """Return the full path to *name* on PATH, or abort with a clear message."""
    path = shutil.which(name)
    if path is None:
        print(f"error: {name!r} not found on PATH", file=sys.stderr)
        sys.exit(1)
    return path


def _run(cmd: list[str]) -> int:
    """Run *cmd*, stream its output, and return the exit code."""
    result = subprocess.run(cmd, cwd=ROOT, check=False)  # noqa: S603
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run black and ruff against the repo using the project settings."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Don't write files back; exit non-zero if changes are needed.",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="With --check: print a unified diff of what would change (black only).",
    )
    args = parser.parse_args()

    black = _find("black")
    ruff = _find("ruff")

    black_cmd = [black, "."]
    if args.check:
        black_cmd += ["--check"]
        if args.diff:
            black_cmd += ["--diff"]

    # ruff check is always read-only; --fix applies changes when not in check mode
    ruff_cmd = [ruff, "check", "."]
    if not args.check:
        ruff_cmd += ["--fix"]

    for cmd in [black_cmd, ruff_cmd]:
        rc = _run(cmd)
        if rc:
            sys.exit(rc)

    sys.exit(0)


if __name__ == "__main__":
    main()
