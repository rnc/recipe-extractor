#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Open a KDE Konsole window, activate the project's virtualenv and run
# recipe-extractor. The window stays open (--hold) after the server stops.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The venv is either a real ./.venv directory, or ./.venv is a pointer file
# naming a virtualenv under ~/.virtualenvs (zsh-autoswitch-virtualenv style).
if [[ -d "$repo/.venv" ]]; then
    venv="$repo/.venv"
elif [[ -f "$repo/.venv" ]]; then
    venv="$HOME/.virtualenvs/$(<"$repo/.venv")"
else
    echo "No .venv found in $repo" >&2
    exit 1
fi

if [[ ! -x "$venv/bin/recipe-extractor" ]]; then
    echo "recipe-extractor not installed in $venv" >&2
    exit 1
fi

exec konsole --hold --workdir "$repo" -e bash -c '
    source "$1/bin/activate"
    exec recipe-extractor
' _ "$venv"
