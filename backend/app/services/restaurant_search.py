"""Restaurant search + deterministic ranking.

Ranking is plain arithmetic on purpose: code calculates and decides,
the LLM (Phase 5+) only handles language.
"""

from app.core.geo import haversine_km
from app.providers.restaurants import RestaurantProvider
from app.schemas.restaurant import RankedRestaurant, Restaurant, RestaurantSearchQuery

# Bayesian average: a rating backed by few reviews is pulled toward PRIOR_RATING.
PRIOR_RATING = 3.5  # what we assume about an unknown restaurant
PRIOR_WEIGHT = 50  # roughly "how many reviews before we trust the rating"

RATING_WEIGHT = 0.75
DISTANCE_WEIGHT = 0.25


def bayesian_rating(rating: float, review_count: int) -> float:
    return (review_count * rating + PRIOR_WEIGHT * PRIOR_RATING) / (review_count + PRIOR_WEIGHT)


def score_restaurant(restaurant: Restaurant, distance_km: float, radius_km: float) -> float:
    rating_part = bayesian_rating(restaurant.rating, restaurant.review_count) / 5
    distance_part = max(0.0, 1 - distance_km / radius_km)
    return round(RATING_WEIGHT * rating_part + DISTANCE_WEIGHT * distance_part, 4)


def search_restaurants(
    provider: RestaurantProvider, query: RestaurantSearchQuery
) -> list[RankedRestaurant]:
    results: list[RankedRestaurant] = []

    for restaurant in provider.search(query):
        distance_km = haversine_km(query.location, restaurant.location)
        # Don't trust providers blindly: enforce the radius ourselves.
        if distance_km > query.radius_km:
            continue
        results.append(
            RankedRestaurant(
                id=restaurant.id,
                name=restaurant.name,
                cuisines=restaurant.cuisines,
                rating=restaurant.rating,
                review_count=restaurant.review_count,
                price_level=restaurant.price_level,
                address=restaurant.address,
                is_open=restaurant.is_open,
                distance_km=round(distance_km, 2),
                matched_dishes=restaurant.dishes_matching(query.query),
                score=score_restaurant(restaurant, distance_km, query.radius_km),
            )
        )

    # Open restaurants first, then best score. (False sorts before True.)
    results.sort(key=lambda r: (not r.is_open, -r.score))
    return results[: query.limit]
