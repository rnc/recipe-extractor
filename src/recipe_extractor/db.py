# SPDX-License-Identifier: Apache-2.0
"""SQLite recipe library (PLAN.md section 10.2).

One short-lived connection per operation keeps this safe under FastAPI's
thread pool and leaves no open handle on a file that may live in a synced
folder. The default rollback journal is used (no ``-wal`` or ``-shm`` side
files), which is friendlier to sync tools than WAL.
"""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from recipe_extractor.models import (
    LibraryEntry,
    LibraryRecord,
    LibraryState,
    Recipe,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id            INTEGER PRIMARY KEY,
    url           TEXT NOT NULL,
    title         TEXT NOT NULL,
    extracted_at  TEXT NOT NULL,
    edited_at     TEXT,
    state         TEXT NOT NULL
        CHECK(state IN ('extracted', 'editing', 'final')),
    recipe_json   TEXT NOT NULL,
    previous_json TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_recipes_url ON recipes(url);
"""

_ENTRY_COLUMNS = "id, url, title, state, extracted_at, edited_at"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _entry(row: sqlite3.Row) -> LibraryEntry:
    return LibraryEntry(
        id=row["id"],
        url=row["url"],
        title=row["title"],
        state=row["state"],
        extracted_at=row["extracted_at"],
        edited_at=row["edited_at"],
    )


def _record(row: sqlite3.Row) -> LibraryRecord:
    return LibraryRecord(
        **_entry(row).model_dump(),
        recipe=Recipe.model_validate_json(row["recipe_json"]),
        has_previous=row["previous_json"] is not None,
    )


class RecipeLibrary:
    """Persistent store of extracted and edited recipes, one row per source URL."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # commit on success, roll back on error
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Library was written by a newer version (schema {version}); "
                    "please upgrade recipe-extractor."
                )
            conn.executescript(_SCHEMA)
            conn.execute("PRAGMA user_version = 1")
        logger.debug("library schema ready version=%d", SCHEMA_VERSION)

    def _fetch_row(self, conn: sqlite3.Connection, record_id: int) -> sqlite3.Row | Any:
        return conn.execute(
            "SELECT * FROM recipes WHERE id = ?", (record_id,)
        ).fetchone()

    def list_entries(self) -> list[LibraryEntry]:
        """All saved recipes, most recently touched first, without bodies."""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_ENTRY_COLUMNS} FROM recipes "  # noqa: S608
                "ORDER BY COALESCE(edited_at, extracted_at) DESC, id DESC"
            ).fetchall()
        return [_entry(row) for row in rows]

    def get(self, record_id: int) -> LibraryRecord | None:
        with self._connect() as conn:
            row = self._fetch_row(conn, record_id)
        return _record(row) if row else None

    def get_by_url(self, url: str) -> LibraryRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM recipes WHERE url = ?", (url,)).fetchone()
        return _record(row) if row else None

    def create(self, url: str, recipe: Recipe) -> LibraryRecord:
        """Insert a freshly extracted recipe (state 'extracted')."""
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO recipes (url, title, extracted_at, state, recipe_json) "
                "VALUES (?, ?, ?, 'extracted', ?)",
                (url, recipe.title, _now(), recipe.model_dump_json()),
            )
            row = self._fetch_row(conn, int(cursor.lastrowid or 0))
        logger.info("library created id=%d", row["id"])
        return _record(row)

    def save(
        self,
        record_id: int,
        recipe: Recipe,
        state: LibraryState,
        *,
        keep_previous: bool = False,
    ) -> LibraryRecord | None:
        """Auto-save an edit. Optionally keep the replaced version for Restore."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE recipes SET title = ?, state = ?, edited_at = ?, "
                "previous_json = CASE WHEN ? THEN recipe_json ELSE previous_json END, "
                "recipe_json = ? WHERE id = ?",
                (
                    recipe.title,
                    state,
                    _now(),
                    keep_previous,
                    recipe.model_dump_json(),
                    record_id,
                ),
            )
            row = self._fetch_row(conn, record_id)
        if row is None:
            return None
        logger.info(
            "library saved id=%d state=%s keep_previous=%s",
            record_id,
            state,
            keep_previous,
        )
        return _record(row)

    def replace_with_extraction(
        self, record_id: int, recipe: Recipe
    ) -> LibraryRecord | None:
        """Overwrite with a fresh extraction; the old version goes to Restore."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE recipes SET title = ?, state = 'extracted', "
                "extracted_at = ?, edited_at = NULL, previous_json = recipe_json, "
                "recipe_json = ? WHERE id = ?",
                (recipe.title, _now(), recipe.model_dump_json(), record_id),
            )
            row = self._fetch_row(conn, record_id)
        if row is None:
            return None
        logger.info("library re-extracted id=%d", record_id)
        return _record(row)

    def restore(self, record_id: int) -> LibraryRecord | None:
        """Swap the recipe with its previous version (so Restore can be undone)."""
        with self._connect() as conn:
            row = self._fetch_row(conn, record_id)
            if row is None or row["previous_json"] is None:
                return None
            previous = Recipe.model_validate_json(row["previous_json"])
            conn.execute(
                "UPDATE recipes SET title = ?, state = 'editing', edited_at = ?, "
                "recipe_json = previous_json, previous_json = recipe_json "
                "WHERE id = ?",
                (previous.title, _now(), record_id),
            )
            row = self._fetch_row(conn, record_id)
        logger.info("library restored id=%d", record_id)
        return _record(row)

    def delete(self, record_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM recipes WHERE id = ?", (record_id,))
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("library deleted id=%d", record_id)
        return deleted
