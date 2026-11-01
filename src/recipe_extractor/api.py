# SPDX-License-Identifier: Apache-2.0
"""JSON API routes."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from recipe_extractor import __version__
from recipe_extractor.extract import extract_recipe
from recipe_extractor.fetch import FetchError, SafeFetcher
from recipe_extractor.models import (
    ConvertRequest,
    ConvertResponse,
    ExtractRequest,
    ExtractResponse,
)
from recipe_extractor.units import convert_recipe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class Health(BaseModel):
    status: str
    version: str


@router.get("/health")
def health() -> Health:
    """Liveness check; also confirms which version is running."""
    return Health(status="ok", version=__version__)


@router.post("/extract", response_model=ExtractResponse)
def extract(request: ExtractRequest) -> ExtractResponse:
    """Extract structured recipe data from a URL or raw HTML."""
    if not request.url and not request.html:
        raise HTTPException(
            status_code=400,
            detail="Either 'url' or 'html' must be provided in the request.",
        )

    fetcher = SafeFetcher()
    html_content = ""
    target_url = ""

    if request.url:
        target_url = request.url.strip()
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
    elif request.html:
        html_content = request.html

    try:
        recipe, warnings = extract_recipe(
            html_content,
            url=target_url,
            fetcher=fetcher,
            download_images=bool(target_url),
            unit_system=request.unit_system,
        )
    except Exception as e:
        logger.warning("Recipe extraction failed for '%s': %s", target_url, e)
        raise HTTPException(
            status_code=422,
            detail="Could not extract recipe structured data from the provided page.",
        ) from e

    return ExtractResponse(recipe=recipe, warnings=warnings)


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
