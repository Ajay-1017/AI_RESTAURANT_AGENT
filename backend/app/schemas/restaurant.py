"""Normalized restaurant data: OUR shape, whatever provider the data came from.

These are Pydantic models (data passing through the system), not SQLAlchemy
models (rows in our database). Restaurant data belongs to the provider.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class MenuItem(BaseModel):
    name: str
    # Money in integer minor units (paise): 34900 = ₹349.00. Never floats.
    price_minor: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)  # ISO 4217, e.g. "INR"


class Restaurant(BaseModel):
    id: str  # provider-prefixed, e.g. "mock:saffron-dum-house"
    provider: str
    name: str
    cuisines: list[str]
    rating: float = Field(ge=0, le=5)  # always 0-5, whatever the provider's scale
    review_count: int = Field(ge=0)
    price_level: int = Field(ge=1, le=4)  # 1 = ₹ ... 4 = ₹₹₹₹
    location: Location
    address: str
    is_open: bool
    menu: list[MenuItem]

    def matches(self, text: str) -> bool:
        """True if the name, the cuisines, or any single dish contains every query word."""
        fields = [self.name, " ".join(self.cuisines), *(item.name for item in self.menu)]
        return any(_contains_all_words(field, text) for field in fields)

    def dishes_matching(self, text: str) -> list[str]:
        return [item.name for item in self.menu if _contains_all_words(item.name, text)]


def _contains_all_words(field: str, text: str) -> bool:
    field_lower = field.lower()
    return all(word in field_lower for word in text.lower().split())


class RestaurantSearchQuery(BaseModel):
    """Search input. Used as the API's query parameters, by the service and providers,
    and later as the schema of the agent's search tool."""

    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    # Upper bounds protect us from very expensive calls to paid provider APIs.
    radius_km: float = Field(default=5.0, ge=0.5, le=25)
    limit: int = Field(default=10, ge=1, le=50)

    @property
    def location(self) -> Location:
        return Location(lat=self.lat, lng=self.lng)


class RankedRestaurant(BaseModel):
    """One search result: a restaurant summary plus why/how well it matched."""

    id: str
    name: str
    cuisines: list[str]
    rating: float
    review_count: int
    price_level: int
    address: str
    is_open: bool
    distance_km: float
    matched_dishes: list[str]
    score: float  # 0-1, higher is better
