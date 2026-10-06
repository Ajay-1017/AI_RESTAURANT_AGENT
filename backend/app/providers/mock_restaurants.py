"""A fake restaurant provider backed by a JSON file.

It behaves like an external API: the raw data has its own format, and this
module's job is to translate it into our normalized Restaurant model.
A real provider (e.g. Google Places) would do the same, with HTTP instead of a file.
"""

import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.geo import haversine_km
from app.schemas.restaurant import Location, MenuItem, Restaurant, RestaurantSearchQuery

PROVIDER_NAME = "mock"
DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "mock_restaurants.json"


def _price_level_from_cost_for_two(cost_for_two: int) -> int:
    if cost_for_two <= 400:
        return 1
    if cost_for_two <= 800:
        return 2
    if cost_for_two <= 1500:
        return 3
    return 4


def _to_minor_units(price: str) -> int:
    # Decimal, not float: float("0.1") + float("0.2") != 0.3
    return int(Decimal(price) * 100)


def normalize(raw: dict[str, Any]) -> Restaurant:
    """Translate one raw provider record into our Restaurant model.

    Pydantic validates the result, so malformed provider data fails loudly here
    instead of leaking into the rest of the app.
    """
    return Restaurant(
        id=f"{PROVIDER_NAME}:{raw['slug']}",
        provider=PROVIDER_NAME,
        name=raw["title"],
        cuisines=[tag.lower() for tag in raw["tags"]],
        rating=raw["stars"],
        review_count=raw["reviews"],
        price_level=_price_level_from_cost_for_two(raw["cost_for_two"]),
        location=Location(lat=raw["coords"]["latitude"], lng=raw["coords"]["longitude"]),
        address=raw["address"],
        is_open=raw["open_now"],
        menu=[
            MenuItem(name=d["dish"], price_minor=_to_minor_units(d["price"]), currency="INR")
            for d in raw["dishes"]
        ],
    )


@lru_cache
def load_mock_restaurants() -> tuple[Restaurant, ...]:
    """Read and normalize the JSON file once per process (tuple: immutable, safe to share)."""
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return tuple(normalize(item) for item in raw["results"])


class MockRestaurantProvider:
    """Satisfies the RestaurantProvider protocol without inheriting from it."""

    def __init__(self, restaurants: tuple[Restaurant, ...] | None = None) -> None:
        self._restaurants = restaurants if restaurants is not None else load_mock_restaurants()

    def search(self, query: RestaurantSearchQuery) -> list[Restaurant]:
        # Like a real API: filter by text + radius. Ranking is NOT the provider's job.
        return [
            r
            for r in self._restaurants
            if r.matches(query.query) and haversine_km(query.location, r.location) <= query.radius_km
        ]

    def get_restaurant(self, restaurant_id: str) -> Restaurant | None:
        return next((r for r in self._restaurants if r.id == restaurant_id), None)
