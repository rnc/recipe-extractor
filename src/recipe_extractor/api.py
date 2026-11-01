# SPDX-License-Identifier: Apache-2.0
"""JSON API routes."""

import logging
import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from recipe_extractor import __version__
from recipe_extractor.db import RecipeLibrary
from recipe_extractor.extract import extract_recipe
from recipe_extractor.fetch import FetchError, SafeFetcher
from recipe_extractor.models import (
    ConvertRequest,
    ConvertResponse,
    ExtractRequest,
    ExtractResponse,
    LibraryEntry,
    LibraryRecord,
    LibrarySaveRequest,
    Recipe,
    ReExtractResponse,
)
from recipe_extractor.units import convert_recipe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

UnitSystem = Literal["original", "metric", "uk"]

EXTRACT_FAILED = "Could not extract recipe structured data from the provided page."


class Health(BaseModel):
    status: str
    version: str
    library: bool


def _library(request: Request) -> RecipeLibrary | None:
    """The recipe library, or None when persistence is disabled."""
    library: RecipeLibrary | None = getattr(request.app.state, "library", None)
    return library


def require_library(request: Request) -> RecipeLibrary:
    library = _library(request)
    if library is None:
        raise HTTPException(status_code=404, detail="The recipe library is disabled.")
    return library


@router.get("/health")
def health(request: Request) -> Health:
    """Liveness check; also confirms which version is running."""
    return Health(
        status="ok", version=__version__, library=_library(request) is not None
    )


def _fetch_and_extract(
    url: str, unit_system: UnitSystem
) -> tuple[Recipe, list[str], str]:
    """Fetch a URL safely and extract it. Returns recipe, warnings, final URL."""
    fetcher = SafeFetcher()
    target_url = url.strip()
    try:
        resource = fetcher.fetch(target_url)
        html_content = resource.text
        target_url = resource.url  # Use final URL after redirects
    except FetchError as e:
        logger.warning("Fetch failed for URL '%s': %s", target_url, e)
        raise HTTPException(
            status_code=400,
            detail=f"Unable to safely fetch the recipe URL: {e}",
        ) from e
    except Exception as e:
        logger.error("Unexpected error fetching URL '%s': %s", target_url, e)
        raise HTTPException(
            status_code=400,
            detail="An unexpected error occurred while fetching the URL.",
        ) from e

    try:
        recipe, warnings = extract_recipe(
            html_content,
            url=target_url,
            fetcher=fetcher,
            download_images=True,
            unit_system=unit_system,
        )
    except Exception as e:
        logger.warning("Recipe extraction failed for '%s': %s", target_url, e)
        raise HTTPException(
            status_code=422,
            detail=EXTRACT_FAILED,
        ) from e
    return recipe, warnings, target_url


@router.post("/extract", response_model=ExtractResponse)
def extract(request: ExtractRequest, http_request: Request) -> ExtractResponse:
    """Extract structured recipe data from a URL or raw HTML.

    With the library enabled, a new URL is saved at once (auto-save). A URL that
    is already saved returns the saved copy instead and is never overwritten.
    """
    if not request.url and not request.html:
        raise HTTPException(
            status_code=400,
            detail="Either 'url' or 'html' must be provided in the request.",
        )

    library = _library(http_request)

    if not request.url:
        # Pasted HTML has no source URL, so it cannot be saved (PLAN.md 10.2).
        assert request.html is not None  # noqa: S101 - narrowed by the check above
        try:
            recipe, warnings = extract_recipe(
                request.html,
                url="",
                fetcher=SafeFetcher(),
                download_images=False,
                unit_system=request.unit_system,
            )
        except Exception as e:
            logger.warning("Recipe extraction failed for pasted HTML: %s", e)
            raise HTTPException(
                status_code=422,
                detail=EXTRACT_FAILED,
            ) from e
        return ExtractResponse(recipe=recipe, warnings=warnings)

    if library is not None:
        known = library.get_by_url(request.url.strip())
        if known is not None:
            return _from_library(known)

    recipe, warnings, final_url = _fetch_and_extract(request.url, request.unit_system)

    if library is None:
        return ExtractResponse(recipe=recipe, warnings=warnings)

    known = library.get_by_url(final_url)
    if known is not None:
        return _from_library(known)

    try:
        record = library.create(final_url, recipe)
    except sqlite3.Error as e:
        # Never lose a good extraction because the library could not be written.
        logger.error("Auto-save failed: %s", e)
        warnings.append("The recipe could not be saved to the library.")
        return ExtractResponse(recipe=recipe, warnings=warnings)
    return ExtractResponse(
        recipe=recipe, warnings=warnings, library_id=record.id, state=record.state
    )


def _from_library(record: LibraryRecord) -> ExtractResponse:
    logger.info("extract served from library id=%d", record.id)
    return ExtractResponse(
        recipe=record.recipe,
        warnings=["Loaded your saved copy. Use Re-extract to fetch it again."],
        library_id=record.id,
        from_library=True,
        state=record.state,
        edited_at=record.edited_at,
        has_previous=record.has_previous,
    )


@router.post("/convert", response_model=ConvertResponse)
def convert(request: ConvertRequest) -> ConvertResponse:
    """Convert recipe units (weights, volumes, temperatures, dimensions, vocabulary)."""
    try:
        converted_recipe = convert_recipe(request.recipe, request.unit_system)
        return ConvertResponse(recipe=converted_recipe)
    except Exception as e:
        logger.warning("Unit conversion failed: %s", e)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to convert recipe units: {e}",
        ) from e


# ---------------------------------------------------------------- library


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Recipe not found in the library.")


@router.get("/library")
def library_list(request: Request) -> list[LibraryEntry]:
    """List saved recipes, most recently touched first (no recipe bodies)."""
    return require_library(request).list_entries()


@router.get("/library/{record_id}")
def library_get(record_id: int, request: Request) -> LibraryRecord:
    record = require_library(request).get(record_id)
    if record is None:
        raise _not_found()
    return record


@router.put("/library/{record_id}")
def library_save(
    record_id: int, body: LibrarySaveRequest, request: Request
) -> LibraryRecord:
    """Auto-save an edit."""
    record = require_library(request).save(
        record_id, body.recipe, body.state, keep_previous=body.keep_previous
    )
    if record is None:
        raise _not_found()
    return record


@router.delete("/library/{record_id}", status_code=204)
def library_delete(record_id: int, request: Request) -> None:
    if not require_library(request).delete(record_id):
        raise _not_found()


@router.post("/library/{record_id}/restore")
def library_restore(record_id: int, request: Request) -> LibraryRecord:
    """Swap the recipe with its previous version."""
    library = require_library(request)
    if library.get(record_id) is None:
        raise _not_found()
    record = library.restore(record_id)
    if record is None:
        raise HTTPException(status_code=409, detail="There is no previous version.")
    return record


def describe_changes(old: Recipe, new: Recipe) -> list[str]:
    """Short, human-readable differences between a saved and a fresh recipe."""
    changes: list[str] = []
    if old.title != new.title:
        changes.append(f"Title: '{old.title}' -> '{new.title}'")
    if old.servings != new.servings:
        changes.append(
            f"Servings: {old.servings or 'none'} -> {new.servings or 'none'}"
        )
    for label, before, after in (
        ("Prep time", old.prep_time_minutes, new.prep_time_minutes),
        ("Cook time", old.cook_time_minutes, new.cook_time_minutes),
        ("Total time", old.total_time_minutes, new.total_time_minutes),
    ):
        if before != after:
            changes.append(f"{label}: {before} -> {after} minutes")

    old_lines = {i.original_raw or i.raw for i in old.ingredients}
    new_lines = {i.original_raw or i.raw for i in new.ingredients}
    if old_lines != new_lines:
        changes.append(
            f"Ingredients: {len(new_lines - old_lines)} new, "
            f"{len(old_lines - new_lines)} no longer present"
        )
    if [s.text for s in old.steps] != [s.text for s in new.steps]:
        changes.append(f"Method: {len(old.steps)} -> {len(new.steps)} steps")
    if old.notes != new.notes:
        changes.append("Notes differ")
    if len(old.images) != len(new.images):
        changes.append(f"Images: {len(old.images)} -> {len(new.images)}")
    return changes


@router.post("/library/{record_id}/re-extract", response_model=ReExtractResponse)
def library_re_extract(
    record_id: int, request: Request, confirm: bool = False
) -> ReExtractResponse:
    """Fetch the source again. Nothing is overwritten unless ``confirm=true``."""
    library = require_library(request)
    record = library.get(record_id)
    if record is None:
        raise _not_found()

    fresh, warnings, _ = _fetch_and_extract(record.url, "original")
    changes = describe_changes(record.recipe, fresh)
    if not confirm:
        return ReExtractResponse(applied=False, changes=changes, warnings=warnings)

    updated = library.replace_with_extraction(record_id, fresh)
    if updated is None:
        raise _not_found()
    return ReExtractResponse(
        applied=True, changes=changes, warnings=warnings, record=updated
    )
