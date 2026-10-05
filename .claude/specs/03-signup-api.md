# Spec: POST /api/signup — User Registration Endpoint

## 1. Context

The frontend signup page (`frontend/pages/signup.py`) already exists and POSTs to `POST /api/signup` with a JSON body of `{ username, password }`. It expects a `2xx` response on success and reads a `detail` field from error responses. The backend (`src/`) has only a placeholder `main.py` — the entire FastAPI application and supporting layers must be built from scratch.

---

## 2. Endpoint Contract

### Request

```
POST /api/signup
Content-Type: application/json
```

```json
{
  "username": "alice",
  "password": "s3cur3P@ss"
}
```

| Field      | Type   | Constraints                        |
|------------|--------|------------------------------------|
| `username` | string | required, min length 3, max 150    |
| `password` | string | required, min length 8, max 128    |

### Success Response — `201 Created`

```json
{
  "token": "<jwt-string>"
}
```

### Error Responses

| Scenario                          | Status | Body                                                     |
|-----------------------------------|--------|----------------------------------------------------------|
| Validation failure (bad input)    | 422    | FastAPI default (Pydantic validation error with `detail` list) |
| Username already taken            | 409    | `{ "success": false, "error": "Username already taken" }` |
| Unexpected server error           | 500    | `{ "success": false, "error": "Internal server error" }` |

> The frontend reads `response.json().get("detail", "")` for non-5xx errors. Because Pydantic validation errors already use `detail`, and our `AppException` global handler emits `{ "success": false, "error": ... }`, the frontend's `msg` fallback path covers both cases correctly. No special mapping is needed.

---

## 3. Files to Create

Following the mandatory layered architecture (`api/ → services/ → repository/ → db/`):

```
src/
  main.py                   ← replace placeholder; wire FastAPI app
  db/
    __init__.py
    mongo_connection.py     ← MongoDBConnection singleton
  schemas/
    __init__.py
    auth.py                 ← SignupRequest, SignupResponse
  repository/
    __init__.py
    auth.py                 ← AuthRepository
  services/
    __init__.py
    auth.py                 ← AuthService
  api/
    __init__.py
    auth.py                 ← auth_router (POST /api/signup)
  utils/
    __init__.py
    auth.py                 ← AuthUtils (bcrypt + JWT)
    exception.py            ← AppException + global handler registration
  logging/
    __init__.py
    logger.py               ← setup_logging()
tests/
  unit/
    test_auth_service.py
  e2e/
    test_auth_api.py
```

---

## 4. Layer Specifications

### 4.1 `src/db/mongo_connection.py` — MongoDBConnection Singleton

**Purpose:** Provide a single shared MongoDB client across the application lifetime.

**Class:** `MongoDBConnection`

| Member | Signature | Description |
|---|---|---|
| `connect` | `classmethod(uri: str, database_name: str) → None` | Initialises `MongoClient`, stores client + db on the class. Idempotent if already connected. |
| `get_collection` | `classmethod(name: str) → Collection` | Returns the named collection. Raises `AppException(500)` if `connect()` was never called. |
| `close` | `classmethod() → None` | Closes the client; used in test teardown. |

**State variables** (class-level):
- `_client: MongoClient | None = None`
- `_db: Database | None = None`

---

### 4.2 `src/schemas/auth.py` — Pydantic Models

**`SignupRequest(BaseModel)`**

| Field      | Type | Constraints |
|------------|------|-------------|
| `username` | str  | `Field(min_length=3, max_length=150)` |
| `password` | str  | `Field(min_length=8, max_length=128)` |

**`SignupResponse(BaseModel)`**

| Field   | Type | Description               |
|---------|------|---------------------------|
| `token` | str  | JWT string, no expiry info |

---

### 4.3 `src/repository/auth.py` — AuthRepository

**Class:** `AuthRepository`

Access collection via `@property _collection → MongoDBConnection.get_collection("users")`.

| Method | Signature | Description |
|---|---|---|
| `find_by_username` | `(username: str) → dict \| None` | `find_one({"username": username})`. Logs entry with `logger.info`. |
| `insert_user` | `(document: dict) → str` | `insert_one(document)`, returns `str(inserted_id)`. |

No business logic. Raises pymongo exceptions unmodified; the service converts them.

---

### 4.4 `src/utils/auth.py` — AuthUtils

**Class:** `AuthUtils`

Reads from environment: `JWT_SECRET`, `JWT_ALGORITHM` (default `"HS256"`), `JWT_EXPIRES_IN` (seconds, default `3600`).

| Method | Signature | Description |
|---|---|---|
| `hash_password` | `staticmethod(plain: str) → str` | `bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()` |
| `validate_hash_password` | `staticmethod(plain: str, hashed: str) → bool` | `bcrypt.checkpw(plain.encode(), hashed.encode())` |
| `create_access_token` | `staticmethod(data: dict) → str` | Encodes `{**data, "exp": now + expires_in}` via `jose.jwt.encode`. |

> `validate_hash_password` is the canonical name; callers must use this name to avoid the bug noted in CLAUDE.md.

---

### 4.5 `src/services/auth.py` — AuthService

**Class:** `AuthService`

```python
def __init__(self):
    self._repo = AuthRepository()
```

| Method | Signature | Returns |
|---|---|---|
| `signup` | `(payload: SignupRequest) → SignupResponse` | Creates user, returns token |

**`signup` logic:**
1. `self._repo.find_by_username(payload.username)` — if result exists, raise `AppException("Username already taken", status_code=409)`.
2. `hashed = AuthUtils.hash_password(payload.password)`
3. `self._repo.insert_user({"username": payload.username, "password": hashed})`
4. `token = AuthUtils.create_access_token({"sub": payload.username})`
5. Return `SignupResponse(token=token)`

Catch only low-level (pymongo) exceptions and re-raise as `AppException("Internal server error", status_code=500)`. Never catch `AppException`.

---

### 4.6 `src/api/auth.py` — auth_router

```python
auth_router = APIRouter(prefix="/api", tags=["Auth"])
_service = AuthService()

@auth_router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(payload: SignupRequest):
    return _service.signup(payload)
```

- No try/except — `AppException` is caught by the global handler in `main.py`.
- No print statements.

---

### 4.7 `src/utils/exception.py` — AppException

```python
class AppException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
```

Global handler (registered in `main.py`):

```python
@app.exception_handler(AppException)
async def app_exception_handler(request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.message},
    )
```

---

### 4.8 `src/main.py` — Application Entry Point

Responsibilities (in order):
1. `setup_logging()` — before any import that logs.
2. Load `.env` via `python-dotenv`.
3. `MongoDBConnection.connect(MONGO_URI, DATABASE_NAME)` — on startup.
4. Create `FastAPI` app instance.
5. Register `AppException` global handler.
6. `app.include_router(auth_router)`.

---

## 5. Dependencies to Add

The current `pyproject.toml` only lists frontend packages. Add the following backend dependencies:

```bash
uv add fastapi uvicorn[standard] pymongo python-dotenv bcrypt python-jose[cryptography]
```

| Package | Purpose |
|---|---|
| `fastapi` | Web framework |
| `uvicorn[standard]` | ASGI server |
| `pymongo` | MongoDB driver |
| `python-dotenv` | Load `.env` |
| `bcrypt` | Password hashing |
| `python-jose[cryptography]` | JWT encoding/decoding |

---

## 6. Environment Variables

Add these to the `.env` file in the project root (referenced in CLAUDE.md):

```
MONGO_URI=mongodb://localhost:27017
DATABASE_NAME=decision_intelligence_db
JWT_SECRET=<your-secret-min-32-chars>
JWT_EXPIRES_IN=3600
JWT_ALGORITHM=HS256
```

---

## 7. MongoDB Collection

- Collection name: `users`
- Stored document shape: `{ _id: ObjectId, username: str, password: str (bcrypt hash) }`
- Index: unique index on `username` field (enforces uniqueness at the DB level as a safety net).

---

## 8. Test Plan

### Unit Tests — `tests/unit/test_auth_service.py`

Mock `AuthRepository` with `unittest.mock.MagicMock`.

| Test case | Setup | Expected |
|---|---|---|
| Successful signup | `find_by_username` returns `None`; `insert_user` returns a fake id | Returns `SignupResponse` with a non-empty `token` |
| Username already taken | `find_by_username` returns an existing user dict | Raises `AppException` with `status_code=409` |
| DB error on insert | `insert_user` raises `pymongo.errors.PyMongoError` | Raises `AppException` with `status_code=500` |

### End-to-End Tests — `tests/e2e/test_auth_api.py`

Use `fastapi.testclient.TestClient` against a test MongoDB database. Drop the `users` collection in teardown.

| Test case | Request | Expected status | Expected body |
|---|---|---|---|
| Valid signup | `{ "username": "alice", "password": "securepass1" }` | `201` | `{ "token": "<non-empty string>" }` |
| Duplicate username | Same payload twice | `409` on second | `{ "success": false, "error": "Username already taken" }` |
| Short username | `{ "username": "ab", "password": "securepass1" }` | `422` | FastAPI validation error |
| Short password | `{ "username": "alice", "password": "short" }` | `422` | FastAPI validation error |
| Missing field | `{ "username": "alice" }` | `422` | FastAPI validation error |

---

## 9. Out of Scope

- Login endpoint (`POST /api/login`) — separate user story.
- Email verification or multi-factor auth.
- Rate limiting.
- Frontend changes — `frontend/pages/signup.py` is already complete and compatible with this contract.
