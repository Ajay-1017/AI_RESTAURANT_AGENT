import pytest

from app.core.geo import haversine_km
from app.schemas.restaurant import Location

CHENNAI = Location(lat=13.0827, lng=80.2707)
BENGALURU = Location(lat=12.9716, lng=77.5946)


def test_distance_to_same_point_is_zero() -> None:
    assert haversine_km(CHENNAI, CHENNAI) == 0


def test_chennai_to_bengaluru_is_about_290_km() -> None:
    # Known straight-line distance is roughly 290 km.
    assert haversine_km(CHENNAI, BENGALURU) == pytest.approx(290, abs=5)


def test_distance_is_symmetric() -> None:
    assert haversine_km(CHENNAI, BENGALURU) == pytest.approx(haversine_km(BENGALURU, CHENNAI))
