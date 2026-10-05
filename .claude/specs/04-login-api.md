# Spec: POST /api/login — User Authentication Endpoint

**ID:** `04-login-api`
**Status:** Ready for implementation
**Depends on:** `03-signup-api` (users collection and AuthRepository must exist)

---

## 1. Context

The frontend login page (`frontend/pages/login.py`) already exists. It POSTs to `POST /api/login` with `{"username": "...", "password": "..."}` and navigates to `/upload` on any 2xx response. Per the user story, it must also extract the JWT token from the response body and write it to `sessionStorage` — a one-line addition to the existing `_handle_submit()` function.

The backend currently has only `POST /api/signup` in `src/api/auth.py`. The login endpoint extends the existing auth layer in three files — no new files are needed. `AuthRepository.find_by_username()` and `AuthUtils.validate_hash_password()` are already implemented and are the only repository/utility methods required.

---

## 2. Endpoint Contract

### Request

```
POST /api/login
Content-Type: application/json
```

```json
{
  "username": "alice",
  "password": "s3cur3P@ss"
}
```

| Field      | Type   | Constraints                     |
|------------|--------|---------------------------------|
| `username` | string | required, min length 3, max 150 |
| `password` | string | required, min length 8, max 128 |

### Success Response — `200 OK`

```json
{
  "token": "<jwt-string>"
}
```

### Error Responses

| Scenario                       | Status | Body                                                                   |
|--------------------------------|--------|------------------------------------------------------------------------|
| Validation failure (bad input) | 422    | FastAPI default (Pydantic validation error with `detail` list)         |
| Username not found             | 401    | `{ "success": false, "error": "Invalid username or password" }`        |
| Password mismatch              | 401    | `{ "success": false, "error": "Invalid username or password" }`        |
| Unexpected server error        | 500    | `{ "success": false, "error": "Internal server error" }`               |

> **Security note:** Both "username not found" and "password mismatch" return the identical 401 message and body to prevent user enumeration attacks. Never expose which field failed.

---

## 3. Files to Modify

No new files. The login feature extends the existing auth layer:

```
src/
  schemas/auth.py      ← add LoginRequest, LoginResponse
  services/auth.py     ← add login() method to AuthService
  api/auth.py          ← add POST /api/login route; update imports
frontend/
  pages/login.py       ← store JWT token in sessionStorage on success
```

---

## 4. Layer Specifications

### 4.1 `src/schemas/auth.py` — Add LoginRequest and LoginResponse

**`LoginRequest(BaseModel)`**

| Field      | Type | Constraints                          |
|------------|------|--------------------------------------|
| `username` | str  | `Field(min_length=3, max_length=150)` |
| `password` | str  | `Field(min_length=8, max_length=128)` |

**`LoginResponse(BaseModel)`**

| Field   | Type | Description |
|---------|------|-------------|
| `token` | str  | JWT string  |

> `LoginResponse` is a dedicated class — do not reuse `SignupResponse` even though the shape is identical. Each endpoint owns its schema.

---

### 4.2 `src/services/auth.py` — Add `login()` to AuthService

Add the following method to the `AuthService` class:

```python
def login(self, payload: LoginRequest) -> LoginResponse:
    try:
        user = self._repo.find_by_username(payload.username)
    except pymongo.errors.PyMongoError as e:
        logger.error(f"DB error on find_by_username: {e}")
        raise AppException("Internal server error", status_code=500)

    if not user or not AuthUtils.validate_hash_password(payload.password, user["password"]):
        raise AppException("Invalid username or password", status_code=401)

    token = AuthUtils.create_access_token({"sub": payload.username})
    return LoginResponse(token=token)
```

**Step-by-step logic:**
1. Call `self._repo.find_by_username(payload.username)`. Wrap in a pymongo error guard.
2. If `user` is `None` **or** `AuthUtils.validate_hash_password(payload.password, user["password"])` returns `False`, raise `AppException("Invalid username or password", status_code=401)`.
3. Both failure branches use the **same** message — never leak which check failed.
4. On success, call `AuthUtils.create_access_token({"sub": payload.username})` and return `LoginResponse(token=token)`.

**Rules:**
- Catch only `pymongo.errors.PyMongoError`; never catch `AppException`.
- The canonical password check method is `AuthUtils.validate_hash_password(plain, hashed)` — do not rename or alias it.
- No `print()`. Use `logger.info()` / `logger.error()`.

---

### 4.3 `src/api/auth.py` — Add `/login` Route

Add the import for `LoginRequest` and `LoginResponse` to the existing import line from `src.schemas.auth`:

```python
from src.schemas.auth import SignupRequest, SignupResponse, LoginRequest, LoginResponse
```

Add the route to `auth_router`:

```python
@auth_router.post("/login", response_model=LoginResponse, status_code=200)
async def login(payload: LoginRequest):
    return _service.login(payload)
```

**Rules:**
- No try/except — `AppException` is caught globally by `main.py`.
- `response_model` is mandatory.
- Route function must be `async`.
- No `print()`.

---

### 4.4 `frontend/pages/login.py` — Store JWT in sessionStorage

In the `_handle_submit()` function, update the success branch (currently lines 60-62). Replace:

```python
if 200 <= response.status_code < 300:
    ui.navigate.to("/upload")
    return
```

With:

```python
if 200 <= response.status_code < 300:
    import json
    token = response.json().get("token", "")
    ui.run_javascript(f"sessionStorage.setItem('token', {json.dumps(token)})")
    ui.navigate.to("/upload")
    return
```

> `ui.run_javascript` is required because NiceGUI page handlers run server-side in Python; `sessionStorage` is a browser-side API. `json.dumps(token)` properly escapes the token string for safe JavaScript interpolation.

---

## 5. Test Plan

### Unit Tests — `tests/unit/test_auth_service.py`

Extend the existing file. Mock `AuthRepository` with `unittest.mock.MagicMock`.

| Test case              | Setup                                                                    | Expected                                     |
|------------------------|--------------------------------------------------------------------------|----------------------------------------------|
| Successful login       | `find_by_username` returns a dict with a valid bcrypt hash; password matches | Returns `LoginResponse` with non-empty `token` |
| Username not found     | `find_by_username` returns `None`                                        | Raises `AppException` with `status_code=401` |
| Wrong password         | `find_by_username` returns a user dict; password does not match          | Raises `AppException` with `status_code=401` |
| DB error on lookup     | `find_by_username` raises `pymongo.errors.PyMongoError`                  | Raises `AppException` with `status_code=500` |

> For the "successful login" test, generate a real bcrypt hash in the test with `AuthUtils.hash_password("securepass1")` and store it in the mock return value — do not mock `validate_hash_password` itself, as that method is a project invariant.

### End-to-End Tests — `tests/e2e/test_auth_api.py`

Extend the existing file. Use a fixture that creates a test user via `POST /api/signup` before running login tests, and drops the `users` collection in teardown.

| Test case               | Request                                                      | Expected status | Expected body                                                    |
|-------------------------|--------------------------------------------------------------|-----------------|------------------------------------------------------------------|
| Valid credentials       | `{ "username": "alice", "password": "securepass1" }`         | `200`           | `{ "token": "<non-empty string>" }`                              |
| Username not found      | `{ "username": "ghost", "password": "securepass1" }`         | `401`           | `{ "success": false, "error": "Invalid username or password" }`  |
| Wrong password          | `{ "username": "alice", "password": "wrongpassword1" }`      | `401`           | `{ "success": false, "error": "Invalid username or password" }`  |
| Short password (422)    | `{ "username": "alice", "password": "short" }`               | `422`           | FastAPI validation error with `detail` list                      |
| Missing password field  | `{ "username": "alice" }`                                    | `422`           | FastAPI validation error with `detail` list                      |

---

## 6. Out of Scope

- Logout endpoint or token invalidation.
- Token refresh / sliding expiry.
- Rate limiting or account lockout after failed attempts.
- Persistent token storage (`localStorage` or cookies) — only `sessionStorage` is in scope.
- Frontend auth guard on `/login` (no redirect if already authenticated).
- Reading or forwarding the stored token on the `/upload` page — that is a separate user story.
- Any change to `src/main.py`, `src/db/`, `src/utils/`, or `src/repository/` — all required code already exists.
