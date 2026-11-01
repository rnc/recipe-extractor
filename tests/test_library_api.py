# SPDX-License-Identifier: Apache-2.0
"""Tests for the library API routes and auto-save on extract."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from recipe_extractor import api
from recipe_extractor.main import app, create_app
from recipe_extractor.models import Ingredient, Recipe, Step

URL = "https://example.com/cake"


def make_recipe(title: str = "Cake") -> Recipe:
    return Recipe(
        title=title,
        source_url=URL,
        servings="8",
        ingredients=[Ingredient(raw="200g flour", original_raw="200g flour")],
        steps=[Step(text="Mix.")],
    )


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "recipes.db"))


@pytest.fixture
def fake_fetch(monkeypatch: pytest.MonkeyPatch) -> Callable[[Recipe], list[str]]:
    """Replace the network fetch; returns the list of URLs that were fetched."""
    fetched: list[str] = []

    def install(recipe: Recipe) -> list[str]:
        def fake(url: str, unit_system: str) -> tuple[Recipe, list[str], str]:
            fetched.append(url)
            return recipe.model_copy(deep=True), [], url

        monkeypatch.setattr(api, "_fetch_and_extract", fake)
        return fetched

    return install


def extract(client: TestClient, url: str = URL) -> dict[str, Any]:
    response = client.post("/api/extract", json={"url": url})
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


def test_module_level_app_has_no_library() -> None:
    """Importing the app (as tests do) must never touch a real library."""
    assert app.state.library is None
    assert TestClient(app).get("/api/health").json()["library"] is False


def test_health_reports_library(client: TestClient) -> None:
    assert client.get("/api/health").json()["library"] is True


def test_library_routes_404_when_disabled() -> None:
    plain = TestClient(create_app())
    assert plain.get("/api/library").status_code == 404
    assert plain.get("/api/library/1").status_code == 404
    assert plain.delete("/api/library/1").status_code == 404
    assert plain.post("/api/library/1/restore").status_code == 404
    assert plain.post("/api/library/1/re-extract").status_code == 404


def test_extract_without_library_has_no_id(
    fake_fetch: Callable[[Recipe], list[str]],
) -> None:
    fake_fetch(make_recipe())
    response = TestClient(create_app()).post("/api/extract", json={"url": URL})
    assert response.status_code == 200
    assert response.json()["library_id"] is None
    assert response.json()["from_library"] is False


def test_new_extract_is_auto_saved(
    client: TestClient, fake_fetch: Callable[[Recipe], list[str]]
) -> None:
    fake_fetch(make_recipe())
    data = extract(client)
    assert data["from_library"] is False
    assert isinstance(data["library_id"], int)
    assert data["state"] == "extracted"
    assert data["has_previous"] is False

    listing = client.get("/api/library").json()
    assert len(listing) == 1
    assert listing[0]["title"] == "Cake"
    assert listing[0]["state"] == "extracted"
    assert "recipe" not in listing[0]


def test_known_url_loads_saved_copy_and_never_overwrites(
    client: TestClient, fake_fetch: Callable[[Recipe], list[str]]
) -> None:
    fetched = fake_fetch(make_recipe())
    record_id = extract(client)["library_id"]

    edited = make_recipe("My edited cake")
    assert (
        client.put(
            f"/api/library/{record_id}",
            json={"recipe": edited.model_dump(), "state": "editing"},
        ).status_code
        == 200
    )

    again = extract(client)
    assert again["from_library"] is True
    assert again["library_id"] == record_id
    assert again["recipe"]["title"] == "My edited cake"
    assert again["state"] == "editing"
    assert again["edited_at"] is not None
    assert "saved copy" in again["warnings"][0]
    assert fetched == [URL], "a known URL must not be fetched again"


def test_get_save_and_delete(
    client: TestClient, fake_fetch: Callable[[Recipe], list[str]]
) -> None:
    fake_fetch(make_recipe())
    record_id = extract(client)["library_id"]

    got = client.get(f"/api/library/{record_id}").json()
    assert got["recipe"]["title"] == "Cake"
    assert got["has_previous"] is False

    saved = client.put(
        f"/api/library/{record_id}",
        json={"recipe": make_recipe("Final").model_dump(), "state": "final"},
    )
    assert saved.status_code == 200
    assert saved.json()["state"] == "final"
    assert saved.json()["edited_at"] is not None

    assert client.delete(f"/api/library/{record_id}").status_code == 204
    assert client.get(f"/api/library/{record_id}").status_code == 404
    assert client.delete(f"/api/library/{record_id}").status_code == 404


def test_save_validates_input(client: TestClient) -> None:
    assert client.put("/api/library/1", json={}).status_code == 422
    bad_state = {"recipe": make_recipe().model_dump(), "state": "extracted"}
    assert client.put("/api/library/1", json=bad_state).status_code == 422
    unknown = {"recipe": make_recipe().model_dump(), "state": "editing"}
    assert client.put("/api/library/999", json=unknown).status_code == 404


def test_re_extract_previews_then_applies_with_restore(
    client: TestClient, fake_fetch: Callable[[Recipe], list[str]]
) -> None:
    fake_fetch(make_recipe("Old title"))
    record_id = extract(client)["library_id"]
    client.put(
        f"/api/library/{record_id}",
        json={"recipe": make_recipe("My edits").model_dump(), "state": "editing"},
    )

    fake_fetch(make_recipe("New title"))
    preview = client.post(f"/api/library/{record_id}/re-extract")
    assert preview.status_code == 200
    body = preview.json()
    assert body["applied"] is False
    assert body["record"] is None
    assert any("My edits" in c and "New title" in c for c in body["changes"])
    # The preview must not have changed anything.
    assert client.get(f"/api/library/{record_id}").json()["recipe"]["title"] == (
        "My edits"
    )

    applied = client.post(f"/api/library/{record_id}/re-extract?confirm=true")
    assert applied.json()["applied"] is True
    assert applied.json()["record"]["recipe"]["title"] == "New title"
    assert applied.json()["record"]["has_previous"] is True

    restored = client.post(f"/api/library/{record_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["recipe"]["title"] == "My edits"


def test_restore_errors(
    client: TestClient, fake_fetch: Callable[[Recipe], list[str]]
) -> None:
    fake_fetch(make_recipe())
    record_id = extract(client)["library_id"]
    assert client.post(f"/api/library/{record_id}/restore").status_code == 409
    assert client.post("/api/library/999/restore").status_code == 404
    assert client.post("/api/library/999/re-extract").status_code == 404


def test_pasted_html_is_not_saved(client: TestClient) -> None:
    html = (Path(__file__).parent / "fixtures" / "simple_recipe.html").read_text()
    response = client.post("/api/extract", json={"html": html})
    assert response.status_code == 200
    assert response.json()["library_id"] is None
    assert client.get("/api/library").json() == []


def test_failed_save_does_not_lose_the_extraction(
    client: TestClient,
    fake_fetch: Callable[[Recipe], list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sqlite3

    fake_fetch(make_recipe())

    def boom(*args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(client.app.state.library, "create", boom)  # type: ignore[attr-defined]
    response = client.post("/api/extract", json={"url": URL})
    assert response.status_code == 200
    assert response.json()["library_id"] is None
    assert "could not be saved" in response.json()["warnings"][0]
    assert response.json()["recipe"]["title"] == "Cake"


def test_describe_changes() -> None:
    old = make_recipe("A")
    assert api.describe_changes(old, old.model_copy(deep=True)) == []

    new = make_recipe("B")
    new.servings = "4"
    new.prep_time_minutes = 10
    new.ingredients = [Ingredient(raw="1 egg")]
    new.steps = [Step(text="Mix."), Step(text="Bake.")]
    new.notes = ["x"]
    changes = api.describe_changes(old, new)
    assert "Title: 'A' -> 'B'" in changes
    assert "Servings: 8 -> 4" in changes
    assert "Prep time: None -> 10 minutes" in changes
    assert "Ingredients: 1 new, 1 no longer present" in changes
    assert "Method: 1 -> 2 steps" in changes
    assert "Notes differ" in changes


def test_logs_never_contain_recipe_content(
    client: TestClient,
    fake_fetch: Callable[[Recipe], list[str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """PLAN.md 10.3: no ingredient text, step text or data: URIs in the logs."""
    from recipe_extractor.models import RecipeImage

    recipe = make_recipe("Secret cake")
    recipe.ingredients = [Ingredient(raw="999g unobtainium")]
    recipe.steps = [Step(text="Whisk the moonbeams.")]
    recipe.images = [RecipeImage(src="data:image/png;base64,QUJDREVGRw==")]
    fake_fetch(recipe)

    with caplog.at_level(logging.DEBUG):
        record_id = extract(client)["library_id"]
        client.put(
            f"/api/library/{record_id}",
            json={"recipe": recipe.model_dump(), "state": "final"},
        )
        client.post(f"/api/library/{record_id}/restore")
        client.delete(f"/api/library/{record_id}")

    assert "library created" in caplog.text
    for secret in ("unobtainium", "moonbeams", "data:image", "QUJDREVGRw"):
        assert secret not in caplog.text
