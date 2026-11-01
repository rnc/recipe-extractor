# SPDX-License-Identifier: Apache-2.0
"""Canonical data models for Recipe Extractor."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LibraryState = Literal["extracted", "editing", "final"]


class RecipeImage(BaseModel):
    """An extracted or user-supplied recipe image."""

    model_config = ConfigDict(extra="forbid")

    src: str = Field(description="Image data: URI or remote URL")
    alt: str = Field(default="", description="Alt text or image caption")
    selected: bool = Field(
        default=False, description="Whether this image is selected for printing"
    )
    original_url: str | None = Field(
        default=None, description="Original source URL if known"
    )


class Ingredient(BaseModel):
    """A single ingredient line, optionally structured."""

    model_config = ConfigDict(extra="forbid")

    raw: str = Field(description="Full raw text of the ingredient line")
    quantity: float | str | None = Field(
        default=None, description="Numeric or string quantity"
    )
    unit: str | None = Field(default=None, description="Unit of measurement")
    name: str | None = Field(
        default=None, description="Ingredient name without quantity/unit"
    )
    note: str | None = Field(
        default=None, description="Preparation note (e.g. diced, beaten)"
    )
    group: str | None = Field(
        default=None,
        description="Ingredient group heading (e.g. 'For the sauce')",
    )
    converted: str | None = Field(
        default=None, description="Converted text for the current unit system"
    )
    original_raw: str | None = Field(
        default=None, description="Original un-converted text of the ingredient line"
    )
    unit_override: Literal["original", "metric", "uk"] | None = Field(
        default=None, description="Per-line unit override"
    )


class Step(BaseModel):
    """A method step."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="Instruction text")


class Recipe(BaseModel):
    """Canonical Recipe model."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", description="Recipe title")
    source_url: str | None = Field(default=None, description="Original recipe URL")
    servings: str | None = Field(default=None, description="Yield or servings string")
    prep_time_minutes: int | None = Field(
        default=None, description="Prep time in minutes"
    )
    cook_time_minutes: int | None = Field(
        default=None, description="Cook time in minutes"
    )
    total_time_minutes: int | None = Field(
        default=None, description="Total time in minutes"
    )
    images: list[RecipeImage] = Field(
        default_factory=list, description="Extracted recipe images"
    )
    ingredients: list[Ingredient] = Field(
        default_factory=list, description="List of ingredients"
    )
    steps: list[Step] = Field(default_factory=list, description="Ordered method steps")
    notes: list[str] = Field(
        default_factory=list, description="Extra notes or instructions"
    )
    unit_system: Literal["original", "metric", "uk"] = Field(
        default="original", description="Current unit system of the recipe"
    )


class ExtractRequest(BaseModel):
    """Request payload for /api/extract."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, description="URL of the recipe to extract")
    html: str | None = Field(
        default=None, description="Raw HTML string if provided directly"
    )
    unit_system: Literal["original", "metric", "uk"] = Field(
        default="original",
        description="Optional unit system to convert to (defaults to original)",
    )


class ExtractResponse(BaseModel):
    """Response payload for /api/extract."""

    model_config = ConfigDict(extra="forbid")

    recipe: Recipe
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal warnings during extraction"
    )
    library_id: int | None = Field(
        default=None,
        description="Library record id; null when persistence is disabled",
    )
    from_library: bool = Field(
        default=False,
        description="True when the saved library copy was returned, not a new fetch",
    )
    state: LibraryState | None = Field(
        default=None, description="Saved state; null when not in the library"
    )
    edited_at: str | None = Field(default=None, description="Last saved edit time")
    has_previous: bool = Field(
        default=False, description="True when a previous version can be restored"
    )


class ConvertRequest(BaseModel):
    """Request payload for /api/convert."""

    model_config = ConfigDict(extra="forbid")

    recipe: Recipe
    unit_system: Literal["original", "metric", "uk"] = Field(
        default="metric", description="Target unit system"
    )


class ConvertResponse(BaseModel):
    """Response payload for /api/convert."""

    model_config = ConfigDict(extra="forbid")

    recipe: Recipe


class LibraryEntry(BaseModel):
    """Summary of a saved recipe (no recipe body), for the library list."""

    model_config = ConfigDict(extra="forbid")

    id: int
    url: str
    title: str
    state: LibraryState
    extracted_at: str = Field(description="ISO-8601 UTC timestamp")
    edited_at: str | None = Field(
        default=None, description="ISO-8601 UTC timestamp of the last saved edit"
    )


class LibraryRecord(LibraryEntry):
    """A saved recipe with its full body."""

    recipe: Recipe
    has_previous: bool = Field(
        default=False, description="True when a previous version can be restored"
    )


class LibrarySaveRequest(BaseModel):
    """Request payload for PUT /api/library/{id} (auto-save)."""

    model_config = ConfigDict(extra="forbid")

    recipe: Recipe
    state: Literal["editing", "final"] = "editing"
    keep_previous: bool = Field(
        default=False,
        description="Copy the stored recipe to the restore slot before replacing it",
    )


class ReExtractResponse(BaseModel):
    """Response payload for POST /api/library/{id}/re-extract."""

    model_config = ConfigDict(extra="forbid")

    applied: bool = Field(description="False for the preview, true once committed")
    changes: list[str] = Field(
        default_factory=list, description="Human-readable summary of differences"
    )
    warnings: list[str] = Field(default_factory=list)
    record: LibraryRecord | None = Field(
        default=None, description="The updated record, present only when applied"
    )
