# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Decision Intelligence is a full-stack application with:
- **Backend**: FastAPI REST API (`src/`) serving on port 8000
- **Frontend**: NiceGUI web app (`frontend/`) serving on port 8080
- **Database**: MongoDB (singleton connection pattern)
- **Auth**: bcrypt password hashing + JWT tokens via `python-jose`

## Running the Application

Both services must be started separately.

**Backend:**
```bash
python -m src.main
```

**Frontend** (from the `frontend/` directory):
```bash
cd frontend && python main.py
```

**Environment variables** (`.env` in project root):
```
MONGO_URI=mongodb://localhost:27017
DATABASE_NAME=decision_intelligence_db
JWT_SECRET=<your-secret>
JWT_EXPIRES_IN=3600
JWT_ALGORITHM=HS256
API_URL=http://localhost:8000
```

## Architecture

### Backend Layer Structure (`src/`)

The backend follows a strict layered architecture — requests flow through:

```
api/ → services/ → repository/ → db/
```

- **`api/`** — FastAPI routers. Each router file instantiates its service directly. Catches exceptions and wraps them as `AppException`.
- **`services/`** — Business logic. Orchestrates repository calls and utility functions.
- **`repository/`** — MongoDB query layer. Accesses collections via `MongoDBConnection.get_collection(name)`.
- **`db/mongo_connection.py`** — `MongoDBConnection` singleton class. Must be initialized via `MongoDBConnection.connect(uri, database_name)` before any repository is used. The `src/main.py` entrypoint calls this on startup.
- **`schemas/`** — Pydantic request/response models with validation.
- **`utils/auth.py`** — `AuthUtils` class for bcrypt hashing and JWT encode/decode. Reads `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRES_IN` from env.
- **`utils/exception.py`** — `AppException(message, status_code)` is the single custom exception type. Registered as a global handler in `main.py`.
- **`logging/logger.py`** — `setup_logging()` configures root logger once (idempotent). Logs to console and to a rotating file at `logs/app.log`. Call it before any `logging.getLogger()` use.

### Frontend (`frontend/`)

Built with NiceGUI. Pages are registered by importing the page modules in `frontend/main.py`. Each page module uses `@ui.page("/route")` decorators. The frontend calls the backend API via `requests` (not async).

### Key Invariants

- `MongoDBConnection` is a singleton — `get_collection()` raises `AppException` if called before `connect()`.
- `setup_logging()` is idempotent — safe to call multiple times (guards on `root.handlers`), but should be called once at app startup before other imports log.
- The canonical password-check method is `AuthUtils.validate_hash_password(plain, hashed)` — do not rename or alias it.
- All imports inside `src/` use the full `src.` prefix (e.g., `from src.utils.exception import AppException`).

## Dependencies

Managed via `pyproject.toml` with `uv`. Python 3.12 required.

```bash
uv sync        # install dependencies
uv add <pkg>   # add a new dependency
```
