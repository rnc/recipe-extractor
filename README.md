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
- **Browser Print & PDF:** A dedicated `@media print` stylesheet formatted for A4 printing and native "Save as PDF", keeping source attribution and clean typography.
- **Security:** Built-in SSRF protection blocking private network ranges, cloud metadata IPs, and unsafe file schemes.

## Installation and Running

Requires Python 3.12 or newer (Python 3.14 recommended).

### 1. Set up virtual environment and install

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Run the application

```sh
recipe-extractor
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your web browser.

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

- **Licence:** Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
- **Personal Use:** Recipe Extractor is intended for personal recipe organization. Extracted text retains source URL attribution on printed copies.
