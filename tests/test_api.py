# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from fastapi.testclient import TestClient

from recipe_extractor import __version__
from recipe_extractor.main import HOST, app

client = TestClient(app)
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_index_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Recipe Extractor" in response.text


def test_binds_to_loopback_only() -> None:
    assert HOST == "127.0.0.1"


def test_extract_with_html_payload() -> None:
    html = (FIXTURES_DIR / "simple_recipe.html").read_text()
    response = client.post("/api/extract", json={"html": html})
    assert response.status_code == 200
    data = response.json()
    assert "recipe" in data
    assert data["recipe"]["title"] == "Classic Lemon Drizzle Cake"
    assert len(data["recipe"]["ingredients"]) == 5


def test_extract_missing_payload() -> None:
    response = client.post("/api/extract", json={})
    assert response.status_code == 400


def test_extract_blocks_private_ssrf_url() -> None:
    response = client.post(
        "/api/extract", json={"url": "http://127.0.0.1:8000/api/health"}
    )
    assert response.status_code == 400
    assert "Unable to safely fetch" in response.json()["detail"]


def test_extract_invalid_html_content() -> None:
    response = client.post(
        "/api/extract", json={"html": "<html><body>No recipe here</body></html>"}
    )
    assert response.status_code == 422
    assert "Could not extract" in response.json()["detail"]
