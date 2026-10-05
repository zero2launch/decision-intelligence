# Signup Flow Review

**Date:** 2026-06-28  
**Scope:** `src/api/auth.py`, `src/services/auth.py`, `src/repository/auth.py`, `src/schemas/auth.py`, `src/utils/auth.py`, `src/utils/exception.py`, `src/main.py`

---

## 1. Bugs

### 1.1 `DuplicateKeyError` Surfaced as 500 Instead of 409

**File:** `src/services/auth.py:29-33`

```python
try:
    self._repo.insert_user({"username": payload.username, "password": hashed})
except pymongo.errors.PyMongoError as e:
    logger.error(f"DB error on insert_user: {e}")
    raise AppException("Internal server error", status_code=500)
```

`pymongo.errors.DuplicateKeyError` is a subclass of `PyMongoError`. If two concurrent signup requests pass the `find_by_username` check simultaneously (TOCTOU race), MongoDB's unique index rejects the second `insert_one` with a `DuplicateKeyError` — but the service catches it as a generic `PyMongoError` and returns 500 "Internal server error" to the client instead of 409 "Username already taken".

**Fix:** Catch `DuplicateKeyError` before the generic `PyMongoError` catch and raise 409.

```python
except pymongo.errors.DuplicateKeyError:
    raise AppException("Username already taken", status_code=409)
except pymongo.errors.PyMongoError as e:
    logger.error(f"DB error on insert_user: {e}")
    raise AppException("Internal server error", status_code=500)
```

---

## 2. Security Issues

### 2.1 `JWT_SECRET` Raises Unhandled `KeyError` If Not Set

**File:** `src/utils/auth.py:20`

```python
secret = os.environ["JWT_SECRET"]
```

Using `os.environ["KEY"]` raises `KeyError` if the variable is absent. This propagates as an unhandled Python exception — FastAPI will return a raw 500 with a traceback rather than a controlled `AppException`. The secret-key check must be done at startup, not at call time.

**Fix:** Validate required env vars at application startup in `main.py` and fail fast with a clear message. Use `os.environ.get()` with an explicit guard:

```python
secret = os.environ.get("JWT_SECRET")
if not secret:
    raise AppException("JWT_SECRET is not configured", status_code=500)
```

### 2.2 No Username Case Normalization — Case-Variant Duplicates Allowed

**File:** `src/services/auth.py:19`, `src/schemas/auth.py`

`find_by_username` queries MongoDB with the exact casing the client sends. A user who registers as `"Alice"` does not block registration of `"alice"` or `"ALICE"`. These become separate accounts, which is almost certainly unintended and enables username-squatting attacks.

**Fix:** Normalize to lowercase (or store a `username_lower` index field) before the lookup and insert:

```python
normalized = payload.username.strip().lower()
existing = self._repo.find_by_username(normalized)
```

### 2.3 No Username Character-Set Validation

**File:** `src/schemas/auth.py:5`

```python
username: str = Field(min_length=3, max_length=150)
```

The only constraint is length. Usernames containing whitespace, control characters, unicode homoglyphs, or path-like sequences (e.g. `"../admin"`, `"alice\n"`) are accepted. This can cause display bugs and potential injection in downstream systems that embed the username.

**Fix:** Add a `pattern` constraint or `@field_validator` to allow only safe characters:

```python
username: str = Field(min_length=3, max_length=150, pattern=r"^[a-zA-Z0-9_\-\.]+$")
```

### 2.4 No Password Complexity Requirement

**File:** `src/schemas/auth.py:6`

```python
password: str = Field(min_length=8, max_length=128)
```

Only minimum length is enforced. A password like `"aaaaaaaa"` (8 identical characters) is accepted. Consider requiring at least one digit and one letter, or using a `zxcvbn`-style strength estimate.

### 2.5 Username Logged in Plain Text (PII Risk)

**File:** `src/repository/auth.py:15`

```python
logger.info(f"Finding user by username: {username}")
```

Usernames are written to `logs/app.log` in plain text. Depending on jurisdiction and data classification, usernames may be considered PII (GDPR Art. 4). Log files are often retained, forwarded to aggregation systems, and not subject to the same access controls as the database.

**Fix:** Either omit the value from the log or use a pseudonymized form (e.g. hash prefix) for correlation:

```python
logger.info(f"Finding user by username hash prefix: {hash(username) % 10000}")
```

---

## 3. Architecture Violations

### 3.1 DB Connect and Index Creation at Module Level in `main.py`

**File:** `src/main.py:20-27`

```python
MongoDBConnection.connect(
    uri=os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
    database_name=os.environ.get("DATABASE_NAME", "decision_intelligence_db"),
)

from pymongo import ASCENDING
MongoDBConnection.get_collection("users").create_index([("username", ASCENDING)], unique=True)
```

Both calls execute at **import time** — not inside a startup event handler. Consequences:

- **Breaks test isolation:** The e2e test had to set env vars before importing `app` to override the connection target. The `create_index` call also fires before any test fixture can intervene, and the index is lost after the first test drops the collection (subsequent tests run without the unique constraint).
- **Hides startup failures:** Errors thrown here are not caught by the global `AppException` handler. A misconfigured `MONGO_URI` crashes the import silently instead of logging a clear startup error.
- **Violates the "startup event" contract:** FastAPI provides `lifespan` context managers precisely for this kind of initialization.

**Fix:** Move all startup logic into a `lifespan` handler:

```python
from contextlib import asynccontextmanager
from pymongo import ASCENDING

@asynccontextmanager
async def lifespan(app: FastAPI):
    MongoDBConnection.connect(
        uri=os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
        database_name=os.environ.get("DATABASE_NAME", "decision_intelligence_db"),
    )
    MongoDBConnection.get_collection("users").create_index(
        [("username", ASCENDING)], unique=True
    )
    yield
    MongoDBConnection.close()

app = FastAPI(title="Decision Intelligence API", lifespan=lifespan)
```

### 3.2 `AppException.__init__` Does Not Call `super().__init__()`

**File:** `src/utils/exception.py:5-7`

```python
class AppException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
```

Not calling `super().__init__(message)` means `str(exc)` and `repr(exc)` return empty strings, and `exc.args` is an empty tuple. This breaks any generic exception logger that calls `str(exc)` or `exc.args[0]` — including Python's own traceback formatter.

**Fix:**

```python
def __init__(self, message: str, status_code: int = 400):
    super().__init__(message)
    self.message = message
    self.status_code = status_code
```

---

## 4. Error Handling

### 4.1 `app_exception_handler` Does Not Log the Error

**File:** `src/utils/exception.py:10-14`

```python
async def app_exception_handler(request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.message},
    )
```

Every `AppException` — including unexpected 500s — is returned to the client with no server-side log entry. A 500 from a DB failure is indistinguishable in the logs from a 409 from a duplicate username. Operators have no way to detect production errors without adding external monitoring.

**Fix:** Log 5xx exceptions at `ERROR` level and 4xx at `WARNING`:

```python
logger = logging.getLogger(__name__)

async def app_exception_handler(request, exc: AppException):
    if exc.status_code >= 500:
        logger.error(f"[{exc.status_code}] {request.method} {request.url.path} — {exc.message}")
    else:
        logger.warning(f"[{exc.status_code}] {request.method} {request.url.path} — {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.message},
    )
```

### 4.2 TOCTOU Race Covered Only at DB Level, Not in Error Path

Already described in **Bug 1.1**. The service's check-then-insert pattern is logically correct but the exception path for the constraint violation returns the wrong status code. The unique index in MongoDB is the correct second line of defense — it just needs to be handled properly.

---

## 5. Logging

### 5.1 No Success Log on Signup Completion

**File:** `src/services/auth.py`

The service logs DB errors but never logs a successful signup. This makes it impossible to trace a completed signup through the logs.

**Fix:** Add after token creation:

```python
logger.info(f"Signup successful for username: {payload.username}")
```

(Note: apply username PII policy from §2.5 consistently here too.)

### 5.2 Inconsistent Log Detail Between `find_by_username` and `insert_user`

**File:** `src/repository/auth.py`

- `find_by_username` logs the username: `"Finding user by username: {username}"`
- `insert_user` logs nothing about who is being inserted: `"Inserting new user document"`

This asymmetry makes log correlation across the two operations harder. Both should either include the username or omit it, consistently.

---

## Summary Table

| # | Severity | Category | Location | Issue |
|---|----------|----------|----------|-------|
| 1.1 | High | Bug | `services/auth.py:29` | `DuplicateKeyError` returned as 500, not 409 |
| 2.1 | High | Security | `utils/auth.py:20` | Missing `JWT_SECRET` raises unhandled `KeyError` |
| 2.2 | Medium | Security | `services/auth.py:19` | Case-variant usernames allowed (e.g. Alice vs alice) |
| 2.3 | Medium | Security | `schemas/auth.py:5` | No character-set constraint on username |
| 2.4 | Low | Security | `schemas/auth.py:6` | No password complexity beyond minimum length |
| 2.5 | Medium | Security | `repository/auth.py:15` | Username logged in plain text (PII) |
| 3.1 | High | Architecture | `main.py:20-27` | DB init and index creation at import time, not in startup handler |
| 3.2 | Low | Architecture | `utils/exception.py:6` | `AppException` omits `super().__init__()` |
| 4.1 | Medium | Error Handling | `utils/exception.py:10` | Global handler swallows errors without logging |
| 4.2 | High | Error Handling | `services/auth.py:29` | Race-condition duplicate not mapped to 409 (same as 1.1) |
| 5.1 | Low | Logging | `services/auth.py` | No log on successful signup |
| 5.2 | Low | Logging | `repository/auth.py` | Inconsistent username logging between repo methods |
