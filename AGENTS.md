# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Source of truth
- The committed codebase, `pyproject.toml`, `README.md`, and the test suite are the source of truth for features and behavior.

## Commands (run from the repo root, inside the project venv)
- Environment setup / activation:
  - With uv: `uv sync --extra dev` creates `.venv/` and installs all dependencies and development tools.
  - If using `~/.virtualenvs/` (e.g. with zsh-autoswitch-virtualenv and `.venv` pointer file): `V=~/.virtualenvs/$(cat .venv); export PATH=$V/bin:$PATH`.
  - Standard venv: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.
- All checks (all must pass): `black --check . && ruff check . && mypy && pytest && pip-audit`
- Formatting & linting script: `python scripts/run_formatters.py` (formats in-place) or `python scripts/run_formatters.py --check` (check only).
- Single test: `pytest tests/test_api.py::test_health`
- Live-site tests are opt-in: `pytest -m live`. They are excluded by `addopts` and CI.
- Sample snapshot tool: `python scripts/snapshot_samples.py` (downloads offline snapshots to `tests/samples_private/` based on `tests/samples/manifest.toml`).
- Run the app: `recipe-extractor` (serves http://127.0.0.1:8000).
- Lint workflow files after any `.github/` change: `uvx --from actionlint-py actionlint .github/workflows/*.yml && uvx zizmor .github/workflows/`. CI runs the same checks in the `lint-workflows` job.

## GitHub Actions pinning (mandatory)
- Every `uses:` must be a full 40-character commit SHA followed by a version comment: `uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`. Never use tags, branches or short SHAs.
- Resolve a SHA: `git ls-remote https://github.com/<owner>/<repo>.git "refs/tags/<tag>" "refs/tags/<tag>^{}"`. If two lines print, use the `^{}` one.
- Dependabot (`.github/dependabot.yml`) updates the pins weekly with a 7-day cooldown. Do not bump them by hand without a reason.
- The zizmor step uses `advanced-security: false` and `annotations: true`. Without that it uploads SARIF and needs `security-events: write`, which the read-only workflow does not have.
- Workflows need top-level `permissions: contents: read`, checkout with `persist-credentials: false`, and no `${{ }}` expressions inside `run:` (pass via `env:`).

## Non-obvious conventions
- **Test client dependency:** `fastapi.testclient` needs `httpx2`, which is in the `dev` extra. Do not add plain `httpx`: it is unmaintained (last release 2024-12) and the security policy rejects it.
- **Safe network fetching:** Use `requests` via the safe-fetch wrapper `recipe_extractor.fetch.SafeFetcher` with SSRF protection (blocks private IP ranges, cloud metadata, and unsafe schemes).
- **Formatting split:** `black` formats and `ruff` only lints. Do not enable `ruff format` or any ruff rule that conflicts with black.
- `mypy` runs in strict mode over `src` and `tests`, so test functions need `-> None`.
- Ruff has the `S` (bandit) rules on. Tests may use `assert`. Any `subprocess` call needs an explicit `# noqa: S603` with a reason.
- Server binds to `127.0.0.1` only (`HOST` in `src/recipe_extractor/main.py`, covered by a test). Never `0.0.0.0`.
- The static mount in `main.py` is registered last so it cannot shadow `/api` routes. Keep it last.
- Frontend files go in `src/recipe_extractor/static/`. They are vendored and have no CDN links. Render extracted text with `textContent`, never `innerHTML`.
- Every source file starts with `SPDX-License-Identifier: Apache-2.0` (a comment, or an HTML comment in HTML).
- `tests/samples_private/` is gitignored on purpose. It holds local snapshots of sample recipe pages. Never track, copy, or quote its contents, and never write remote URLs of private samples into committed files. `tests/test_repo_hygiene.py` enforces this.
- **Persistence is off unless asked for:** the module-level `app` in `main.py` has no library, so importing it (as tests do) can never touch a real database. Only the `recipe-extractor` command enables it, via `--database` (default: the user data directory via `platformdirs`). Tests that need a library call `create_app(db_path=tmp_path / ...)`, and CLI tests must monkeypatch `default_db_path`. There is no env var or config file by design.
- **`--database` values:** only the exact words `default` and `disabled` are special; anything else must be an absolute path. Do not loosen this, it stops a typo creating a stray file.
- **Never log recipe bodies, ingredient text or `data:` URIs.** Structured logging records operational data only.
- Public tests and CI use synthetic fixtures only, with no network.
- Python floor is 3.12 (required by `pint`). The target runtime is 3.14. Do not use syntax newer than 3.12 without raising the floor.
