# API Design Rules

This document defines the mandatory rules for implementing any new API endpoint, service, or repository in this codebase. All backend code must follow these conventions.

---

## 1. Layer Responsibility

The backend follows a strict four-layer architecture. Each layer has one job and one job only.

```
HTTP Request
    ↓
api/         ← Controller: parse input, call service, return response
    ↓
services/    ← Business Logic: orchestrate, validate, raise domain errors
    ↓
repository/  ← Data Access: MongoDB queries only, no business logic
    ↓
db/          ← Connection: singleton, connection pooling
```

**Rules:**
- API routers must not contain business logic. They parse the request and delegate to the service.
- Services must not contain raw MongoDB queries. They call repository methods.
- Repositories must not raise HTTP-specific errors. They raise Python exceptions and let the service handle semantics.
- Never skip a layer. A router must not call `MongoDBConnection` directly.

---

## 2. File & Module Naming

For every new feature (e.g., `deals`), create one file per layer:

```
src/
  api/deals.py
  services/deals.py
  repository/deals.py
  schemas/deals.py
```

- File names are lowercase and match the feature name exactly across all layers.
- Router variable: `<feature>_router` (e.g., `deals_router`)
- Service class: `<Feature>Service` (e.g., `DealsService`)
- Repository class: `<Feature>Repository` (e.g., `DealsRepository`)
- Schema class: `<Feature>Request`, `<Feature>Response` (e.g., `CreateDealRequest`, `DealResponse`)

---

## 3. API Router (Controller Layer)

```python
from fastapi import APIRouter
from src.schemas.deals import CreateDealRequest, DealResponse
from src.services.deals import DealsService
from src.utils.exception import AppException
import logging

deals_router = APIRouter(prefix="/api/deals", tags=["Deals"])
logger = logging.getLogger(__name__)

_service = DealsService()

@deals_router.post("/", response_model=DealResponse)
async def create_deal(payload: CreateDealRequest):
    return _service.create_deal(payload)
```

**Rules:**
- Prefix must follow `/api/<feature>` pattern.
- Tag must match the feature name (displayed in Swagger UI).
- The service is instantiated once at module level as a private variable (`_service`).
- Router functions must be `async`.
- Every router must declare `response_model` so the API contract is explicit.
- No try/except in router functions — `AppException` is caught globally by `main.py`.
- No print statements. Use `logger`.
- Register every new router in `src/main.py` with `app.include_router(...)`.

---

## 4. Pydantic Schemas

```python
from pydantic import BaseModel, Field, field_validator

class CreateDealRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    value: float = Field(gt=0)
    status: str = Field(pattern=r"^(Won|Lost|Active)$")

class DealResponse(BaseModel):
    id: str
    name: str
    value: float
    status: str
```

**Rules:**
- All request models inherit from `pydantic.BaseModel`.
- Use `Field(...)` for every field with appropriate constraints (`min_length`, `gt`, `pattern`, etc.).
- Custom validation uses `@field_validator` with `@classmethod`.
- Response models must never expose internal fields like `_id`, `password`, or `hashed` values.
- Response models must always map MongoDB `_id` to a string `id`.
- Separate request and response schemas. Never reuse a request model as a response.

---

## 5. Service Layer

```python
from src.repository.deals import DealsRepository
from src.utils.exception import AppException
import logging

logger = logging.getLogger(__name__)

class DealsService:
    def __init__(self):
        self._repo = DealsRepository()

    def create_deal(self, payload) -> dict:
        existing = self._repo.find_by_name(payload.name)
        if existing:
            raise AppException("A deal with this name already exists", status_code=409)
        deal_id = self._repo.insert(payload.model_dump())
        return {"id": deal_id, **payload.model_dump()}
```

**Rules:**
- Services instantiate their own repository in `__init__`. No global repository singletons.
- All domain errors are raised as `AppException(message, status_code=<appropriate HTTP code>)`.
- Services must never swallow `AppException`. Only catch lower-level exceptions (e.g., pymongo errors) and re-raise them as `AppException`.
- Services are not `async`. MongoDB calls via pymongo are synchronous.
- Never use `print()`. Always use `logger.info()`, `logger.warning()`, `logger.error()`.
- Business validation (uniqueness, state checks, authorization) lives here, not in the router or repository.

**HTTP status code reference:**
| Situation | Status Code |
|-----------|-------------|
| Resource not found | 404 |
| Conflict (duplicate) | 409 |
| Bad request / validation | 400 |
| Unauthorized | 401 |
| Forbidden | 403 |
| Unexpected server error | 500 |

---

## 6. Repository Layer

```python
from src.db.mongo_connection import MongoDBConnection
import logging

logger = logging.getLogger(__name__)

class DealsRepository:

    @property
    def _collection(self):
        return MongoDBConnection.get_collection("deals")

    def find_by_name(self, name: str):
        logger.info(f"Finding deal by name: {name}")
        return self._collection.find_one({"name": name})

    def insert(self, document: dict) -> str:
        result = self._collection.insert_one(document)
        return str(result.inserted_id)

    def find_by_id(self, deal_id: str):
        from bson import ObjectId
        return self._collection.find_one({"_id": ObjectId(deal_id)})
```

**Rules:**
- Collections are accessed via `@property` using `MongoDBConnection.get_collection(name)`. Never store the collection as an instance variable — MongoDB connection must already be initialized.
- Repository methods only contain pymongo query logic.
- Repositories raise lower-level exceptions (pymongo errors); the service layer converts these to `AppException`.
- Every public method must have a `logger.info(...)` at entry.
- Log `logger.error(...)` before re-raising any caught exception.
- Use `ObjectId` from `bson` when querying by `_id`. Always convert `_id` to `str` before returning to upper layers.

---

## 7. Exception Handling

The single exception type is `AppException` from `src/utils/exception.py`.

```python
class AppException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
```

**Rules:**
- Never raise a plain `Exception` in service or router code. Always raise `AppException`.
- Never catch `AppException` and wrap it again — this creates double-wrapped errors. The pattern:
  ```python
  # WRONG
  try:
      ...
  except Exception as e:
      raise AppException(str(e), 500)   # hides AppException raised inside

  # CORRECT — only catch low-level exceptions
  try:
      user = self._repo.get_user_by_username(username)
  except Exception as e:
      logger.error(f"DB error: {e}")
      raise AppException("Database error", status_code=500)
  if not user:
      raise AppException("User not found", status_code=404)
  ```
- The global handler in `main.py` converts `AppException` to `{"success": false, "error": message}`.

---

## 8. Logging

```python
import logging
logger = logging.getLogger(__name__)
```

**Rules:**
- Every module declares its own logger with `__name__`.
- Do not call `setup_logging()` inside feature modules — it is called once in `src/main.py` at startup.
- Log levels:
  - `logger.info(...)` — routine operations (method entry, successful operations)
  - `logger.warning(...)` — expected-but-notable conditions (user not found, empty results)
  - `logger.error(...)` — exceptions, unexpected failures
  - `logger.debug(...)` — verbose diagnostic data (disabled in production by LOG_LEVEL)
- Never use `print()` in any module under `src/`.

---

## 9. MongoDB Collection Naming

- Use lowercase plural names: `users`, `deals`, `projects`, `accounts`.
- Collection name must match what the repository passes to `MongoDBConnection.get_collection(name)`.
- When a new collection is needed, add it to the collections index comment in `src/db/mongo_connection.py`.

---

## 10. Registering a New Feature

Checklist when adding a new feature (e.g., `deals`):

1. Create `src/schemas/deals.py` with request and response models.
2. Create `src/repository/deals.py` with `DealsRepository`.
3. Create `src/services/deals.py` with `DealsService`.
4. Create `src/api/deals.py` with `deals_router`.
5. Add `app.include_router(deals_router)` in `src/main.py`.
6. Create `tests/unit/test_deals_service.py` for service unit tests.
7. Create `tests/e2e/test_deals_api.py` for end-to-end API tests.

---

## 11. Testing Standards

Every feature must have both unit tests and end-to-end tests before it is considered complete.

**Unit tests** (`tests/unit/test_<feature>_service.py`):
- Test service methods in isolation.
- Mock the repository using `unittest.mock.MagicMock`.
- Cover: happy path, not-found, conflict/duplicate, validation errors.

**End-to-end tests** (`tests/e2e/test_<feature>_api.py`):
- Use `fastapi.testclient.TestClient` with a real (test) MongoDB database.
- Test the full stack from HTTP request to database and back.
- Cover: correct status codes, response body shape, error cases.

See `.claude/skills/api-skill.md` for the test templates.

---

## 12. What Not To Do

- Do not add try/except in router functions.
- Do not write business logic in repository methods.
- Do not query MongoDB directly in services.
- Do not use print statements anywhere under `src/`.
- Do not catch `AppException` and wrap it in another `AppException`.
- Do not expose `_id`, `password`, or any hashed/internal fields in response schemas.
- Do not create a new custom exception class — use `AppException` only.
- Do not skip `response_model` on router endpoints.
- Do not access `MongoDBConnection` outside of repository classes.
