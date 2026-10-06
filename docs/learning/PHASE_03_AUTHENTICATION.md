# Phase 3 — Authentication and Sessions

## 1. Goal

Let users register, log in, stay logged in safely, and log out, and give every future endpoint a one-line way to require a logged-in user.

| Endpoint | Purpose |
|---|---|
| `POST /auth/register` | create user (Argon2id-hashed password) → `201` |
| `POST /auth/login` | verify password, create server-side session, set HttpOnly cookies |
| `GET /auth/me` | first protected endpoint |
| `POST /auth/refresh` | rotate the refresh token, issue a new access token → `204` |
| `POST /auth/logout` | revoke the session, clear cookies → `204` (idempotent) |

Plus the `get_current_user` dependency (`CurrentUser` type alias).

## 2. Why do we need this?

Every later feature needs to know **who** is asking:
- whose booking is this (Phase 10)?
- who approved this payment, and are they allowed to (Phase 11)?
- which user should the webhook result be pushed to (Phase 12)?

Authentication is the foundation for **authorization**. A payment system with weak auth is a payment system anyone can use.

## 3. Concepts

### 3.1 Authentication vs authorization
- **Authentication:** *who are you?* Failure → `401`.
- **Authorization:** *may you do this?* Failure → `403` (or `404` to hide existence). It starts in Phase 10.

### 3.2 Password hashing with Argon2id
- Store `hash(password)`, never the password, and never in a reversible (encrypted) form.
- **Salt:** random bytes mixed in per password and stored inside the hash string. The same password gives different hashes, so rainbow tables are useless.
- **Slow and memory-hard on purpose:** about 50 ms and 64 MB per hash. A user never notices; an attacker with a leaked database can try only a handful of guesses per second per core, instead of billions with SHA-256.
- The hash string carries its own parameters: `$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>`. That's what lets `check_needs_rehash` upgrade old hashes at the next login.

### 3.3 Sessions vs JWT and our hybrid

| | Server session | Pure JWT | **Ours (hybrid)** |
|---|---|---|---|
| Identity proof | random ID → DB lookup | signed claims, no DB | signed claims **and** a session lookup |
| Instant logout | ✔ | ✘ (wait for expiry) | ✔ |
| Forged token rejected before DB | n/a | ✔ | ✔ |

Our access JWT carries `sub` (user), `sid` (session), `type`, `iat`, `exp`. Each request checks the signature (crypto) **and** that session `sid` is still valid (one primary-key lookup).

### 3.4 JWT
- `header.payload.signature`, base64url. **Signed, not encrypted**: anyone can read the payload, so put no secrets in it.
- The signature is an HMAC-SHA256 over header+payload with `JWT_SECRET_KEY`. Change one character of the payload and verification fails.
- Always decode with `algorithms=["HS256"]`, so a token can't choose `"none"` or a different algorithm.
- `options={"require": [...]}` rejects tokens that are missing claims.

### 3.5 Access token + refresh token

| | Access | Refresh |
|---|---|---|
| Format | JWT | opaque random (`secrets.token_urlsafe(32)`) |
| Lifetime | 15 min | 7 days (absolute) |
| Cookie path | `/` (every request) | `/auth` (refresh and logout only) |
| Server stores | nothing | `sha256(token)` in `user_sessions` |

**Why SHA-256 is fine for refresh tokens but not for passwords:** the token has 256 bits of randomness, so there's nothing to guess. We also need a deterministic hash to find the session. A salted Argon2 hash can't be looked up.

### 3.6 Rotation
Each refresh replaces the stored hash, so the previous refresh token stops working. A stolen refresh token dies as soon as the real user refreshes.
- **Not built yet:** reuse detection, where presenting an old token revokes the whole session (assume theft). It needs a record of previous hashes.

### 3.7 Cookies and their flags

| Flag | Defends against |
|---|---|
| `HttpOnly` | XSS stealing the token (`document.cookie` can't see it) |
| `Secure` | sending the token over plain HTTP (`COOKIE_SECURE=true` in production; startup **fails** otherwise) |
| `SameSite=Lax` | CSRF: cookie not sent on cross-site POST/fetch |
| `Path=/auth` | long-lived refresh token travelling with every API call |
| `Max-Age` | browser keeping expired tokens |

Why not `localStorage`? Any injected script can read it and send the token to an attacker's server.

### 3.8 CSRF
Browsers attach cookies automatically, so a malicious site could make your browser send a POST. Our defences:
1. `SameSite=Lax`
2. JSON-only request bodies (an HTML form can't send `application/json`; a cross-site `fetch` triggers a CORS preflight we'll deny in Phase 8)
3. Planned: a CSRF token for payment actions (Phase 11/13)

### 3.9 Foreign keys, relationships, cascade

```python
user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)   # database level
sessions = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)  # Python level
```
- **Foreign key:** the database refuses a session pointing to a non-existent user.
- **`ON DELETE CASCADE`:** deleting a user deletes their sessions *in the database* (verified manually: 1 session → 0 after deleting the user).
- **`relationship()`:** Python navigation (`user.sessions`, `session.user`). It creates no SQL constraint. Adding it produced **no** migration change.
- **`passive_deletes=True`:** let the database cascade instead of SQLAlchemy loading every session first.
- **Index on `user_id`:** PostgreSQL doesn't index foreign keys automatically, and "all sessions of user X" (log out everywhere) needs it.

### 3.10 Concurrency: `SELECT … FOR UPDATE`
Two tabs refresh at the same moment with the same refresh token. Without a lock, both read the session, both rotate, and both get valid tokens. `with_for_update()` locks the row: the second request waits, then finds the hash already changed → `401`.

### 3.11 Anti-enumeration
- Login returns the same `401 "Invalid email or password"` for a wrong password and for an unknown email.
- For an unknown email we still run an Argon2 verify against `DUMMY_PASSWORD_HASH`, so **timing** doesn't reveal it either.
- Known trade-off: register returns `409` for a taken email. Rate limiting (Phase 13) is the mitigation.

### 3.12 Input validation with Pydantic
- `EmailStr` for the email format.
- Password length between 8 and 128 (the upper bound prevents CPU-burning huge inputs to Argon2).
- `extra="forbid"`: unknown fields like `"is_superuser": true` → `422`. That's a defence against *mass assignment*.
- `response_model=UserRead`: `hashed_password` can never appear in a response, even by accident.

### 3.13 `SecretStr`
`jwt_secret_key: SecretStr` prints as `'**********'`. If settings are ever logged or appear in a traceback, the secret doesn't. Use `.get_secret_value()` only where it's really needed.

## 4. Architecture

```
            ┌──────────── HTTP layer: app/api/ ─────────────┐
Request ──► │ auth.py (routes)   cookies.py (flags)          │
            │ deps.py: get_current_user ──┐                  │
            └──────────────┬──────────────┼──────────────────┘
                           ▼              ▼
            ┌──── Business logic: app/services/auth.py ─────┐
            │ register · authenticate · create/rotate/revoke │
            └──────────────┬──────────────┬──────────────────┘
                           ▼              ▼
            app/core/security.py     app/models/ (User, UserSession)
            (pure crypto, no DB)          │
                                          ▼
                                     PostgreSQL
                              users ◄──FK CASCADE── user_sessions
```

| Layer | Knows about | Doesn't know about |
|---|---|---|
| `api/` | HTTP, cookies, status codes | how sessions are stored |
| `services/` | database, business rules | HTTP, cookies |
| `core/security.py` | cryptography | database, HTTP |

Each layer can be tested on its own. `test_security.py` runs with no database at all.

## 5. Files

| File | Role |
|---|---|
| `app/config.py` | `jwt_secret_key` (SecretStr, ≥32 chars), token lifetimes, `cookie_secure`; production requires secure cookies |
| `app/core/security.py` | Argon2 hashing, JWT create/decode, refresh token generate/hash |
| `app/models/user.py` | `normalize_email()`, `sessions` relationship |
| `app/models/user_session.py` | `UserSession` model, `is_valid()` |
| `app/models/__init__.py` | registers `UserSession` for Alembic |
| `alembic/versions/0002_create_user_sessions_table.py` | table + FK + unique hash + index |
| `app/schemas/auth.py` | `RegisterRequest`, `LoginRequest`, `UserRead` |
| `app/services/auth.py` | all session/user logic and its exceptions |
| `app/api/cookies.py` | cookie names and flags in one place |
| `app/api/deps.py` | `DbSession`, `get_current_user`, `CurrentUser` |
| `app/api/auth.py` | the five endpoints |
| `app/main.py` | mounts the auth router |
| `requirements.txt` | `argon2-cffi`, `pyjwt` (passlib and python-jose removed and uninstalled) |
| `.env.example` | auth variables documented |
| `tests/test_security.py` | 11 crypto unit tests |
| `tests/test_auth.py` | 15 HTTP flow tests |
| `tests/test_config.py` | secret length, secret hidden, production cookie rule |

## 6. Code Explanation

### Registration relies on the database, not a pre-check
```python
db.add(user)
try:
    db.commit()
except IntegrityError:
    db.rollback()
    raise EmailAlreadyRegisteredError from None
```
A `SELECT … WHERE email=?` check first would be a race: two simultaneous requests could both see "free". The UNIQUE constraint decides. `from None` hides the database exception chain, which is an internal detail.

### Getting the session ID before committing
```python
db.add(session)
db.flush()          # sends the INSERT inside the transaction; session.id now known
access_token = create_access_token(user.id, session.id)
db.commit()
```
- **`flush`** = send the pending SQL to the database (still inside the transaction).
- **`commit`** = make it permanent.

The JWT needs `session.id`. Reading it *after* commit would trigger an extra SELECT, because SQLAlchemy expires objects on commit.

### The dependency chain
```python
def get_current_user(db: DbSession, access_token: Annotated[str | None, Cookie()] = None) -> User:
```
- `Cookie()` tells FastAPI to read the cookie with the same name as the parameter.
- Every failure raises the **same** `401 "Not authenticated"`, so attackers learn nothing about *which* check failed.
- A route opts in with one parameter: `def me(user: CurrentUser)`.

### Cookie deletion needs a matching path
`delete_cookie("refresh_token", path="/auth")`. A cookie is identified by name + domain + path. Deleting with `path="/"` would leave the `/auth` cookie alive.

## 7. Request Flow

**Login:**
1. FastAPI validates the body against `LoginRequest` (otherwise `422`).
2. `authenticate_user`: normalize the email, then `SELECT` the user and Argon2-verify the password (or the dummy hash if there's no such user).
3. `create_session`:
   1. Generate the refresh token.
   2. `INSERT user_sessions(hash, expires_at)`, then flush.
   3. Sign the JWT `{sub, sid, exp}`, then commit.
4. `set_auth_cookies` adds two `Set-Cookie` headers.
5. Response: `200` + `UserRead` JSON. No tokens in the body.

**`GET /auth/me`:**
1. The browser sends `Cookie: access_token=…`.
2. `get_current_user`:
   1. Decode the JWT (signature, `exp`, `type`).
   2. `db.get(UserSession, sid)`: is it revoked or expired, or does `user_id` not match?
   3. Is the user inactive?
3. Return the user → serialized via `UserRead`.

**Refresh:**
1. The browser sends `Cookie: refresh_token=…`. It's sent because the path `/auth/refresh` is under `/auth`.
2. `SELECT … WHERE refresh_token_hash = sha256(token) FOR UPDATE`.
3. Valid → new random token, store its hash (the old one dies), sign a new JWT, commit.
4. Two new `Set-Cookie` headers, `204`.

**Logout:** find the session by the refresh token hash → `revoked_at = now()` → clear both cookies → `204`.

## 8. Important Decisions

| Decision | Why | Trade-off |
|---|---|---|
| Session check on every request | instant logout/deactivation; money is involved | one indexed lookup per request |
| JWT for access tokens | forged/expired tokens rejected without DB; claims usable by WebSocket/MCP later | more moving parts than a plain session ID |
| Opaque refresh token, hashed | revocable; a DB leak doesn't leak usable tokens | needs a DB row |
| Absolute 7-day session expiry | bounded lifetime even with constant refreshing | re-login weekly |
| `argon2-cffi` directly | small, maintained, OWASP-recommended algorithm | — |
| PyJWT (not python-jose) | widely used, actively maintained | — |
| `SameSite=Lax` + JSON-only, CSRF token later | strong baseline without extra machinery yet | add a CSRF token before payments |
| `revoked_at` instead of DELETE | audit trail | table grows; clean up old rows later |
| Register doesn't auto-login | each endpoint does one thing | one extra request for the client |
| Service layer introduced | login and refresh share logic; HTTP kept separate | one more module |

## 9. Common Mistakes

1. Storing plaintext, or a fast hash (MD5/SHA-256), for passwords.
2. Putting secrets or personal data in the JWT payload. It's readable.
3. Decoding JWTs without pinning `algorithms` (the `alg: none` attack).
4. Storing tokens in `localStorage` (XSS theft).
5. Long-lived access tokens with no revocation.
6. Storing raw refresh tokens in the database.
7. Different error messages for "no such user" and "wrong password" (user enumeration).
8. Checking uniqueness with a SELECT before INSERT (race condition).
9. Returning the ORM object without a response model (`hashed_password` leaks).
10. Forgetting `Secure` cookies in production. We fail at startup to prevent it.
11. Deleting a cookie with a different `path` than it was set with.
12. Hardcoding `JWT_SECRET_KEY`. Anyone with it can impersonate any user.

## 10. Testing

```bash
cd backend && source ../.venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head          # applies 0002 to your dev DB
pytest -v                     # expect: 41 passed
```

| Group | What it proves |
|---|---|
| `test_security.py` | Argon2id + salt; JWT round trip; expired, forged, tampered, `alg:none` and wrong-type tokens all rejected |
| register tests | hashed storage, no password in the response, case-insensitive duplicate → 409, validation incl. extra fields |
| login tests | HttpOnly/SameSite/Path flags, identical failure messages, only the hash stored server-side |
| refresh tests | rotation; replaying the old token → 401 (with a positive control); expired session → 401 |
| logout/deactivation | a still-unexpired JWT stops working immediately |
| config tests | short secret fails, secret hidden in repr, production requires secure cookies |

**Manual flow with curl** (`-c` saves cookies to a file, `-b` sends them):
```bash
uvicorn app.main:app --reload
H='Content-Type: application/json'
curl -i -H "$H" -d '{"email":"me@example.com","password":"correct horse battery"}' localhost:8000/auth/register
curl -i -c jar.txt -H "$H" -d '{"email":"me@example.com","password":"correct horse battery"}' localhost:8000/auth/login
curl -b jar.txt localhost:8000/auth/me                                  # 200 + user
curl -b jar.txt -c jar.txt -X POST -i localhost:8000/auth/refresh       # 204 + new cookies
curl -b jar.txt -c jar.txt -X POST -i localhost:8000/auth/logout        # 204
curl -b jar.txt localhost:8000/auth/me                                  # 401
rm jar.txt
```
In `/docs` (Swagger UI), cookies work too: log in there and `/auth/me` succeeds.

## 11. Interview Questions

1. Authentication vs authorization: give an example of each in a booking system.
2. Why hash passwords instead of encrypting them? What's a salt? Why must password hashing be slow?
3. Why is SHA-256 acceptable for refresh tokens but not for passwords?
4. What's inside a JWT? Is it encrypted? What does the signature guarantee?
5. What's the `alg: none` attack, and how do you prevent it?
6. Stateless JWT vs server-side sessions: trade-offs? How do you revoke a JWT?
7. Why have both access and refresh tokens? Why is the refresh token's cookie path restricted?
8. What's refresh token rotation? What's reuse detection?
9. HttpOnly cookies vs `localStorage` for tokens: which attacks does each expose you to?
10. What's CSRF? How do `SameSite` cookies and JSON-only APIs mitigate it?
11. How do you prevent user enumeration on login? What about timing attacks?
12. Two requests refresh with the same token at the same moment. What can go wrong, and how does `SELECT … FOR UPDATE` help?
13. Foreign key vs SQLAlchemy `relationship()`: what does each do? What does `ON DELETE CASCADE` do?
14. Why rely on a UNIQUE constraint instead of checking whether an email exists first?
15. What's mass assignment, and how does `extra="forbid"` help?

## 12. What I Should Understand Before Continuing

- [ ] I can explain how Argon2 verifies a password without storing it.
- [ ] I can decode a JWT by hand (base64) and explain why changing it breaks the signature.
- [ ] I can draw the login → request → refresh → logout timeline and say where each token travels.
- [ ] I know why logout is instant in our design but wouldn't be with a pure JWT.
- [ ] I can explain each cookie flag and the attack it defends against.
- [ ] I can explain the FK + `ON DELETE CASCADE` + index on `user_sessions.user_id`.
- [ ] I know how to protect a new endpoint: `def endpoint(user: CurrentUser)`.
- [ ] I know which layer (api / services / core) new auth-related code belongs in.
- [ ] `pytest -v` shows 41 passed, and I ran the curl flow myself.
