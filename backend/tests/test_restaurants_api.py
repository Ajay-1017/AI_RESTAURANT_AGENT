"""HTTP tests for /restaurants. Authentication is overridden, so no database is needed."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main import app
from app.models import User

T_NAGAR = {"lat": 13.0418, "lng": 80.2341}


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A client whose requests count as coming from a logged-in user."""
    app.dependency_overrides[get_current_user] = lambda: User(email="test@example.com")
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_search_requires_login() -> None:
    response = TestClient(app).get("/restaurants/search", params={"query": "biryani", **T_NAGAR})

    assert response.status_code == 401


def test_detail_requires_login() -> None:
    assert TestClient(app).get("/restaurants/mock:saffron-dum-house").status_code == 401


def test_search_returns_ranked_results(client: TestClient) -> None:
    response = client.get("/restaurants/search", params={"query": "biryani", **T_NAGAR})

    assert response.status_code == 200
    results = response.json()
    assert results[0]["name"] == "Saffron Dum House"
    assert results[0]["matched_dishes"]
    assert {"distance_km", "score", "is_open"} <= results[0].keys()
    assert "menu" not in results[0]  # summaries only; menu is in the detail endpoint


@pytest.mark.parametrize(
    "bad_params",
    [
        {"query": "b", **T_NAGAR},  # query too short
        {"query": "biryani", "lat": 200, "lng": 80.2},  # impossible latitude
        {"query": "biryani", **T_NAGAR, "radius_km": 100},  # radius too large
        {"query": "biryani", **T_NAGAR, "limit": 0},
        {"query": "biryani"},  # location missing
        {"query": "biryani", **T_NAGAR, "unexpected": "x"},  # unknown parameter
    ],
)
def test_search_rejects_invalid_input(client: TestClient, bad_params: dict) -> None:
    assert client.get("/restaurants/search", params=bad_params).status_code == 422


def test_restaurant_detail_includes_menu_in_minor_units(client: TestClient) -> None:
    response = client.get("/restaurants/mock:saffron-dum-house")

    assert response.status_code == 200
    menu = response.json()["menu"]
    assert {"name": "Chicken Dum Biryani", "price_minor": 34900, "currency": "INR"} in menu


def test_unknown_restaurant_returns_404(client: TestClient) -> None:
    assert client.get("/restaurants/mock:does-not-exist").status_code == 404
