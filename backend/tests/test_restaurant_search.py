"""Provider normalization, matching, and ranking. No database, no HTTP."""

import pytest

from app.providers.mock_restaurants import (
    MockRestaurantProvider,
    load_mock_restaurants,
    normalize,
)
from app.schemas.restaurant import Location, MenuItem, Restaurant, RestaurantSearchQuery
from app.services.restaurant_search import bayesian_rating, score_restaurant, search_restaurants

T_NAGAR = {"lat": 13.0418, "lng": 80.2341}


def query(text: str, **overrides) -> RestaurantSearchQuery:
    return RestaurantSearchQuery(query=text, **{**T_NAGAR, **overrides})


def make_restaurant(**overrides) -> Restaurant:
    data = {
        "id": "test:r",
        "provider": "test",
        "name": "Test Restaurant",
        "cuisines": ["biryani"],
        "rating": 4.0,
        "review_count": 100,
        "price_level": 2,
        "location": Location(**T_NAGAR),
        "address": "Somewhere",
        "is_open": True,
        "menu": [MenuItem(name="Chicken Biryani", price_minor=25000, currency="INR")],
    }
    return Restaurant(**{**data, **overrides})


# --- Normalization (raw provider format -> our Restaurant) ----------------------


def test_mock_data_loads_and_validates() -> None:
    restaurants = load_mock_restaurants()

    assert len(restaurants) == 12
    assert all(r.id.startswith("mock:") for r in restaurants)


def test_normalize_translates_provider_format() -> None:
    raw = {
        "slug": "x", "title": "X Biryani", "tags": ["Biryani"], "stars": 4.2, "reviews": 10,
        "cost_for_two": 1000, "coords": {"latitude": 13.0, "longitude": 80.0},
        "address": "A", "open_now": True, "dishes": [{"dish": "Biryani", "price": "349.90"}],
    }

    restaurant = normalize(raw)

    assert restaurant.id == "mock:x"
    assert restaurant.name == "X Biryani"
    assert restaurant.cuisines == ["biryani"]  # lowercased
    assert restaurant.price_level == 3  # cost_for_two 1000 -> ₹₹₹
    assert restaurant.menu[0].price_minor == 34990  # "349.90" -> integer paise, no float error


def test_normalize_rejects_invalid_provider_data() -> None:
    raw = {
        "slug": "x", "title": "X", "tags": [], "stars": 9.0, "reviews": 10,  # 9.0 is not on a 0-5 scale
        "cost_for_two": 100, "coords": {"latitude": 13.0, "longitude": 80.0},
        "address": "A", "open_now": True, "dishes": [],
    }

    with pytest.raises(ValueError):
        normalize(raw)


# --- Matching ------------------------------------------------------------------


def test_matching_is_case_insensitive_and_reports_dishes() -> None:
    restaurant = make_restaurant()

    assert restaurant.matches("BIRYANI")
    assert restaurant.dishes_matching("biryani") == ["Chicken Biryani"]


def test_multi_word_query_must_match_within_one_dish() -> None:
    restaurant = make_restaurant(
        name="Plain Name",
        cuisines=["indian"],
        menu=[
            MenuItem(name="Chicken Dum Biryani", price_minor=1, currency="INR"),
            MenuItem(name="Chicken Curry", price_minor=1, currency="INR"),
        ],
    )

    assert restaurant.dishes_matching("chicken biryani") == ["Chicken Dum Biryani"]
    assert not restaurant.matches("mutton biryani")


def test_mock_search_filters_by_text_and_radius() -> None:
    names = {r.name for r in MockRestaurantProvider().search(query("biryani", radius_km=5))}

    assert "Saffron Dum House" in names
    assert "Tambaram Biryani Junction" not in names  # ~16 km away
    assert "Annapoorna Tiffin Centre" not in names  # no biryani


def test_search_with_no_matches_returns_empty_list() -> None:
    assert MockRestaurantProvider().search(query("sushi")) == []


# --- Ranking ------------------------------------------------------------------


def test_bayesian_rating_distrusts_few_reviews() -> None:
    few_reviews = bayesian_rating(5.0, 2)
    many_reviews = bayesian_rating(4.6, 3400)

    assert few_reviews == pytest.approx(3.56, abs=0.01)
    assert many_reviews > few_reviews


def test_score_prefers_closer_restaurant_when_ratings_equal() -> None:
    restaurant = make_restaurant()

    assert score_restaurant(restaurant, 0.5, 5) > score_restaurant(restaurant, 4.5, 5)


def test_score_is_between_zero_and_one() -> None:
    best = make_restaurant(rating=5.0, review_count=1_000_000)

    assert 0 <= score_restaurant(best, 0, 5) <= 1
    assert 0 <= score_restaurant(make_restaurant(rating=0, review_count=0), 5, 5) <= 1


def test_search_results_are_ranked_open_first_then_by_score() -> None:
    results = search_restaurants(MockRestaurantProvider(), query("biryani"))

    open_scores = [r.score for r in results if r.is_open]
    assert open_scores == sorted(open_scores, reverse=True)
    assert results[-1].name == "Thalassery Spice"  # closed -> last
    names = [r.name for r in results]
    # 5.0 stars from 3 reviews ranks below 4.6 stars from 3400 reviews.
    assert names.index("Nawab's Kitchen") < names.index("Biryani Point Express")


def test_search_respects_limit() -> None:
    assert len(search_restaurants(MockRestaurantProvider(), query("biryani", limit=2))) == 2


class _SloppyProvider:
    """A provider that ignores the radius. Proves the service enforces it anyway."""

    def search(self, query: RestaurantSearchQuery) -> list[Restaurant]:
        return [make_restaurant(id="test:far", location=Location(lat=12.9249, lng=80.1000))]

    def get_restaurant(self, restaurant_id: str) -> Restaurant | None:
        return None


def test_service_enforces_radius_even_if_provider_does_not() -> None:
    assert search_restaurants(_SloppyProvider(), query("biryani", radius_km=5)) == []
