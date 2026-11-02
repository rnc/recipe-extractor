# Recipe Extractor

A self-contained web app to extract recipes from websites, edit them in a clean structured interface, and print or save them to PDF without adverts, stories, or clutter.

## Features

- **Extract by URL:** Fetches recipes using structured Schema.org JSON-LD data and site-specific scrapers.
- **Image handling:** Automatically extracts recipe images, embeds them safely, and lets you select which image to print.
- **Structured editing:**
  - Edit title, servings, prep time, cook time, and total time.
  - Reorder, add, and delete ingredients and method steps (with Up/Down buttons and undo support).
  - Support for ingredient section groupings (e.g. "For the sauce").
  - Add extra notes and cooking instructions.
- **Saved recipe library:** Every recipe you extract is saved automatically, and so are your edits, in a single SQLite file. Re-open, delete, re-extract (with a summary of what changed) or restore the previous version from the "Saved recipes" panel. Extracting a URL you have already saved loads your saved copy and never overwrites it.
- **Browser Print & PDF:** A dedicated `@media print` stylesheet formatted for A4 printing and native "Save as PDF", keeping source attribution and clean typography.
- **Security:** Built-in SSRF protection blocking private network ranges, cloud metadata IPs, and unsafe file schemes.

## Installation and Running

Requires Python 3.12 or newer (Python 3.14 recommended).

### 1. Set up virtual environment and install

The recommended way is [uv](https://docs.astral.sh/uv/). The repository includes a `uv.lock` file, so every machine gets the same dependency versions, and uv downloads a suitable Python if the system one is too old.

```sh
uv sync --extra dev
source .venv/bin/activate
```

This creates `.venv/` in the project directory and installs the app (editable) together with the development tools. Leave out `--extra dev` if you only want to run the app.

If you use [zsh-autoswitch-virtualenv](https://github.com/MichaelAquilina/zsh-autoswitch-virtualenv), `uv.lock` makes it detect a uv project. In that case run `mkvenv --extra dev` (it passes the options to `uv sync`) instead of the two commands above, and the environment then activates whenever you `cd` into the directory.

Without uv, plain pip also works. It ignores `uv.lock`, so versions may differ:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

To change dependencies, edit `pyproject.toml`, run `uv lock`, and commit both `pyproject.toml` and `uv.lock`. To upgrade everything to the newest allowed versions, run `uv lock --upgrade`.

### 2. Run the application

```sh
recipe-extractor
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your web browser.

Options:

| Option | Meaning |
|---|---|
| `--database=default` | The default. Saves to `~/.local/share/recipe-extractor/recipes.db` (the OS user data directory). |
| `--database=disabled` | Nothing is saved. |
| `--database=/absolute/path/recipes.db` | Saves to that file, for example a synced folder. The path must be absolute, and a value such as `foo` or `disable` is rejected. |
| `--debug` | Log at DEBUG level instead of INFO. |

On start-up the app logs which library it is using, for example `Library: /home/you/.local/share/recipe-extractor/recipes.db`. The setting is not remembered between runs, so if you use a custom path, put it in a shell alias.

The library is a plain file: back it up by copying it. It can be a symlink into a synced folder, but only run one copy of the app at a time against the same file.

## Development & Testing

Run all checks:

```sh
black --check .
ruff check .
mypy
pytest
pip-audit
```

### Testing with Sample Recipes

1. List sample URLs and expectations in `tests/samples/manifest.toml`.
2. Download offline snapshots and images:
   ```sh
   python scripts/snapshot_samples.py
   ```
3. Run snapshot tests (offline):
   ```sh
   pytest
   ```
4. Run live site tests (opt-in network tests):
   ```sh
   pytest -m live
   ```

## Licence & Etiquette

- **Licence:** Apache-2.0. See [LICENSE](LICENSE).
- **Personal Use:** Recipe Extractor is intended for personal recipe organization. Extracted text retains source URL attribution on printed copies.
