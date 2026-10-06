"""The restaurant provider interface and how the app picks one."""

from typing import Protocol

from app.config import settings
from app.providers.mock_restaurants import MockRestaurantProvider
from app.schemas.restaurant import Restaurant, RestaurantSearchQuery


class RestaurantProvider(Protocol):
    """Anything with these two methods is a restaurant provider (structural typing).

    Implementations must return normalized Restaurant objects, never raw API data.
    """

    def search(self, query: RestaurantSearchQuery) -> list[Restaurant]: ...

    def get_restaurant(self, restaurant_id: str) -> Restaurant | None: ...


def get_restaurant_provider() -> RestaurantProvider:
    """FastAPI dependency. Switching providers is a config change, not a code change."""
    if settings.restaurant_provider == "mock":
        return MockRestaurantProvider()
    raise RuntimeError(f"Unknown restaurant provider: {settings.restaurant_provider}")
