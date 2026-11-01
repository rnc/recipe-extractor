# SPDX-License-Identifier: Apache-2.0
"""Tests for the SQLite recipe library."""

import sqlite3
from pathlib import Path

import pytest

from recipe_extractor.db import SCHEMA_VERSION, RecipeLibrary
from recipe_extractor.models import Ingredient, Recipe, Step

URL = "https://example.com/cake"


def make_recipe(title: str = "Cake") -> Recipe:
    return Recipe(
        title=title,
        source_url=URL,
        ingredients=[Ingredient(raw="200g flour")],
        steps=[Step(text="Mix.")],
    )


@pytest.fixture
def library(tmp_path: Path) -> RecipeLibrary:
    return RecipeLibrary(tmp_path / "sub" / "recipes.db")


def test_creates_parent_directory_and_schema(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "recipes.db"
    RecipeLibrary(path)
    assert path.exists()
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_rejects_database_from_newer_version(tmp_path: Path) -> None:
    path = tmp_path / "recipes.db"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError, match="newer version"):
        RecipeLibrary(path)


def test_create_and_get_round_trip(library: RecipeLibrary) -> None:
    record = library.create(URL, make_recipe())
    assert record.state == "extracted"
    assert record.edited_at is None
    assert not record.has_previous
    assert library.get(record.id) == record
    assert library.get_by_url(URL) == record
    assert library.get(999) is None
    assert library.get_by_url("https://other.example") is None


def test_url_is_unique(library: RecipeLibrary) -> None:
    library.create(URL, make_recipe())
    with pytest.raises(sqlite3.IntegrityError):
        library.create(URL, make_recipe())


def test_save_updates_recipe_state_and_title(library: RecipeLibrary) -> None:
    record = library.create(URL, make_recipe())
    saved = library.save(record.id, make_recipe("Better cake"), "editing")
    assert saved is not None
    assert saved.title == "Better cake"
    assert saved.recipe.title == "Better cake"
    assert saved.state == "editing"
    assert saved.edited_at is not None
    assert not saved.has_previous
    assert library.save(999, make_recipe(), "editing") is None


def test_save_can_keep_previous_version(library: RecipeLibrary) -> None:
    record = library.create(URL, make_recipe("Original"))
    saved = library.save(record.id, make_recipe("Reset"), "editing", keep_previous=True)
    assert saved is not None and saved.has_previous

    restored = library.restore(record.id)
    assert restored is not None
    assert restored.recipe.title == "Original"
    # Restore swaps, so it can itself be undone.
    again = library.restore(record.id)
    assert again is not None
    assert again.recipe.title == "Reset"


def test_replace_with_extraction_keeps_old_version(library: RecipeLibrary) -> None:
    record = library.create(URL, make_recipe("Old"))
    library.save(record.id, make_recipe("My edits"), "editing")

    replaced = library.replace_with_extraction(record.id, make_recipe("Fresh"))
    assert replaced is not None
    assert replaced.recipe.title == "Fresh"
    assert replaced.state == "extracted"
    assert replaced.edited_at is None
    assert replaced.has_previous

    restored = library.restore(record.id)
    assert restored is not None
    assert restored.recipe.title == "My edits"


def test_restore_without_previous_returns_none(library: RecipeLibrary) -> None:
    record = library.create(URL, make_recipe())
    assert library.restore(record.id) is None
    assert library.restore(999) is None


def test_delete(library: RecipeLibrary) -> None:
    record = library.create(URL, make_recipe())
    assert library.delete(record.id) is True
    assert library.delete(record.id) is False
    assert library.get(record.id) is None


def test_list_entries_most_recent_first_without_bodies(
    library: RecipeLibrary,
) -> None:
    first = library.create("https://example.com/1", make_recipe("One"))
    second = library.create("https://example.com/2", make_recipe("Two"))
    library.save(first.id, make_recipe("One edited"), "editing")

    entries = library.list_entries()
    assert [e.id for e in entries] == [first.id, second.id]
    assert entries[0].title == "One edited"
    assert not hasattr(entries[0], "recipe")


def test_state_check_constraint(library: RecipeLibrary) -> None:
    with sqlite3.connect(library.path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO recipes (url, title, extracted_at, state, recipe_json) "
            "VALUES ('u', 't', 'now', 'bogus', '{}')"
        )


def test_data_survives_reopening(tmp_path: Path) -> None:
    path = tmp_path / "recipes.db"
    created = RecipeLibrary(path).create(URL, make_recipe())
    assert RecipeLibrary(path).get(created.id) == created
