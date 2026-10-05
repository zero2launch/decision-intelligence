# Spec: CSV / XLS / XLSX Row-Based Chunking Pipeline

**ID:** `08-csv-chunking`
**Status:** Ready for implementation
**Depends on:** `06-upload-api-file-conversion` (`_extract_csv()`, `_extract_xls()`, `_extract_xlsx()` must exist in `UploadService`; `ChromaConnection` must be initialized at startup), `07-pdf-chunking` (`ChunkingService` class and `ChromaConnection` singleton must exist)

---

## 1. Context

`UploadService.process_upload()` already extracts row data from CSV, XLS, and XLSX files via `_extract_csv()`, `_extract_xls()`, and `_extract_xlsx()`. Each extraction method returns `json.dumps(rows)` — a JSON string of `list[dict]` where every dict maps column headers to cell values.

Currently, no chunking pipeline runs for tabular files. This spec adds a row-based chunking pipeline triggered for every CSV, XLS, and XLSX upload. The pipeline groups every 10 rows into a single chunk, formats each chunk as human-readable key-value text, generates an OpenAI embedding per chunk, and stores the chunk with its embedding in the existing in-memory ChromaDB collection.

No new HTTP endpoint is introduced. The pipeline runs inside the existing `POST /api/upload` request, invoked from `UploadService` immediately after tabular text extraction.

---

## 2. Pipeline Overview

```
UploadService.process_upload()  [existing, extended for CSV/XLS/XLSX]
    │
    ├─ _extract_csv(binary_data)   → rows_json   [existing]
    ├─ _extract_xls(binary_data)   → rows_json   [existing]
    ├─ _extract_xlsx(binary_data)  → rows_json   [existing]
    │
    └─ _chunking_svc.chunk_and_store_tabular(rows_json, filename, username)  [NEW]
            │
            ├─ 1. Parse rows_json → list[dict]
            │
            ├─ 2. Group rows in batches of 10 (last batch may be < 10)
            │
            ├─ 3. For each batch:
            │       a. Format each row as "key: value | key: value ..." text
            │       b. Concatenate row texts with newlines → chunk_text
            │       c. Generate OpenAI embedding for chunk_text
            │       d. Add chunk + embedding to ChromaDB in-memory collection
            │          with metadata: { filename, username, chunk_index, row_start, row_end }
            │
            └─ 4. Return total chunk count (logged; not surfaced in HTTP response)
```

The HTTP response remains `UploadResponse(success=True, uploaded=<n>)` — unchanged.

---

## 3. Files to Create / Modify

```
src/
  services/
    chunking.py   ← modify: add chunk_and_store_tabular() and _format_row_as_text()
    upload.py     ← modify: call chunk_and_store_tabular() for CSV/XLS/XLSX branches
```

No new files are required. All infrastructure (`ChromaConnection`, `ChunkingService`, `AppException`) already exists from spec `07`.

---

## 4. Dependencies

No new packages required. The pipeline reuses:

| Package    | Already added in | Purpose                              |
|------------|------------------|--------------------------------------|
| `chromadb` | spec `07`        | In-memory vector store for chunks    |
| `openai`   | spec `07`        | OpenAI SDK for embedding generation  |

`json` and `uuid` are Python standard library — no install needed.

---

## 5. Environment Variables

No new variables. `OPENAI_API_KEY` is already read by `ChunkingService.__init__()` (established in spec `07`). Ensure it is present in `.env`.

---

## 6. Layer Specifications

### 6.1 `src/services/chunking.py` — Extend ChunkingService

Add two methods to the existing `ChunkingService` class. Do not modify any existing method.

---

#### 6.1.1 `_format_row_as_text(row: dict) -> str`

Converts a single row dict into a human-readable key-value string.

```python
def _format_row_as_text(self, row: dict) -> str:
    return " | ".join(f"{key}: {value}" for key, value in row.items() if value is not None)
```

**Rules:**
- Fields with `None` values are omitted (common in XLS/XLSX sparse rows).
- Separator between key-value pairs is ` | ` — readable in plain text and as a ChromaDB document.
- Do not JSON-encode the output — the result must be a plain readable string, not escaped JSON.
- Empty strings are kept as-is (e.g., `"Name: "`) — they represent present-but-blank cells.
- The format for a row `{"Name": "Alice", "Score": 92, "Notes": None}` is: `"Name: Alice | Score: 92"`.

---

#### 6.1.2 `chunk_and_store_tabular(rows_json: str, filename: str, username: str) -> int`

Orchestrates the full tabular chunking pipeline.

```python
import json
import uuid

def chunk_and_store_tabular(self, rows_json: str, filename: str, username: str) -> int:
    rows: list[dict] = json.loads(rows_json)
    if not rows:
        logger.warning(f"No rows found in '{filename}' — skipping tabular chunking")
        return 0

    chroma_collection = ChromaConnection.get_collection()
    chunk_size = 10
    total_chunks = 0

    for chunk_index in range(0, len(rows), chunk_size):
        batch = rows[chunk_index : chunk_index + chunk_size]
        row_start = chunk_index
        row_end = chunk_index + len(batch) - 1

        chunk_text = "\n".join(self._format_row_as_text(row) for row in batch)

        try:
            embedding = self._generate_embedding(chunk_text)
        except Exception as e:
            logger.error(
                f"OpenAI embedding error for chunk {chunk_index // chunk_size} "
                f"of '{filename}': {e}"
            )
            raise AppException("Internal server error", status_code=500)

        chunk_id = str(uuid.uuid4())

        try:
            chroma_collection.add(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk_text],
                metadatas=[{
                    "filename": filename,
                    "username": username,
                    "chunk_index": chunk_index // chunk_size,
                    "row_start": row_start,
                    "row_end": row_end,
                }],
            )
        except Exception as e:
            logger.error(
                f"ChromaDB add error for chunk {chunk_index // chunk_size} "
                f"of '{filename}': {e}"
            )
            raise AppException("Internal server error", status_code=500)

        total_chunks += 1

    logger.info(
        f"chunk_and_store_tabular complete for '{filename}': "
        f"{total_chunks} chunks stored ({len(rows)} rows total)"
    )
    return total_chunks
```

**Rules:**
- Empty file (zero rows after parsing) logs a warning and returns `0` — it is not an error.
- `chunk_size = 10` is a local constant, not a module-level constant, because it is specific to tabular chunking (unlike `PARENT_TOKEN_LIMIT`/`CHILD_TOKEN_LIMIT` which are module-level for the PDF pipeline).
- Each chunk is assigned a `uuid.uuid4()` string ID to guarantee uniqueness across multiple uploads of the same file. Do not use `"{filename}_{chunk_index}"` — ChromaDB's `add` raises `DuplicateIDError` on re-upload.
- `row_start` and `row_end` are zero-based, inclusive indices into the original row list. They are stored in metadata to support future retrieval mapping.
- The last batch may contain fewer than 10 rows — this is correct and expected.
- `AppException` is never caught inside this method — only low-level exceptions (openai, chromadb) are caught and re-raised.
- Do not log `chunk_text` at INFO level — it may contain sensitive data.
- Reuses `self._generate_embedding()` defined in spec `07` — do not duplicate it.
- No MongoDB storage is performed — this pipeline stores only in ChromaDB per the user story.

---

### 6.2 `src/services/upload.py` — Extend UploadService for Tabular Files

Modify `process_upload` to call `chunk_and_store_tabular` after tabular extraction.

**Current code (lines 51–53):**

```python
if content_type == "pdf":
    self._chunking_svc.chunk_and_store(extracted_text, file.filename, username)
```

**Updated code:**

```python
if content_type == "pdf":
    self._chunking_svc.chunk_and_store(extracted_text, file.filename, username)
elif content_type in {"csv", "xls", "xlsx"}:
    self._chunking_svc.chunk_and_store_tabular(extracted_text, file.filename, username)
```

**Rules:**
- `chunk_and_store_tabular` propagates `AppException` directly — `process_upload` does not catch it.
- `UploadService` does not use the return value of `chunk_and_store_tabular`.
- No other changes to `UploadService` are needed — `_chunking_svc` is already instantiated in `__init__`.
- The extraction methods (`_extract_csv`, `_extract_xls`, `_extract_xlsx`) remain unchanged — they already return a `json.dumps(rows)` string that `chunk_and_store_tabular` can parse directly.

---

## 7. ChromaDB Document Shape

Each tabular chunk is stored in the same `child_chunks` ChromaDB collection already used by the PDF pipeline.

| ChromaDB field | Value |
|----------------|-------|
| `id`           | `str(uuid.uuid4())` — unique per chunk per upload |
| `embedding`    | `list[float]` — 1536-dimensional vector from `text-embedding-3-small` |
| `document`     | Human-readable key-value text for the 10-row batch |
| `metadata`     | `{ "filename": str, "username": str, "chunk_index": int, "row_start": int, "row_end": int }` |

**Metadata field descriptions:**

| Field         | Type | Description                                                  |
|---------------|------|--------------------------------------------------------------|
| `filename`    | str  | Original CSV/XLS/XLSX filename from the upload request       |
| `username`    | str  | JWT `sub` claim — owner of the upload                        |
| `chunk_index` | int  | Zero-based chunk number (chunk 0 = rows 0–9, chunk 1 = rows 10–19, etc.) |
| `row_start`   | int  | Zero-based index of first row in this chunk                  |
| `row_end`     | int  | Zero-based index of last row in this chunk (inclusive)       |

---

## 8. Row Formatting Reference

Given a CSV with columns `["Product", "Revenue", "Region"]`, a 3-row batch:

| Row | Raw dict | Formatted text |
|-----|----------|----------------|
| 0   | `{"Product": "Widget A", "Revenue": 5000, "Region": "North"}` | `Product: Widget A \| Revenue: 5000 \| Region: North` |
| 1   | `{"Product": "Widget B", "Revenue": 3200, "Region": "South"}` | `Product: Widget B \| Revenue: 3200 \| Region: South` |
| 2   | `{"Product": "Widget C", "Revenue": None, "Region": "East"}`  | `Product: Widget C \| Region: East` |

The full chunk text stored in ChromaDB for the above batch:

```
Product: Widget A | Revenue: 5000 | Region: North
Product: Widget B | Revenue: 3200 | Region: South
Product: Widget C | Region: East
```

---

## 9. Capacity Reference

For a typical CSV file:

| File size | Rows | Chunks (10 rows/chunk) | OpenAI API calls |
|-----------|------|------------------------|-----------------|
| Small     | 50   | 5                      | 5               |
| Medium    | 500  | 50                     | 50              |
| Large     | 5000 | 500                    | 500             |

Each embedding call uses `text-embedding-3-small` (1536 dimensions, ~1000 tokens per 10-row chunk for typical business data).

---

## 10. Test Plan

### Unit Tests — `tests/unit/test_chunking_service.py`

Add the following test cases to the existing test file. Mock `ChromaConnection.get_collection()` and the OpenAI client.

```python
@pytest.fixture()
def service():
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        svc = ChunkingService.__new__(ChunkingService)
        svc._repo = MagicMock()
        svc._openai_api_key = "test-key"
        return svc
```

| Test case | Setup | Expected |
|-----------|-------|----------|
| `_format_row_as_text` normal row | `{"Name": "Alice", "Age": 30}` | Returns `"Name: Alice \| Age: 30"` |
| `_format_row_as_text` omits None | `{"Name": "Alice", "Score": None}` | Returns `"Name: Alice"` |
| `_format_row_as_text` empty dict | `{}` | Returns `""` |
| `chunk_and_store_tabular` happy path | 25 rows; each embedding returns 1536-dim vector; ChromaDB add succeeds | Returns `3`; ChromaDB `add` called 3 times (chunks of 10, 10, 5) |
| `chunk_and_store_tabular` exact multiple | 20 rows | Returns `2`; `add` called 2 times |
| `chunk_and_store_tabular` empty rows | `rows_json = "[]"` | Returns `0`; no embedding calls; no ChromaDB calls |
| `chunk_and_store_tabular` single row | 1 row | Returns `1`; `add` called once with `row_start=0, row_end=0` |
| `chunk_and_store_tabular` metadata shape | 15 rows | Second chunk has `chunk_index=1`, `row_start=10`, `row_end=14` |
| `chunk_and_store_tabular` OpenAI error | Embedding raises `Exception("timeout")` | Raises `AppException(status_code=500)` |
| `chunk_and_store_tabular` ChromaDB error | `chroma_collection.add` raises `Exception` | Raises `AppException(status_code=500)` |
| `chunk_and_store_tabular` UUID IDs | 2 chunks generated | Both `ids` passed to ChromaDB `add` are valid UUID4 strings and differ from each other |

**Patching guidance:**
- Patch `src.services.chunking.ChromaConnection` to return a `MagicMock` collection.
- Patch `src.services.chunking.uuid` if asserting on specific ID values; otherwise just assert they are valid UUIDs with `uuid.UUID(id_value)`.
- Do not mock `_format_row_as_text` — test the real method in `chunk_and_store_tabular` tests.

---

## 11. Error Handling Summary

| Failure point               | Exception source              | Caught by                   | Re-raised as                              |
|-----------------------------|-------------------------------|-----------------------------|-------------------------------------------|
| `rows_json` not valid JSON  | `json.loads`                  | Not caught — propagates up  | Unhandled `json.JSONDecodeError` → 500 via global handler (input always comes from our own `_extract_*` methods so this should never happen) |
| Empty rows list             | (no exception)                | —                           | Returns `0`; no error                     |
| OpenAI API failure          | `Exception` (openai SDK)      | `chunk_and_store_tabular`   | `AppException("Internal server error", 500)` |
| ChromaDB `add` failure      | `Exception` (chromadb)        | `chunk_and_store_tabular`   | `AppException("Internal server error", 500)` |
| `ChromaConnection` not init | `AppException(500)` from `get_collection()` | Propagates through `chunk_and_store_tabular` unmodified | `AppException(500)` |

---

## 12. Distinction from PDF Pipeline

| Aspect              | PDF (spec `07`)                         | CSV/XLS/XLSX (this spec)                  |
|---------------------|-----------------------------------------|-------------------------------------------|
| Chunking strategy   | Token-based (~500 tokens / ~100 tokens) | Row-based (every 10 rows)                 |
| Hierarchy           | Parent → Child (2-level)                | Flat (single level)                       |
| MongoDB storage     | Yes (`parent_chunks` collection)        | No                                        |
| ChromaDB storage    | Child chunks with parent reference      | Each 10-row chunk directly                |
| Chunk ID            | `"{parent_mongo_id}_{child_index}"`     | `str(uuid.uuid4())`                       |
| Input format        | Plain extracted text                    | JSON string of `list[dict]`               |
| Entry method        | `chunk_and_store(text, ...)`            | `chunk_and_store_tabular(rows_json, ...)` |

---

## 13. Out of Scope

- Querying or searching the stored chunks (future RAG story).
- Persisting ChromaDB to disk — in-memory only per the user story.
- Overlap between row chunks — not specified in the user story.
- Deduplication on re-upload — UUIDs make each upload independent.
- Storing tabular data in MongoDB — the user story only requires ChromaDB.
- Multi-sheet XLSX files producing independent chunks per sheet — rows from all sheets are already flattened by `_extract_xlsx()` before this pipeline receives them.
- Configurable rows-per-chunk — 10 is fixed per the user story.
- Async embedding generation.
