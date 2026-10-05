# Test Plan: POST /api/signup

**Source spec:** `.claude/specs/03-signup-spec.md`  
**Endpoint:** `POST /api/signup`  
**Layers under test:** `schemas/auth.py`, `utils/auth.py`, `repository/auth.py`, `services/auth.py`, `api/auth.py`, `db/mongo_connection.py`

---

## 1. Unit Tests

**Location:** `tests/unit/test_auth_service.py`  
**Tool:** `pytest` + `unittest.mock.MagicMock`  
**Scope:** `AuthService` in complete isolation — repository is mocked, no DB, no JWT validation.

### Setup

```python
from unittest.mock import MagicMock, patch
import pytest
from src.services.auth import AuthService
from src.schemas.auth import SignupRequest
from src.utils.exception import AppException

@pytest.fixture
def mock_repo():
    with patch("src.services.auth.AuthRepository") as MockRepo:
        instance = MockRepo.return_value
        yield instance

@pytest.fixture
def service(mock_repo):
    return AuthService()
```

---

### 1.1 Happy Path

| ID | Test name | Setup | Call | Assert |
|----|-----------|-------|------|--------|
| U-01 | `test_signup_returns_token_on_success` | `mock_repo.find_by_username` → `None`; `mock_repo.insert_user` → `"507f1f77bcf86cd799439011"` | `service.signup(SignupRequest(username="alice", password="securepass1"))` | Returns `SignupResponse`; `response.token` is a non-empty string |
| U-02 | `test_signup_token_contains_username_sub` | Same as U-01 | Same | Decode the returned JWT (without verification); assert `payload["sub"] == "alice"` |
| U-03 | `test_signup_stores_hashed_password_not_plaintext` | `mock_repo.find_by_username` → `None` | `service.signup(...)` | Capture the `document` passed to `mock_repo.insert_user`; assert `document["password"] != "securepass1"` and `bcrypt.checkpw(b"securepass1", document["password"].encode())` is `True` |
| U-04 | `test_signup_stores_correct_username` | `mock_repo.find_by_username` → `None` | `service.signup(SignupRequest(username="bob", password="securepass1"))` | `document["username"] == "bob"` in the `insert_user` call |

---

### 1.2 Conflict / Duplicate

| ID | Test name | Setup | Call | Assert |
|----|-----------|-------|------|--------|
| U-05 | `test_signup_raises_409_when_username_taken` | `mock_repo.find_by_username` → `{"username": "alice", "password": "<hash>"}` | `service.signup(SignupRequest(username="alice", password="securepass1"))` | Raises `AppException`; `exc.status_code == 409`; `exc.message == "Username already taken"` |
| U-06 | `test_signup_does_not_call_insert_when_username_taken` | Same as U-05 | Same | `mock_repo.insert_user.assert_not_called()` |

---

### 1.3 Database Error Handling

| ID | Test name | Setup | Call | Assert |
|----|-----------|-------|------|--------|
| U-07 | `test_signup_raises_500_on_insert_failure` | `mock_repo.find_by_username` → `None`; `mock_repo.insert_user` raises `pymongo.errors.PyMongoError` | `service.signup(...)` | Raises `AppException` with `status_code == 500` |
| U-08 | `test_signup_raises_500_on_find_failure` | `mock_repo.find_by_username` raises `pymongo.errors.PyMongoError` | `service.signup(...)` | Raises `AppException` with `status_code == 500` |
| U-09 | `test_app_exception_is_not_rewrapped` | `mock_repo.find_by_username` → existing user (triggers 409) | `service.signup(...)` | The caught `AppException` has exactly `status_code=409`; it is not wrapped into a 500 |

---

### 1.4 AuthUtils Unit Tests

**Location:** `tests/unit/test_auth_utils.py`

| ID | Test name | Call | Assert |
|----|-----------|------|--------|
| U-10 | `test_hash_password_returns_bcrypt_hash` | `AuthUtils.hash_password("mypassword")` | Result starts with `"$2b$"` |
| U-11 | `test_validate_hash_password_correct` | `AuthUtils.validate_hash_password("mypassword", AuthUtils.hash_password("mypassword"))` | Returns `True` |
| U-12 | `test_validate_hash_password_wrong` | `AuthUtils.validate_hash_password("wrongpassword", AuthUtils.hash_password("mypassword"))` | Returns `False` |
| U-13 | `test_hash_produces_different_salts` | Call `hash_password("same")` twice | Two hashes are not equal (salt randomness) |
| U-14 | `test_create_access_token_contains_sub` | `AuthUtils.create_access_token({"sub": "alice"})` | Decoded payload has `"sub": "alice"` |
| U-15 | `test_create_access_token_contains_exp` | `AuthUtils.create_access_token({"sub": "alice"})` | Decoded payload has `"exp"` key; value is in the future |

---

### 1.5 MongoDBConnection Unit Tests

**Location:** `tests/unit/test_mongo_connection.py`

| ID | Test name | Setup | Call | Assert |
|----|-----------|-------|------|--------|
| U-16 | `test_get_collection_raises_before_connect` | Fresh class state (`_client = None`) | `MongoDBConnection.get_collection("users")` | Raises `AppException` with `status_code == 500` |
| U-17 | `test_connect_is_idempotent` | Call `connect()` once with a mock client | Call `connect()` again | Second call does not create a second `MongoClient`; client instance is the same object |

---

## 2. Integration Tests

**Location:** `tests/e2e/test_auth_api.py`  
**Tool:** `fastapi.testclient.TestClient` + a real MongoDB test database  
**Database:** Use `DATABASE_NAME=decision_intelligence_test_db` via env override in `conftest.py`  
**Teardown:** Drop the `users` collection after each test (or after each test session).

### Setup

```python
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.db.mongo_connection import MongoDBConnection

@pytest.fixture(autouse=True)
def clean_users():
    yield
    MongoDBConnection.get_collection("users").drop()

client = TestClient(app)
```

---

### 2.1 Success Path

| ID | Test name | Request body | Expected status | Expected response |
|----|-----------|-------------|-----------------|-------------------|
| I-01 | `test_signup_201_returns_token` | `{"username": "alice", "password": "securepass1"}` | `201` | Body has key `"token"`; value is a non-empty string |
| I-02 | `test_signup_token_is_valid_jwt` | Same | `201` | Decode `response.json()["token"]` with `python-jose`; assert `payload["sub"] == "alice"` |
| I-03 | `test_signup_persists_user_in_db` | `{"username": "bob", "password": "securepass1"}` | `201` | Query `users` collection directly; document with `username="bob"` exists; `password` field is a bcrypt hash (starts with `$2b$`) |
| I-04 | `test_signup_does_not_store_plaintext_password` | `{"username": "carol", "password": "securepass1"}` | `201` | Query DB; `document["password"] != "securepass1"` |

---

### 2.2 Conflict / Duplicate

| ID | Test name | Setup | Expected status | Expected response body |
|----|-----------|-------|-----------------|------------------------|
| I-05 | `test_signup_409_on_duplicate_username` | POST `alice` once successfully; POST `alice` again | `409` | `{"success": false, "error": "Username already taken"}` |
| I-06 | `test_signup_duplicate_is_case_sensitive` | POST `alice`; POST `Alice` | `201` for the second | Two separate users exist in DB (usernames are case-sensitive) |

---

### 2.3 Validation Failures (422)

| ID | Test name | Request body | Expected status | Expected detail |
|----|-----------|-------------|-----------------|-----------------|
| I-07 | `test_signup_422_username_too_short` | `{"username": "ab", "password": "securepass1"}` | `422` | `detail` list contains a `min_length` violation for `username` |
| I-08 | `test_signup_422_password_too_short` | `{"username": "alice", "password": "short"}` | `422` | `detail` list contains a `min_length` violation for `password` |
| I-09 | `test_signup_422_missing_username` | `{"password": "securepass1"}` | `422` | `detail` mentions missing `username` field |
| I-10 | `test_signup_422_missing_password` | `{"username": "alice"}` | `422` | `detail` mentions missing `password` field |
| I-11 | `test_signup_422_empty_body` | `{}` | `422` | `detail` lists both missing fields |
| I-12 | `test_signup_422_wrong_content_type` | Send as `application/x-www-form-urlencoded` | `422` | FastAPI rejects non-JSON body |

---

### 2.4 Response Shape Contract

| ID | Test name | Assert |
|----|-----------|--------|
| I-13 | `test_success_response_has_no_extra_fields` | `response.json().keys() == {"token"}` — no `_id`, `password`, `username` leaked |
| I-14 | `test_error_response_shape` | On 409, body is exactly `{"success": false, "error": "Username already taken"}` |
| I-15 | `test_content_type_is_json` | `response.headers["content-type"]` starts with `"application/json"` for both success and error |

---

## 3. Security Tests

**Location:** `tests/security/test_auth_security.py`

### 3.1 Password Storage

| ID | Test name | How | Assert |
|----|-----------|-----|--------|
| S-01 | `test_password_is_bcrypt_hashed_in_db` | Sign up, query DB directly | Stored value starts with `$2b$`; `bcrypt.checkpw` succeeds |
| S-02 | `test_plaintext_password_not_in_db` | Sign up with `"securepass1"`, query DB | No field in the document equals `"securepass1"` |
| S-03 | `test_plaintext_password_not_in_response` | POST `/api/signup` | `"securepass1"` does not appear anywhere in the raw response text |

### 3.2 JWT Security

| ID | Test name | How | Assert |
|----|-----------|-----|--------|
| S-04 | `test_jwt_has_expiry` | Decode returned token | `"exp"` claim is present and is a future timestamp |
| S-05 | `test_jwt_signed_with_secret` | Attempt to decode the token with a wrong secret | `jose.exceptions.JWTError` is raised |
| S-06 | `test_jwt_algorithm_is_hs256` | Decode token header | `alg == "HS256"` (or whichever `JWT_ALGORITHM` env var specifies) |
| S-07 | `test_jwt_payload_does_not_contain_password` | Decode returned token (no verification needed for payload inspection) | `"password"` key is absent from payload |

### 3.3 Injection & Malformed Input

| ID | Test name | Request body | Assert |
|----|-----------|-------------|--------|
| S-08 | `test_nosql_injection_in_username` | `{"username": {"$gt": ""}, "password": "securepass1"}` | Returns `422` — Pydantic rejects non-string value; no DB query executed |
| S-09 | `test_script_tag_in_username` | `{"username": "<script>alert(1)</script>", "password": "securepass1"}` | Returns `422` (fails `min_length=3` after strip — or 201 if length ≥ 3; stored raw, never rendered by the API) |
| S-10 | `test_null_byte_in_password` | `{"username": "alice", "password": "pass\x00word1"}` | Returns `201` or `422`; assert the null byte is not silently truncated to match a different stored value |
| S-11 | `test_unicode_username` | `{"username": "用户名test", "password": "securepass1"}` | Returns `201`; stored correctly in DB |
| S-12 | `test_very_long_username_rejected` | `username` of 151 chars | `422` |
| S-13 | `test_very_long_password_rejected` | `password` of 129 chars | `422` |

### 3.4 Sensitive Data in Logs / Responses

| ID | Test name | How | Assert |
|----|-----------|-----|--------|
| S-14 | `test_password_not_logged` | Capture log output during signup via `caplog` fixture | The plain-text password string does not appear in any log record |
| S-15 | `test_internal_error_does_not_leak_stack_trace` | Force a DB error (stop Mongo or mock an exception); call the endpoint | Response body is `{"success": false, "error": "Internal server error"}`; no stack trace or pymongo details in body |

---

## 4. Edge Cases

**Location:** `tests/unit/test_auth_edge_cases.py` and `tests/e2e/test_auth_api.py`

### 4.1 Boundary Values

| ID | Test name | Input | Expected |
|----|-----------|-------|----------|
| E-01 | `test_username_exactly_min_length` | `username` = `"abc"` (3 chars) | `201` — boundary is inclusive |
| E-02 | `test_username_exactly_max_length` | `username` = `"a" * 150` | `201` |
| E-03 | `test_username_one_below_min` | `username` = `"ab"` (2 chars) | `422` |
| E-04 | `test_username_one_above_max` | `username` = `"a" * 151` | `422` |
| E-05 | `test_password_exactly_min_length` | `password` = `"12345678"` (8 chars) | `201` |
| E-06 | `test_password_exactly_max_length` | `password` = `"a" * 128` | `201` |
| E-07 | `test_password_one_below_min` | `password` = `"1234567"` (7 chars) | `422` |
| E-08 | `test_password_one_above_max` | `password` = `"a" * 129` | `422` |

### 4.2 Whitespace Handling

| ID | Test name | Input | Expected |
|----|-----------|-------|----------|
| E-09 | `test_username_with_leading_spaces` | `username` = `"  alice"` | `201` (Pydantic does not strip by default; stored as-is) |
| E-10 | `test_username_all_spaces` | `username` = `"   "` (≥3 chars) | `201` unless a custom `@field_validator` strips and re-validates — **note:** spec does not require stripping; test documents actual behaviour |
| E-11 | `test_password_with_spaces` | `password` = `"pass word1"` | `201` — spaces are valid in passwords |

### 4.3 Concurrency / Race Condition (Integration)

| ID | Test name | How | Expected |
|----|-----------|-----|----------|
| E-12 | `test_concurrent_signup_same_username` | Send two simultaneous `POST /api/signup` requests for the same username using `threading.Thread` | Exactly one returns `201`, the other returns `409` (relies on unique index in MongoDB as the final guard) |

### 4.4 Repeated Calls

| ID | Test name | How | Expected |
|----|-----------|-----|----------|
| E-13 | `test_different_users_get_different_tokens` | Sign up `alice` and `bob` | Tokens differ; each contains the correct `sub` |
| E-14 | `test_same_user_signup_twice_returns_409` | POST same credentials twice | First: `201`; second: `409` with `"Username already taken"` |

### 4.5 MongoDB Connection Not Initialized

| ID | Test name | How | Expected |
|----|-----------|-----|----------|
| E-15 | `test_request_before_db_connect_returns_500` | Call endpoint with `MongoDBConnection._client = None` (reset class state after patching) | Returns `500` with `{"success": false, "error": ...}`; no unhandled exception crashes the server |

---

## 5. Test Infrastructure Notes

### conftest.py

```python
# tests/conftest.py
import os
import pytest
from src.db.mongo_connection import MongoDBConnection
from src.logging.logger import setup_logging

os.environ.setdefault("DATABASE_NAME", "decision_intelligence_test_db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-minimum-32-chars!!")

setup_logging()

@pytest.fixture(scope="session", autouse=True)
def connect_test_db():
    MongoDBConnection.connect(
        os.environ["MONGO_URI"],
        os.environ["DATABASE_NAME"],
    )
    yield
    MongoDBConnection.close()
```

### Running the tests

```bash
# All tests
uv run pytest

# Unit only (fast, no DB required)
uv run pytest tests/unit/

# E2E only (requires MongoDB)
uv run pytest tests/e2e/

# Security tests
uv run pytest tests/security/

# Verbose with log capture
uv run pytest -v --log-cli-level=INFO
```

### Coverage target

| Layer | Target |
|---|---|
| `services/auth.py` | 100% |
| `utils/auth.py` | 100% |
| `repository/auth.py` | ≥ 90% |
| `api/auth.py` | 100% |
| `db/mongo_connection.py` | ≥ 80% |

```bash
uv run pytest --cov=src --cov-report=term-missing
```
