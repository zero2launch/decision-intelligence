# Spec: POST /api/upload — File Upload and Content Extraction Endpoint

**ID:** `06-upload-api-file-conversion`
**Status:** Ready for implementation
**Depends on:** `04-login-api` (JWT token generation and `AuthUtils` must exist)

---

## 1. Context

The frontend upload page (`frontend/pages/upload.py`) already exists per spec `05-upload-page-ui`. It POSTs to `POST /api/upload` with a JSON body of `{"files": [...]}` where each file carries a Base64-encoded `content` string, a `filename`, and a `size`. It attaches `Authorization: Bearer <token>` from `sessionStorage` and navigates to `/chatbot` on any 2xx response.

The backend currently only has auth endpoints in `src/api/auth.py`. This spec adds the full upload feature — schema, repository, service, and router — following the mandatory layered architecture.

---

## 2. Endpoint Contract

### Request

```
POST /api/upload
Content-Type: application/json
Authorization: Bearer <jwt-token>
```

```json
{
  "files": [
    {
      "filename": "report.pdf",
      "content": "<base64-encoded-bytes>",
      "size": 45678
    },
    {
      "filename": "data.xlsx",
      "content": "<base64-encoded-bytes>",
      "size": 12345
    }
  ]
}
```

| Field              | Type   | Constraints                                          |
|--------------------|--------|------------------------------------------------------|
| `files`            | list   | required, min 1 item                                 |
| `files[].filename` | string | required, min length 1, max length 255               |
| `files[].content`  | string | required — Base64-encoded file bytes                 |
| `files[].size`     | int    | required, `>= 0` — raw byte count before encoding   |

### Success Response — `200 OK`

```json
{
  "success": true,
  "uploaded": 2
}
```

| Field      | Type | Description                              |
|------------|------|------------------------------------------|
| `success`  | bool | Always `true` on success                 |
| `uploaded` | int  | Number of files successfully processed   |

### Error Responses

| Scenario                         | Status | Body                                                              |
|----------------------------------|--------|-------------------------------------------------------------------|
| Missing or invalid token         | 401    | `{ "success": false, "error": "Invalid or expired token" }`      |
| Validation failure (bad input)   | 422    | FastAPI default (Pydantic validation error with `detail` list)    |
| Malformed Base64 content         | 400    | `{ "success": false, "error": "Invalid Base64 content in file <filename>" }` |
| Unsupported file extension       | 400    | `{ "success": false, "error": "Unsupported file type: <filename>. Accepted: pdf, csv, xls, xlsx" }` |
| Unexpected server error          | 500    | `{ "success": false, "error": "Internal server error" }`         |

---

## 3. Files to Create / Modify

```
src/
  schemas/upload.py        ← new: UploadedFile, UploadRequest, UploadResponse
  repository/upload.py     ← new: UploadRepository
  services/upload.py       ← new: UploadService
  api/upload.py            ← new: upload_router (POST /api/upload)
  utils/auth.py            ← modify: add decode_access_token() to AuthUtils
  main.py                  ← modify: include upload_router
tests/
  unit/
    test_upload_service.py ← new
  e2e/
    test_upload_api.py     ← new
```

---

## 4. Layer Specifications

### 4.1 `src/utils/auth.py` — Add `decode_access_token` to AuthUtils

Add the following static method to the existing `AuthUtils` class:

```python
@staticmethod
def decode_access_token(token: str) -> dict:
    secret = os.environ["JWT_SECRET"]
    algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
    from jose import JWTError, ExpiredSignatureError
    try:
        return jwt.decode(token, secret, algorithms=[algorithm])
    except ExpiredSignatureError:
        raise AppException("Invalid or expired token", status_code=401)
    except JWTError:
        raise AppException("Invalid or expired token", status_code=401)
```

Add the import `from src.utils.exception import AppException` at the top of `src/utils/auth.py`.

**Rules:**
- Both `ExpiredSignatureError` and the generic `JWTError` map to the same 401 message — never reveal which check failed.
- The returned `dict` contains the JWT claims (e.g., `{"sub": "alice", "exp": ...}`).

---

### 4.2 `src/schemas/upload.py` — Pydantic Models

```python
from pydantic import BaseModel, Field

class UploadedFile(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str   # Base64-encoded bytes
    size: int = Field(ge=0)

class UploadRequest(BaseModel):
    files: list[UploadedFile] = Field(min_length=1)

class UploadResponse(BaseModel):
    success: bool
    uploaded: int
```

**Rules:**
- `content` carries no `Field` constraints beyond being a non-empty string — Base64 validity is checked at the service layer, not by Pydantic.
- `UploadRequest.files` must have at least one element (`min_length=1`) — an empty list is a bad request caught at the Pydantic layer (422).
- Never expose internal storage fields (`_id`, `username`, timestamps) in the response.

---

### 4.3 `src/repository/upload.py` — UploadRepository

```python
from src.db.mongo_connection import MongoDBConnection
import logging

logger = logging.getLogger(__name__)

class UploadRepository:

    @property
    def _collection(self):
        return MongoDBConnection.get_collection("documents")

    def insert_document(self, document: dict) -> str:
        logger.info(f"Inserting document: {document.get('filename')}")
        result = self._collection.insert_one(document)
        return str(result.inserted_id)
```

**Stored document shape:**

```json
{
  "_id": "ObjectId",
  "username": "alice",
  "filename": "report.pdf",
  "content_type": "pdf",
  "extracted_text": "...",
  "size": 45678,
  "uploaded_at": "2026-06-29T12:00:00Z"
}
```

| Field            | Type     | Description                                                    |
|------------------|----------|----------------------------------------------------------------|
| `username`       | str      | Decoded from JWT `sub` claim                                   |
| `filename`       | str      | Original filename from the request                             |
| `content_type`   | str      | Lowercase extension: `"pdf"`, `"csv"`, `"xls"`, or `"xlsx"`   |
| `extracted_text` | str      | For PDF: full extracted text. For CSV/XLS/XLSX: JSON-serialised list of row dicts |
| `size`           | int      | Raw byte count from the request                                |
| `uploaded_at`    | datetime | UTC timestamp at time of insert                                |

**Rules:**
- The repository only calls pymongo; no parsing or business logic.
- Raises pymongo exceptions unmodified; the service converts them to `AppException`.
- `@property _collection` ensures the connection is already initialised before access.

---

### 4.4 `src/services/upload.py` — UploadService

**Class:** `UploadService`

```python
from src.repository.upload import UploadRepository
from src.utils.exception import AppException
import logging, base64, io, json, csv
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class UploadService:
    def __init__(self):
        self._repo = UploadRepository()

    def process_upload(self, payload: UploadRequest, username: str) -> UploadResponse:
        ...
```

**`process_upload` logic (step-by-step):**

1. Initialise `uploaded_count = 0`.
2. Iterate over `payload.files` one at a time:
   a. Determine `content_type` from `file.filename.rsplit('.', 1)[-1].lower()`.
   b. If `content_type` not in `{"pdf", "csv", "xls", "xlsx"}`, raise `AppException("Unsupported file type: <filename>. Accepted: pdf, csv, xls, xlsx", status_code=400)`.
   c. Decode Base64: `binary_data = base64.b64decode(file.content)`. Wrap in a try/except for `Exception` to catch malformed Base64 — re-raise as `AppException("Invalid Base64 content in file <filename>", status_code=400)`.
   d. Call the appropriate private extraction method (see below).
   e. Build the document dict and call `self._repo.insert_document(document)`. Wrap pymongo errors in a try/except and re-raise as `AppException("Internal server error", status_code=500)`.
   f. Increment `uploaded_count`.
3. Return `UploadResponse(success=True, uploaded=uploaded_count)`.

**Private extraction methods:**

```python
def _extract_pdf(self, binary_data: bytes) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(stream=binary_data, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)

def _extract_csv(self, binary_data: bytes) -> str:
    text = binary_data.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = [row for row in reader]
    return json.dumps(rows, ensure_ascii=False)

def _extract_xls(self, binary_data: bytes) -> str:
    import xlrd
    workbook = xlrd.open_workbook(file_contents=binary_data)
    rows = []
    for sheet in workbook.sheets():
        headers = [sheet.cell_value(0, col) for col in range(sheet.ncols)]
        for row_idx in range(1, sheet.nrows):
            rows.append({headers[col]: sheet.cell_value(row_idx, col) for col in range(sheet.ncols)})
    return json.dumps(rows, ensure_ascii=False)

def _extract_xlsx(self, binary_data: bytes) -> str:
    import openpyxl
    workbook = openpyxl.load_workbook(io.BytesIO(binary_data), data_only=True)
    rows = []
    for sheet in workbook.worksheets:
        headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
        for row in sheet.iter_rows(min_row=2, values_only=True):
            rows.append({headers[col]: row[col] for col in range(len(headers))})
    return json.dumps(rows, ensure_ascii=False)
```

**Extraction method dispatch:**

| `content_type` | Method         | Library  |
|----------------|----------------|----------|
| `"pdf"`        | `_extract_pdf` | PyMuPDF  |
| `"csv"`        | `_extract_csv` | stdlib   |
| `"xls"`        | `_extract_xls` | xlrd     |
| `"xlsx"`       | `_extract_xlsx`| openpyxl |

**Rules:**
- Files are processed sequentially — one at a time, not concurrently.
- `AppException` raised for any individual file terminates the entire request; no partial-success writes.
- Catch only low-level exceptions (Base64 decode errors, pymongo errors, parser errors) and re-raise as `AppException`. Never catch `AppException` itself.
- No `print()`. Use `logger.info()`, `logger.warning()`, `logger.error()`.

---

### 4.5 `src/api/upload.py` — upload_router

```python
from fastapi import APIRouter, Header
from src.schemas.upload import UploadRequest, UploadResponse
from src.services.upload import UploadService
from src.utils.auth import AuthUtils
from src.utils.exception import AppException
import logging

upload_router = APIRouter(prefix="/api", tags=["Upload"])
logger = logging.getLogger(__name__)

_service = UploadService()

def _get_current_user(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise AppException("Invalid or expired token", status_code=401)
    token = authorization.removeprefix("Bearer ")
    claims = AuthUtils.decode_access_token(token)
    username = claims.get("sub")
    if not username:
        raise AppException("Invalid or expired token", status_code=401)
    return username

@upload_router.post("/upload", response_model=UploadResponse, status_code=200)
async def upload_files(payload: UploadRequest, authorization: str = Header(default="")):
    username = _get_current_user(authorization)
    return _service.process_upload(payload, username)
```

**Rules:**
- `_get_current_user` is a plain function (not a FastAPI `Depends`) — called directly in the route body to keep the router simple and consistent with the rest of the codebase.
- No try/except in the router — `AppException` is caught globally by the handler registered in `main.py`.
- `response_model` is mandatory.
- Route function must be `async`.
- No `print()`.

---

### 4.6 `src/main.py` — Register upload_router

Add the following import and `include_router` call:

```python
from src.api.upload import upload_router
# ...
app.include_router(upload_router)
```

Place the import after the existing `from src.api.auth import auth_router` line and the `include_router` call after `app.include_router(auth_router)`.

---

## 5. File Parsing Details

### PDF — PyMuPDF (`fitz`)

```python
import fitz
doc = fitz.open(stream=binary_data, filetype="pdf")
text = "\n".join(page.get_text() for page in doc)
```

- Opens the PDF from bytes without writing to disk.
- Iterates all pages and concatenates extracted text with newlines.
- `get_text()` with no arguments returns plain text (not HTML or dict).

### CSV — stdlib `csv`

```python
import csv, io, json
reader = csv.DictReader(io.StringIO(binary_data.decode("utf-8", errors="replace")))
rows = list(reader)
extracted_text = json.dumps(rows, ensure_ascii=False)
```

- Decodes bytes as UTF-8; replaces undecodable bytes instead of raising.
- Uses `DictReader` so each row is a `{header: value}` dict.
- Serialises the list of row dicts to a JSON string for uniform storage.

### XLS — `xlrd`

```python
import xlrd, json
workbook = xlrd.open_workbook(file_contents=binary_data)
rows = []
for sheet in workbook.sheets():
    headers = [sheet.cell_value(0, col) for col in range(sheet.ncols)]
    for row_idx in range(1, sheet.nrows):
        rows.append({headers[col]: sheet.cell_value(row_idx, col) for col in range(sheet.ncols)})
extracted_text = json.dumps(rows, ensure_ascii=False)
```

- Processes all sheets in the workbook.
- Assumes row 0 is the header row; data starts at row 1.
- Serialises all rows across all sheets into a single JSON list.
- `xlrd >= 2.0` supports `.xls` only — do not pass `.xlsx` files to this method.

### XLSX — `openpyxl`

```python
import openpyxl, io, json
workbook = openpyxl.load_workbook(io.BytesIO(binary_data), data_only=True)
rows = []
for sheet in workbook.worksheets:
    headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
    for row in sheet.iter_rows(min_row=2, values_only=True):
        rows.append({headers[col]: row[col] for col in range(len(headers))})
extracted_text = json.dumps(rows, ensure_ascii=False)
```

- `data_only=True` reads cell values, not formulas.
- Processes all worksheets.
- Assumes row 1 is the header row; data starts at row 2.

---

## 6. Authentication Flow

```
Request arrives with: Authorization: Bearer <jwt>
    ↓
_get_current_user() strips "Bearer " prefix
    ↓
AuthUtils.decode_access_token(token) → claims dict   [raises AppException(401) on bad/expired token]
    ↓
claims["sub"] → username string                       [raises AppException(401) if sub is missing]
    ↓
username passed to UploadService.process_upload()
    ↓
username stored in each document inserted to MongoDB
```

**Rules:**
- A request with no `Authorization` header, a non-Bearer scheme, an expired token, or a tampered token all return `401` with the same message: `"Invalid or expired token"`.
- The `username` extracted from the token is trusted; no second database lookup is needed to validate the user still exists.

---

## 7. Dependencies to Add

```bash
uv add pymupdf xlrd openpyxl
```

| Package    | Version constraint | Purpose                         |
|------------|--------------------|---------------------------------|
| `pymupdf`  | `>=1.23`           | PDF text extraction via `fitz`  |
| `xlrd`     | `>=2.0`            | `.xls` file parsing             |
| `openpyxl` | `>=3.1`            | `.xlsx` file parsing            |

> `csv`, `io`, `base64`, `json`, and `datetime` are Python standard library modules — no installation needed.

---

## 8. MongoDB Collection

- **Collection name:** `documents`
- **Index:** Compound index on `(username, uploaded_at)` (descending `uploaded_at`) to support future "list my documents" queries efficiently.
- Add the index creation to `src/main.py` alongside the existing `users` index:

```python
MongoDBConnection.get_collection("documents").create_index(
    [("username", ASCENDING), ("uploaded_at", DESCENDING)]
)
```

---

## 9. Test Plan

### Unit Tests — `tests/unit/test_upload_service.py`

Mock `UploadRepository` with `unittest.mock.MagicMock`. Use real Base64-encoded minimal fixtures for each file type.

| Test case                     | Setup                                                                                 | Expected                                                    |
|-------------------------------|---------------------------------------------------------------------------------------|-------------------------------------------------------------|
| Successful PDF upload         | Valid Base64 of a minimal PDF; `insert_document` returns a fake id                   | Returns `UploadResponse(success=True, uploaded=1)`          |
| Successful CSV upload         | Valid Base64 of `"col1,col2\na,b\n"`; `insert_document` returns a fake id            | Returns `UploadResponse(success=True, uploaded=1)`          |
| Successful XLSX upload        | Valid Base64 of a minimal XLSX; `insert_document` returns a fake id                  | Returns `UploadResponse(success=True, uploaded=1)`          |
| Successful XLS upload         | Valid Base64 of a minimal XLS; `insert_document` returns a fake id                   | Returns `UploadResponse(success=True, uploaded=1)`          |
| Multiple files                | Two valid files; both inserts succeed                                                 | Returns `UploadResponse(success=True, uploaded=2)`          |
| Unsupported file type         | `filename="doc.txt"`, valid Base64                                                    | Raises `AppException` with `status_code=400`                |
| Malformed Base64              | `content="not-valid-base64!!!"`                                                       | Raises `AppException` with `status_code=400`                |
| DB error on insert            | Valid file; `insert_document` raises `pymongo.errors.PyMongoError`                   | Raises `AppException` with `status_code=500`                |

> For PDF tests, create a minimal valid PDF binary in a `conftest.py` fixture using `fitz.open()` and save as a real bytes object. Do not mock the extraction methods — test the real parsers.

### End-to-End Tests — `tests/e2e/test_upload_api.py`

Use `fastapi.testclient.TestClient` with a real (test) MongoDB database. Use a fixture that creates a test user via `POST /api/signup` and obtains a JWT before running upload tests. Drop the `documents` collection in teardown.

| Test case                    | Request                                                                                 | Expected status | Expected body                                                              |
|------------------------------|-----------------------------------------------------------------------------------------|-----------------|----------------------------------------------------------------------------|
| Valid PDF upload              | 1 PDF file in `files`, valid JWT                                                        | `200`           | `{ "success": true, "uploaded": 1 }`                                      |
| Valid CSV upload              | 1 CSV file in `files`, valid JWT                                                        | `200`           | `{ "success": true, "uploaded": 1 }`                                      |
| Valid XLSX upload             | 1 XLSX file in `files`, valid JWT                                                       | `200`           | `{ "success": true, "uploaded": 1 }`                                      |
| Multiple mixed files          | PDF + CSV in `files`, valid JWT                                                         | `200`           | `{ "success": true, "uploaded": 2 }`                                      |
| Missing Authorization header | Valid body, no `Authorization` header                                                   | `401`           | `{ "success": false, "error": "Invalid or expired token" }`               |
| Invalid token                 | Valid body, `Authorization: Bearer bad-token`                                           | `401`           | `{ "success": false, "error": "Invalid or expired token" }`               |
| Empty files list              | `{ "files": [] }`, valid JWT                                                            | `422`           | FastAPI validation error (min_length=1 violated)                           |
| Unsupported file type         | `filename="notes.txt"`, valid Base64, valid JWT                                         | `400`           | `{ "success": false, "error": "Unsupported file type: notes.txt. ..." }`  |
| Malformed Base64              | `content="!!!"`, valid JWT                                                              | `400`           | `{ "success": false, "error": "Invalid Base64 content in file ..." }`     |

---

## 10. Out of Scope

- Querying or listing previously uploaded documents (separate user story).
- The `/chatbot` page or any downstream consumption of the extracted text.
- Client-side or server-side file size limits (413 handling) — the frontend already surfaces a 413 message; the backend does not set `Content-Length` limits in this story.
- Image extraction from PDFs (only text via `get_text()`).
- Password-protected PDF or Excel files.
- Multi-sheet CSV (CSV has no native multi-sheet concept; only one "sheet" per file is expected).
- Virus/malware scanning of uploaded content.
- Authentication guard changes to any other endpoint.
