# Phase 4 — Restaurant Search Foundation

## 1. Goal

A restaurant search the API uses now and the AI agent will use from Phase 5:

```
GET /restaurants/search?query=biryani&lat=13.0418&lng=80.2341&radius_km=5&limit=10
GET /restaurants/{restaurant_id}
```

Built from:
1. **Normalized models** (`Restaurant`, `MenuItem`, `Location`): one data shape, whatever the source.
2. **A provider interface** (`RestaurantProvider` Protocol) with `search()` and `get_restaurant()`.
3. **A mock provider** that reads fictional Chennai restaurants from JSON *in a foreign format* and translates them.
4. **Deterministic ranking**: Bayesian-averaged rating + distance; open restaurants first.
5. **Auth-protected endpoints** with strict input validation.

## 2. Why do we need this?

- **Swappable data sources.** Real restaurant data comes from external APIs (Google Places, Foursquare, partners), each with its own JSON. Translating once, at the edge, means the API, the LangGraph agent and the MCP tools only ever see *our* format.
- **Testability now.** The mock gives deterministic data: no API keys, network, cost or flaky tests.
- **The agent needs a tool.** In Phase 5 the LLM will *call* `search_restaurants`. It must already exist, be validated, and give reliable results.
- **Code calculates, the LLM talks.** Ranking is arithmetic, and arithmetic must be consistent, cheap and testable. This rule also underpins payment safety later.

## 3. Concepts

### 3.1 Normalization (the "anti-corruption layer")
Every provider has its own vocabulary:

| Our field | Mock provider | (example) Google-style | (example) Foursquare-style |
|---|---|---|---|
| `name` | `title` | `displayName.text` | `name` |
| `rating` (0–5) | `stars` | `rating` | `rating` (0–10 → ÷2) |
| `price_level` (1–4) | `cost_for_two` (₹) | `priceLevel` enum | `price` 1–4 |
| `menu[].price_minor` | `"349.00"` (string ₹) | n/a | n/a |

The provider's `normalize()` is the **only** place that knows the foreign format. If that format changes, one function changes.

### 3.2 Pydantic model vs SQLAlchemy model

| | SQLAlchemy model (`User`) | Pydantic model (`Restaurant`) |
|---|---|---|
| Represents | a row in **our** database | a data shape at a boundary |
| Persisted by us | yes | no, it belongs to the provider |
| Validation | DB constraints | field constraints at creation |

We **don't** store restaurants. They're external, change often (ratings, hours, prices), and aren't ours to keep in sync. Phase 10 bookings will store a **snapshot**: the restaurant ID, name and item prices *as approved by the user*, so a later menu change can't alter an approved order.

### 3.3 Money in minor units
`price_minor=34900, currency="INR"` = ₹349.00.
```python
>>> 0.1 + 0.2
0.30000000000000004
```
- Floats can't represent most decimals exactly.
- Raw prices are converted with `Decimal`: `int(Decimal("349.90") * 100) == 34990`.
- Payment providers use integer minor units too.

### 3.4 `typing.Protocol` (structural typing)
```python
class RestaurantProvider(Protocol):
    def search(self, query: RestaurantSearchQuery) -> list[Restaurant]: ...
    def get_restaurant(self, restaurant_id: str) -> Restaurant | None: ...
```
`MockRestaurantProvider` doesn't inherit from it. It just has the right methods. Test fakes (like `_SloppyProvider` in the tests) work the same way.
- **ABC:** "you are a provider because you *declared* it".
- **Protocol:** "you are a provider because you *behave* like one", and it's still checked by type checkers.

### 3.5 Choosing the provider through dependency injection
```python
def get_restaurant_provider() -> RestaurantProvider:
    if settings.restaurant_provider == "mock":
        return MockRestaurantProvider()
```
- Routes receive it via `Depends(get_restaurant_provider)`.
- Switching provider = changing `RESTAURANT_PROVIDER` in config.
- Tests can override it, the same pattern as `get_db` and `get_current_user`.

### 3.6 Haversine distance
Latitude/longitude are angles on a sphere, so flat x/y distance is wrong:
```
h = sin²(Δlat/2) + cos(lat1)·cos(lat2)·sin²(Δlng/2)
d = 2 · 6371 km · asin(√h)
```
Tested against a known distance (Chennai → Bengaluru ≈ 290 km). For millions of rows you'd do this in the database (PostGIS) or let the provider do it; for a handful of results, Python is fine.

### 3.7 Ranking: Bayesian average + distance
Sorting by raw rating rewards a 5.0★ from 3 reviews. A Bayesian average pulls ratings with few reviews toward a prior:
```
adjusted = (reviews·rating + m·C) / (reviews + m)        C = 3.5, m = 50
score    = 0.75·(adjusted/5) + 0.25·(1 − distance/radius)
```
Real output for "biryani" near T. Nagar:

| Score | Distance | Rating / reviews | Restaurant |
|---|---|---|---|
| 0.921 | 0.00 km | 4.5 / 1820 | Saffron Dum House |
| 0.815 | 1.48 km | 4.3 / 960 | Ambur Star Biryani |
| 0.762 | 3.51 km | 4.6 / 3400 | Nawab's Kitchen |
| 0.692 | 1.91 km | **5.0 / 3** | Biryani Point Express ← correctly not first |
| 0.679 | 4.17 km | 4.3 / 700 (closed) | Thalassery Spice ← closed sorts last |

The weights are named constants. They're explainable and tunable, and the tests pin the behaviour.

### 3.8 Separation of responsibilities

| Component | Responsible for | Not responsible for |
|---|---|---|
| Provider | fetching, filtering by text + radius, **translating** | ranking |
| Service | distance, **re-checking the radius**, scoring, sorting, limit | where data comes from |
| API | HTTP, auth, validation, status codes | business rules |

The service re-checks the radius because **we don't trust external data blindly**. A buggy or differently-behaving provider can't leak a 16 km-away result into "near me".

The provider doesn't apply `limit`: if it cut to 10 *before* ranking, the best results could be thrown away.

### 3.9 Matching, and its honest limits
A restaurant matches if its name, its cuisines, or **any single dish** contains *every* query word (case-insensitive). So `"chicken biryani"` matches "Chicken **Dum** Biryani", but not a restaurant that has "Chicken Curry" and "Veg Biryani" as separate dishes.
- It doesn't understand "spicy rice dish from Hyderabad". That's intentional.
- In Phase 5 the **LLM** converts fuzzy language into structured `query="biryani"`, which is the right layer for language understanding.

### 3.10 Query parameter model
```python
def search(params: Annotated[RestaurantSearchQuery, Query()], ...)
```
FastAPI reads the query string into a Pydantic model. **One model** defines the constraints for the API, the service, the providers, and (Phase 5) the LLM tool's input schema. `extra="forbid"` rejects unknown parameters (`422`).

### 3.11 Router-level dependencies and route order
```python
router = APIRouter(prefix="/restaurants", dependencies=[Depends(get_current_user)])
```
- Every route in the router requires login, so nobody can forget it on a new endpoint.
- `/search` is declared **before** `/{restaurant_id}`. Routes match in order, otherwise `search` would be treated as an ID.

### 3.12 Validating our own fake data
`normalize()` builds Pydantic models, so a malformed record (for example `stars: 9.0`) **fails loudly** at the boundary. Treat the mock like a real external API: never trust input from outside.

## 4. Architecture

```
GET /restaurants/search?query=biryani&lat=..&lng=..
   │  router dependency: get_current_user  → 401 if not logged in
   │  Query() → RestaurantSearchQuery      → 422 if invalid
   ▼
app/api/restaurants.py ── Depends(get_restaurant_provider) ── config: RESTAURANT_PROVIDER=mock
   ▼
app/services/restaurant_search.py
   ├─ provider.search(query) ─────► MockRestaurantProvider
   │                                 load_mock_restaurants()  (JSON → normalize() → cached tuple)
   │                                 filter: text match + radius
   │                               ◄─ list[Restaurant]
   ├─ haversine_km()  (app/core/geo.py) + radius re-check
   ├─ score_restaurant()  (Bayesian rating + distance)
   └─ sort (open first, score desc) → limit
   ▼
200 JSON: list[RankedRestaurant]   (summary, no menu)
```

## 5. Files

| File | Role |
|---|---|
| `app/schemas/restaurant.py` | `Location`, `MenuItem`, `Restaurant` (+ `matches`, `dishes_matching`), `RestaurantSearchQuery`, `RankedRestaurant` |
| `app/core/geo.py` | `haversine_km()` |
| `app/providers/restaurants.py` | `RestaurantProvider` Protocol + `get_restaurant_provider()` |
| `app/providers/mock_restaurants.py` | `normalize()`, `load_mock_restaurants()` (cached), `MockRestaurantProvider` |
| `app/data/mock_restaurants.json` | 12 fictional Chennai restaurants in a provider-specific format |
| `app/services/restaurant_search.py` | `bayesian_rating`, `score_restaurant`, `search_restaurants` |
| `app/api/restaurants.py` | `/restaurants/search`, `/restaurants/{restaurant_id}` |
| `app/config.py`, `.env.example` | `RESTAURANT_PROVIDER=mock` |
| `app/main.py` | mounts the router |
| `tests/test_geo.py` | distance correctness (3 tests) |
| `tests/test_restaurant_search.py` | normalization, matching, ranking, radius enforcement (13 tests) |
| `tests/test_restaurants_api.py` | auth, ranking via HTTP, validation (6 cases), detail, 404 (11 tests) |

## 6. Code Explanation

### Normalization with validation
```python
def normalize(raw: dict[str, Any]) -> Restaurant:
    return Restaurant(
        id=f"{PROVIDER_NAME}:{raw['slug']}",          # provider-prefixed: IDs never clash between providers
        rating=raw["stars"],                            # validated: 0 ≤ rating ≤ 5
        price_level=_price_level_from_cost_for_two(raw["cost_for_two"]),
        menu=[MenuItem(name=d["dish"], price_minor=_to_minor_units(d["price"]), currency="INR") ...],
        ...
    )
```

### Load once, share safely
```python
@lru_cache
def load_mock_restaurants() -> tuple[Restaurant, ...]:
```
`lru_cache` with no arguments means the file is read and parsed once per process. It returns a **tuple** (immutable), because a cached *list* could be modified by one request and affect every later one.

### Sort key trick
```python
results.sort(key=lambda r: (not r.is_open, -r.score))
```
Tuples compare element by element. `not is_open` is `False` (= 0) for open restaurants, so they come first. `-score` makes higher scores come first within each group.

### Auth override in tests
```python
app.dependency_overrides[get_current_user] = lambda: User(email="test@example.com")
```
The restaurant tests don't care *how* login works (Phase 3 tests cover that), only that a user exists. So they need no database. One test runs **without** the override to prove `401`.

## 7. Request Flow

`GET /restaurants/search?query=chicken%20biryani&lat=13.0418&lng=80.2341&limit=3`:

1. **Router dependency** `get_current_user` reads the `access_token` cookie, decodes the JWT and checks the session (Phase 3). Fails → `401`.
2. FastAPI builds `RestaurantSearchQuery` from the query string. It strips whitespace and checks lengths and ranges. Fails → `422`.
3. `get_restaurant_provider()` → `MockRestaurantProvider` (data already cached).
4. `search_restaurants`:
   1. `provider.search` keeps restaurants where some field contains "chicken" **and** "biryani", within 5 km.
   2. For each: haversine distance, radius re-check, `dishes_matching`, `score_restaurant`.
   3. Sort, then take the first 3.
5. `200` with a list of `RankedRestaurant`. The menu isn't included; the client calls `GET /restaurants/{id}` for details.

## 8. Important Decisions

| Decision | Why | Trade-off |
|---|---|---|
| Provider abstraction (Protocol) | real API coming; tests need deterministic data | one more module |
| No `restaurants` table | data belongs to the provider; bookings will snapshot | no offline search over our own data |
| Foreign-format JSON + `normalize()` | practises the real translation job | slightly more code than a pre-normalized file |
| Ranking in code, not the LLM | consistent, free, testable, explainable | weights are hand-tuned |
| Bayesian average | robust to few reviews | prior constants are a judgement call |
| Open restaurants first | recommending a closed place is useless | static `is_open` in the mock (real hours later) |
| Service re-checks the radius | don't trust external data | duplicate distance computation |
| Search requires login | real APIs cost money and have rate limits | no anonymous browsing |
| One query model for API, service and tool | single source of truth for constraints | query param named `query` (not the shorter `q`) |
| Provider ignores `limit` | rank first, then cut | provider returns more data |

## 9. Common Mistakes

1. Letting a provider's raw JSON spread through the codebase. Switching providers then means a rewrite.
2. Floats for money.
3. Flat x/y distance on latitude/longitude.
4. Sorting by raw average rating (the 5.0★ from 2 reviews problem).
5. Asking the LLM to do ranking arithmetic: inconsistent, slow, costly.
6. Cutting to `limit` before ranking.
7. Trusting external data (no validation, no radius re-check).
8. Declaring `/{id}` before `/search`.
9. Caching a mutable list shared across requests.
10. Storing external data you then have to keep in sync, without needing to.
11. No upper bounds on radius/limit. Somebody will request 10,000 results from your paid API.

## 10. Testing

```bash
cd backend && source ../.venv/bin/activate
pytest -v                    # expect: 68 passed
pytest tests/test_restaurant_search.py -v    # just this phase's logic
```

| Test group | Proves |
|---|---|
| geo | distance is 0 for the same point, ≈290 km Chennai→Bengaluru, symmetric |
| normalization | foreign format → our model; `"349.90"` → `34990`; invalid data rejected |
| matching | case-insensitive; multi-word must match within one dish |
| ranking | Bayesian penalty for few reviews; closer wins on equal rating; score in [0,1]; open first; limit |
| radius safety | a sloppy provider's far result is still excluded |
| API | 401 without login; ranked JSON; 6 kinds of invalid input → 422; detail with integer prices; 404 |

**Manual** (log in first, as in Phase 3):
```bash
curl -c jar.txt -H 'Content-Type: application/json' \
     -d '{"email":"me@example.com","password":"correct horse battery"}' localhost:8000/auth/login
curl -b jar.txt "localhost:8000/restaurants/search?query=biryani&lat=13.0418&lng=80.2341"
curl -b jar.txt "localhost:8000/restaurants/search?query=dosa&lat=13.0339&lng=80.2619&radius_km=2"
curl -b jar.txt "localhost:8000/restaurants/mock:saffron-dum-house"
curl -b jar.txt "localhost:8000/restaurants/search?query=biryani&lat=200&lng=80"   # 422
```
Or use `/docs`: log in with `/auth/login`, then try `/restaurants/search`. The query parameters show up as form fields.

**Try it yourself:** change `RATING_WEIGHT`/`DISTANCE_WEIGHT` in `restaurant_search.py`, rerun the search, and watch the order change. Then see which tests catch it.

## 11. Interview Questions

1. Why put an abstraction in front of external data providers? When would that abstraction be over-engineering?
2. What's normalization / an anti-corruption layer?
3. `typing.Protocol` vs `abc.ABC`: what's the difference and when would you use each?
4. Why should money never be stored as a float? How do payment APIs represent amounts?
5. How do you compute the distance between two GPS coordinates? Why not Euclidean distance?
6. How would you rank restaurants so a 5.0★ with 2 reviews doesn't beat a 4.6★ with 3,000?
7. Why do the ranking in code and not with the LLM? What *should* the LLM do in this flow?
8. Should restaurant data be stored in your database? What about in a booking?
9. Why apply `limit` after ranking, not in the provider?
10. Why validate data from your own mock or from a trusted provider?
11. What happens if you declare `/restaurants/{id}` before `/restaurants/search` in FastAPI?
12. How would you add a real provider (e.g. Google Places) without changing the API or the service?
13. How would you scale geo search to millions of restaurants? (Spatial index / PostGIS / geohash.)

## 12. What I Should Understand Before Continuing

- [ ] I can explain why the provider translates data and why the rest of the app never sees raw provider JSON.
- [ ] I know the difference between our Pydantic `Restaurant` and our SQLAlchemy `User`.
- [ ] I can explain why prices are integers in minor units.
- [ ] I can explain Protocol vs ABC and how the provider is injected (and overridden in tests).
- [ ] I can compute the Bayesian average for one restaurant by hand.
- [ ] I can explain which component filters, which ranks, and why the service re-checks the radius.
- [ ] I know how I'd add a `GooglePlacesProvider` (new class + `normalize()` + one config value).
- [ ] `pytest -v` shows 68 passed, and I've tried searches for biryani, dosa and pizza myself.
