from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.providers.restaurants import RestaurantProvider, get_restaurant_provider
from app.schemas.restaurant import RankedRestaurant, Restaurant, RestaurantSearchQuery
from app.services.restaurant_search import search_restaurants

# Router-level dependency: every endpoint below requires a logged-in user.
router = APIRouter(
    prefix="/restaurants",
    tags=["restaurants"],
    dependencies=[Depends(get_current_user)],
)

Provider = Annotated[RestaurantProvider, Depends(get_restaurant_provider)]


# Declared BEFORE /{restaurant_id}: routes match in order, otherwise
# "/restaurants/search" would be treated as a restaurant with id "search".
@router.get("/search", response_model=list[RankedRestaurant])
def search(
    params: Annotated[RestaurantSearchQuery, Query()],
    provider: Provider,
) -> list[RankedRestaurant]:
    return search_restaurants(provider, params)


@router.get("/{restaurant_id}", response_model=Restaurant)
def get_restaurant(restaurant_id: str, provider: Provider) -> Restaurant:
    restaurant = provider.get_restaurant(restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    return restaurant
