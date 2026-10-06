# Phase 1 — Project Foundation

## 1. Goal

Build a backend skeleton that is **runnable, configurable, testable, and safe to put in Git**:

- A FastAPI application served by Uvicorn
- A `GET /health` liveness endpoint
- Typed, validated configuration from environment variables
- Pinned dependencies, split into runtime vs development
- A repository-wide `.gitignore` that protects secrets
- The first automated tests

There are no business features yet, on purpose.

## 2. Why do we need this?

Every later phase plugs into this foundation:

| Later phase         | Depends on this foundation for...             |
| ------------------- | --------------------------------------------- |
| Database            | `settings.database_url`                     |
| Auth                | secret keys from config, routers              |
| Agent / LLM         | API keys from config (never in code)          |
| Payments / Webhooks | webhook secrets from config, tests            |
| Production          | health checks for load balancers / Kubernetes |

Mistakes here are cheap to fix now and expensive later. For example, a payment API key committed to Git is in the history forever, and an app that can't be tested without a live database slows down every future change.

## 3. Concepts

### 3.1 Virtual environment

An isolated Python installation for one project (`.venv/`). Without it, all projects on your machine share one set of packages, and upgrading FastAPI for project A can break project B.

```bash
python -m venv .venv          # create
source .venv/bin/activate     # use it in this shell
which python                  # -> .../AI_RESTAURANT_AGENT/.venv/bin/python
```

### 3.2 ASGI, Uvicorn, FastAPI: three layers

```
Network (TCP socket)
   ↓
Uvicorn   — the *server*: accepts connections, parses raw HTTP bytes
   ↓  calls app(scope, receive, send)   ← this interface is "ASGI"
FastAPI   — the *framework*: routing, validation, JSON, OpenAPI docs
   ↓
Your function — returns a dict
```

- **FastAPI doesn't listen on a port.** It's just a Python object (`app`). Uvicorn runs it.
- **ASGI** (Asynchronous Server Gateway Interface) replaces the older **WSGI** (used by Flask/Django classic). WSGI is one request → one response, synchronously. ASGI supports `async`, long-lived connections, and **WebSockets**, which we need in Phase 9 for live agent progress.

### 3.3 Configuration from the environment (12-factor app)

Rule: **the same code runs everywhere; only the environment changes.**

|                  | Development    | Production       |
| ---------------- | -------------- | ---------------- |
| Code             | identical      | identical        |
| `DATABASE_URL` | local Postgres | managed Postgres |
| `ENVIRONMENT`  | development    | production       |

Secrets (DB passwords, LLM keys, payment keys) live in environment variables, never in source files.

### 3.4 `pydantic-settings` vs `os.getenv`

```python
# Before: silent failure
DATABASE_URL = os.getenv("DATABASE_URL")   # None if missing, crashes much later

# After: typed + validated at startup
class Settings(BaseSettings):
    environment: Literal["development", "test", "production"] = "development"
```

If `ENVIRONMENT=prod` (a typo), the app **refuses to start** with a clear `ValidationError`. That's the **fail fast** principle: catch problems at boot, not at 2 a.m. halfway through a payment.

Lookup order for a field like `app_name`:

1. A real environment variable `APP_NAME` (highest priority)
2. A line `APP_NAME=...` in `.env`
3. The default in the class

So production (no `.env` file, real env vars from the platform) and development (a `.env` file) both work with the same code.

### 3.5 `.env` vs `.env.example`

| File             | Contains                     | Committed?              |
| ---------------- | ---------------------------- | ----------------------- |
| `.env`         | real values, secrets         | **Never**         |
| `.env.example` | variable names + fake values | Yes, it's documentation |

A new developer runs `cp .env.example .env` and fills it in.

### 3.6 Liveness vs readiness

| Check                         | Question                     | Touches DB?  | Phase |
| ----------------------------- | ---------------------------- | ------------ | ----- |
| `/health` (liveness)        | "Is the process alive?"      | **No** | 1     |
| `/health/ready` (readiness) | "Can it serve real traffic?" | Yes          | 2     |

Why it matters: Kubernetes restarts a container whose liveness check fails. If liveness checked the DB, a DB outage would make Kubernetes restart **every healthy app server in a loop**, which makes the outage worse.

### 3.7 `APIRouter`

A router groups related endpoints. `main.py` stays a thin "assembly" file:

```python
app.include_router(health_router)
# later: app.include_router(auth_router), app.include_router(restaurants_router), ...
```

### 3.8 Dependency pinning

`fastapi` → "whatever is newest today". `fastapi==0.142.2` → the exact version we tested. Without pins, a fresh install months from now may pull a release with breaking changes, and you get "works on my machine" bugs.

- `requirements.txt`: runtime dependencies (installed in production)
- `requirements-dev.txt`: `-r requirements.txt` + test tools (not installed in production, which means a smaller attack surface and image)

### 3.9 `TestClient`

FastAPI's `TestClient` calls the app **in-process**: no Uvicorn, no port, no network. Tests run in milliseconds and don't depend on anything external.

## 4. Architecture

```
 curl / browser / pytest(TestClient)
            │  HTTP
            ▼
        Uvicorn  (ASGI server)
            │
            ▼
   FastAPI app ── app/main.py
            │ include_router
            ▼
   app/api/health.py  ──► {"status": "ok"}

   app/config.py (Settings) ◄── environment variables / backend/.env
```

The database isn't connected at request time in this phase. That's deliberate.

## 5. Files

```
AI_RESTAURANT_AGENT/
├── .gitignore                    # repo-wide: .env, .venv, node_modules, caches
├── docs/learning/PHASE_01_PROJECT_FOUNDATION.md
└── backend/
    ├── .env                      # YOUR real values (git-ignored)
    ├── .env.example              # template, committed
    ├── requirements.txt          # pinned runtime deps
    ├── requirements-dev.txt      # + pytest, httpx2
    ├── pytest.ini                # tells pytest where code/tests live
    ├── app/
    │   ├── __init__.py           # marks `app` as a package
    │   ├── main.py               # creates FastAPI app, mounts routers
    │   ├── config.py             # Settings class + `settings` instance
    │   ├── api/
    │   │   ├── __init__.py
    │   │   └── health.py         # GET /health
    │   └── db/                   # (pre-existing, finished in Phase 2)
    └── tests/
        ├── test_health.py        # endpoint tests
        └── test_config.py        # configuration validation tests
```

Changes to code that already existed:

- `app/main.py`: removed the DB connection from `/`, now uses settings and the router.
- `app/config.py`: `os.getenv` replaced by `Settings`.
- `app/db/database.py`, `alembic/env.py`: import `settings` instead of the removed `DATABASE_URL` constant (one line each).
- `backend/.gitignore`: removed, replaced by the root `.gitignore`.
- `requirements.txt`: pinned. `passlib` and `python-jose` were removed and will be re-evaluated in Phase 3 (passlib is barely maintained and conflicts with modern bcrypt; PyJWT is the more common, better-maintained JWT choice). `python-dotenv` was removed because `pydantic-settings` already depends on it.

## 6. Code Explanation

### `app/config.py`

```python
model_config = SettingsConfigDict(
    env_file=".env",
    extra="ignore",
)
```

- `env_file=".env"` is resolved **relative to the current working directory**, so run the app from `backend/`.
- `extra="ignore"`: if `.env` contains keys that `Settings` doesn't declare, ignore them instead of crashing.

```python
database_url: str | None = None
```

This is optional **only in Phase 1** so the API can start without Postgres. Phase 2 makes it required, so a missing DB URL becomes a startup error.

```python
settings = Settings()
```

A single module-level instance, created once at import. The simplest choice. (A FastAPI-docs alternative is `@lru_cache def get_settings()` + `Depends`, which makes overriding settings in tests easier. We'll switch if we need it.)

### `app/api/health.py`

```python
router = APIRouter(tags=["health"])

@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- `tags` groups the endpoint in the `/docs` UI.
- The return type hint is used by FastAPI for the OpenAPI schema.
- It's a plain `def`, not `async def`, because there's nothing to await. (FastAPI runs sync endpoints in a threadpool, so they don't block the event loop.)

### `tests/test_config.py`

```python
settings = Settings(_env_file=None)
```

`_env_file=None` tells this one instance to **skip your real `.env`**, so the test only sees variables set via `monkeypatch.setenv`. Tests must not depend on a developer's local files.

## 7. Request Flow

`curl http://127.0.0.1:8000/health`:

1. curl opens a TCP connection to port 8000.
2. **Uvicorn** reads the bytes `GET /health HTTP/1.1 ...` and builds an ASGI `scope` dict (method, path, headers).
3. Uvicorn calls the FastAPI `app` with that scope.
4. FastAPI's router matches `GET /health` → `health()`.
5. `health()` returns `{"status": "ok"}`.
6. FastAPI serialises it to JSON and sets `Content-Type: application/json` and status `200`.
7. Uvicorn writes the HTTP response back to the socket.

If the path doesn't match any route, FastAPI returns `404 {"detail": "Not Found"}`.

## 8. Important Decisions

| Decision                                                       | Why                                                                          | Trade-off                                                                                                  |
| -------------------------------------------------------------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `/health` doesn't touch the DB                               | Liveness must not depend on external services                                | Need a separate readiness check (Phase 2)                                                                  |
| `pydantic-settings`                                          | Validation + types + fail fast                                               | One more concept to learn                                                                                  |
| Module-level`settings`                                       | Simplest                                                                     | Slightly harder to override in tests                                                                       |
| pip +`requirements*.txt`                                     | You already used it, and it's universal                                      | No lockfile for transitive deps.`uv`/Poetry with `pyproject.toml` is the modern alternative (Phase 13) |
| No app factory / service layer yet                             | Nothing needs them                                                           | We'll add them when there's a real need                                                                    |
| Root`.gitignore`, `.env.*` blocked except `.env.example` | Protects secrets anywhere in the repo, including a future`frontend/.env`   | —                                                                                                         |
| `httpx2` in dev requirements                                 | Starlette now prefers`httpx2` for `TestClient` (it warns with `httpx`) | —                                                                                                         |

## 9. Common Mistakes

1. **Committing `.env`.** Even if you delete it later, it stays in Git history. If that happens, *rotate the secret*. Deleting the file isn't enough.
2. **Health checks that call the database.** This causes cascading restarts during outages.
3. **`os.getenv` without validation.** You get `None` and a confusing crash far from the cause.
4. **Unpinned dependencies.** Builds that aren't reproducible.
5. **Installing test tools in production.** Keep them in `requirements-dev.txt`.
6. **Running Uvicorn from the wrong directory.** `.env` isn't found and `import app` fails. Run from `backend/`.
7. **Using `--reload` in production.** It's a dev convenience that watches files and costs CPU.
8. **Installing packages outside the venv.** Always check `which python`.

## 10. Testing

**What:** the endpoints respond correctly, unknown routes 404, settings read env vars, invalid settings are rejected.
**Why:** this proves the app boots and config validation works, and it sets up the habit that every phase adds tests.

```bash
cd backend
source ../.venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```

Expected: `5 passed`.

Manual check:

```bash
uvicorn app.main:app --reload
# in another terminal:
curl http://127.0.0.1:8000/health      # {"status":"ok"}
curl http://127.0.0.1:8000/            # {"message":"AI Restaurant Agent API is running","docs":"/docs"}
# open http://127.0.0.1:8000/docs in a browser (Swagger UI)
```

Fail-fast check:

```bash
ENVIRONMENT=prod uvicorn app.main:app   # should crash with a ValidationError
```

## 11. Interview Questions

1. What's the difference between ASGI and WSGI? Why does FastAPI use ASGI?
2. What role does Uvicorn play? Why can't FastAPI serve requests by itself?
3. What's the difference between liveness and readiness probes? What goes wrong if liveness checks the database?
4. How do you manage configuration and secrets across dev, staging and production?
5. Why pin dependency versions? What's the difference between pinning direct dependencies and a lockfile?
6. Someone committed an API key to Git and then deleted the file in the next commit. Is that fixed? What do you do?
7. What's the difference between `def` and `async def` endpoints in FastAPI?
8. How does `TestClient` test an app without starting a server?
9. Why separate runtime and development dependencies?
10. What does "fail fast" mean for configuration, and why is it valuable?

## 12. What I Should Understand Before Continuing

- [ ] I can explain the Uvicorn → ASGI → FastAPI → route chain.
- [ ] I know why `/health` doesn't touch the database.
- [ ] I know where each setting comes from (env var > `.env` > default).
- [ ] I know why `.env` is ignored and `.env.example` is committed.
- [ ] I can add a new setting to `Settings` and read it via `settings.x`.
- [ ] I can add a new route with `APIRouter` and mount it in `main.py`.
- [ ] I can run the tests and the server, and open `/docs`.
- [ ] I can answer the interview questions above in my own words.
