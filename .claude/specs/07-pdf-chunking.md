# Spec: PDF Parent-Child Chunking Pipeline

**ID:** `07-pdf-chunking`
**Status:** Ready for implementation
**Depends on:** `06-upload-api-file-conversion` (`_extract_pdf()` must exist in `UploadService`; `UploadRepository` and `MongoDBConnection` must be operational)

---

## 1. Context

`UploadService.process_upload()` already extracts full text from PDF files via `_extract_pdf()` and stores the raw document in the `documents` MongoDB collection. This spec adds a post-extraction chunking pipeline triggered automatically for every PDF upload.

The pipeline splits the extracted text into parent chunks (~500 tokens each), persists each parent chunk in MongoDB, then splits each parent into child chunks (~100 tokens each), generates an OpenAI embedding for every child, and stores the child with its embedding and parent reference into an in-memory ChromaDB collection.

No new HTTP endpoint is introduced. The pipeline runs inside the existing `POST /api/upload` request, invoked from `UploadService` immediately after PDF text extraction.

---

## 2. Pipeline Overview

```
UploadService.process_upload()  [existing, extended for PDF]
    │
    ├─ _extract_pdf(binary_data) → extracted_text      [existing]
    ├─ _repo.insert_document(document)                 [existing — full doc still stored]
    │
    └─ _chunking_svc.chunk_and_store(extracted_text, filename, username)   [NEW]
            │
            ├─ 1. Tokenise text and split into parent chunks (~500 tokens)
            │
            ├─ 2. For each parent chunk:
            │       a. Insert into MongoDB `parent_chunks` collection → parent_id
            │       b. Split parent into child chunks (~100 tokens)
            │       c. For each child chunk:
            │               i.  Generate OpenAI embedding
            │               ii. Add to ChromaDB in-memory collection
            │                   with metadata: { parent_id, filename, username, child_index }
            │
            └─ 3. Return total child count (logged; not surfaced in HTTP response)
```

The HTTP response remains `UploadResponse(success=True, uploaded=<n>)` — unchanged from spec `06`.

---

## 3. Files to Create / Modify

```
src/
  db/
    chroma_connection.py      ← new: ChromaConnection singleton (in-memory ChromaDB)
  repository/
    chunks.py                 ← new: ChunkRepository (MongoDB parent_chunks collection)
  schemas/
    chunks.py                 ← new: ParentChunkDocument (internal data shape, not HTTP)
  services/
    chunking.py               ← new: ChunkingService (orchestrates the full pipeline)
    upload.py                 ← modify: instantiate ChunkingService; call it for PDFs
  main.py                     ← modify: call ChromaConnection.initialize() at startup

tests/
  unit/
    test_chunking_service.py  ← new: unit tests for ChunkingService
```

---

## 4. Dependencies to Add

```bash
uv add chromadb openai tiktoken
```

| Package    | Purpose                                              |
|------------|------------------------------------------------------|
| `chromadb` | In-memory vector store for child chunks              |
| `openai`   | OpenAI Python SDK — used for embedding generation    |
| `tiktoken` | Token counting to produce accurate ~500/~100 splits  |

---

## 5. Environment Variables

Add `OPENAI_API_KEY` to the `.env` file alongside the existing variables:

```
OPENAI_API_KEY=sk-...
```

`ChunkingService` reads this key via `os.environ["OPENAI_API_KEY"]`. The key must be present at startup; a missing key raises `KeyError` immediately when `ChunkingService` is instantiated (via `UploadService.__init__`), which will surface as a 500 during the first upload request. Do not add a fallback default — an unconfigured key should fail loudly.

---

## 6. Layer Specifications

### 6.1 `src/db/chroma_connection.py` — ChromaDB Singleton

```python
import logging

from src.utils.exception import AppException

logger = logging.getLogger(__name__)


class ChromaConnection:
    _client = None
    _collection = None

    @classmethod
    def initialize(cls, collection_name: str = "child_chunks") -> None:
        if cls._client is not None:
            return
        import chromadb
        cls._client = chromadb.Client()
        cls._collection = cls._client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"ChromaDB in-memory collection '{collection_name}' initialized")

    @classmethod
    def get_collection(cls):
        if cls._collection is None:
            raise AppException("ChromaDB not initialized. Call initialize() first.", status_code=500)
        return cls._collection
```

**Rules:**
- `initialize()` is idempotent — safe to call multiple times (guards on `_client`).
- `chromadb.Client()` creates a purely in-memory (ephemeral) client. Data is lost on process restart — this is intentional per the user story.
- `hnsw:space: "cosine"` aligns with how OpenAI embeddings are typically compared.
- Never call `get_collection()` before `initialize()` — it will raise `AppException(500)`.

---

### 6.2 `src/schemas/chunks.py` — Internal Data Shape

This module defines only internal data containers used by the service and repository layers. No HTTP request/response models are needed.

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ParentChunkDocument:
    filename: str
    username: str
    chunk_index: int
    text: str
    token_count: int
    created_at: datetime

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "username": self.username,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "token_count": self.token_count,
            "created_at": self.created_at,
        }
```

**Rules:**
- `dataclass` is used, not Pydantic, because this shape is never serialised over HTTP — it exists only for internal service-to-repository communication.
- `to_dict()` produces the MongoDB document dict (without `_id`; that is assigned by MongoDB on insert).

---

### 6.3 `src/repository/chunks.py` — ChunkRepository

```python
import logging

from src.db.mongo_connection import MongoDBConnection

logger = logging.getLogger(__name__)


class ChunkRepository:

    @property
    def _collection(self):
        return MongoDBConnection.get_collection("parent_chunks")

    def insert_parent_chunk(self, document: dict) -> str:
        logger.info(
            f"Inserting parent chunk index={document.get('chunk_index')} "
            f"for file={document.get('filename')}"
        )
        result = self._collection.insert_one(document)
        return str(result.inserted_id)
```

**Stored document shape (`parent_chunks` collection):**

```json
{
  "_id": "ObjectId",
  "filename": "report.pdf",
  "username": "alice",
  "chunk_index": 0,
  "text": "...~500 tokens of text...",
  "token_count": 487,
  "created_at": "2026-06-30T10:00:00Z"
}
```

| Field         | Type     | Description                                        |
|---------------|----------|----------------------------------------------------|
| `filename`    | str      | Original PDF filename from the upload request      |
| `username`    | str      | JWT `sub` claim — owner of the upload              |
| `chunk_index` | int      | Zero-based position of this chunk in the document  |
| `text`        | str      | The raw text of this parent chunk                  |
| `token_count` | int      | Actual token count for this chunk (≤500)           |
| `created_at`  | datetime | UTC timestamp at insert time                       |

**Rules:**
- Repository contains only pymongo query logic — no chunking, no embedding, no ChromaDB.
- `@property _collection` pattern prevents collection access before `MongoDBConnection.connect()` is called.
- `insert_one` is synchronous (pymongo). Do not use async.
- Raises pymongo exceptions unmodified; `ChunkingService` converts them to `AppException`.

---

### 6.4 `src/services/chunking.py` — ChunkingService

```python
import logging
import os
from datetime import datetime, timezone

import pymongo.errors

from src.db.chroma_connection import ChromaConnection
from src.repository.chunks import ChunkRepository
from src.schemas.chunks import ParentChunkDocument
from src.utils.exception import AppException

logger = logging.getLogger(__name__)

PARENT_TOKEN_LIMIT = 500
CHILD_TOKEN_LIMIT = 100


class ChunkingService:
    def __init__(self):
        self._repo = ChunkRepository()
        self._openai_api_key = os.environ["OPENAI_API_KEY"]

    def chunk_and_store(self, text: str, filename: str, username: str) -> int:
        ...

    def _split_by_tokens(self, text: str, max_tokens: int) -> list[str]:
        ...

    def _count_tokens(self, text: str) -> int:
        ...

    def _generate_embedding(self, text: str) -> list[float]:
        ...
```

---

#### 6.4.1 Token Counting — `_count_tokens`

```python
def _count_tokens(self, text: str) -> int:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))
```

- Uses `cl100k_base` encoding, which matches the tokenisation used by OpenAI's embedding models (`text-embedding-3-small`, `text-embedding-ada-002`).
- The `tiktoken.get_encoding()` call is cached by tiktoken internally — no need to cache it at the class level.

---

#### 6.4.2 Text Splitting — `_split_by_tokens`

```python
def _split_by_tokens(self, text: str, max_tokens: int) -> list[str]:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    token_ids = enc.encode(text)
    chunks = []
    for start in range(0, len(token_ids), max_tokens):
        chunk_ids = token_ids[start : start + max_tokens]
        chunks.append(enc.decode(chunk_ids))
    return [c for c in chunks if c.strip()]
```

**Rules:**
- Splitting is done on token boundaries, not character or word boundaries. This guarantees the `max_tokens` limit is exact (never exceeded).
- No overlap between chunks — the user story does not request it.
- Empty or whitespace-only chunks are discarded.
- If the entire extracted text is shorter than `max_tokens`, a single chunk equal to the full text is returned.

---

#### 6.4.3 Embedding Generation — `_generate_embedding`

```python
def _generate_embedding(self, text: str) -> list[float]:
    from openai import OpenAI
    client = OpenAI(api_key=self._openai_api_key)
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding
```

**Rules:**
- Model is `text-embedding-3-small` — current default for new OpenAI embedding workloads. Do not hardcode `text-embedding-ada-002`.
- `OpenAI` client is instantiated per call — no connection pooling at this layer (the SDK handles HTTP keep-alive internally).
- Any `openai.OpenAIError` raised here propagates to `chunk_and_store`, which catches it and re-raises as `AppException(500)`.
- Never log the API key or raw embedding vectors.

---

#### 6.4.4 Main Orchestration — `chunk_and_store`

```python
def chunk_and_store(self, text: str, filename: str, username: str) -> int:
    parent_chunks = self._split_by_tokens(text, PARENT_TOKEN_LIMIT)
    logger.info(f"Splitting '{filename}' into {len(parent_chunks)} parent chunks")

    total_children = 0
    chroma_collection = ChromaConnection.get_collection()

    for p_idx, parent_text in enumerate(parent_chunks):
        parent_doc = ParentChunkDocument(
            filename=filename,
            username=username,
            chunk_index=p_idx,
            text=parent_text,
            token_count=self._count_tokens(parent_text),
            created_at=datetime.now(timezone.utc),
        )
        try:
            parent_id = self._repo.insert_parent_chunk(parent_doc.to_dict())
        except pymongo.errors.PyMongoError as e:
            logger.error(f"DB error inserting parent chunk {p_idx} for '{filename}': {e}")
            raise AppException("Internal server error", status_code=500)

        child_chunks = self._split_by_tokens(parent_text, CHILD_TOKEN_LIMIT)
        logger.info(
            f"Parent chunk {p_idx} of '{filename}' split into {len(child_chunks)} child chunks"
        )

        for c_idx, child_text in enumerate(child_chunks):
            try:
                embedding = self._generate_embedding(child_text)
            except Exception as e:
                logger.error(f"OpenAI embedding error for child {c_idx} of parent {p_idx}: {e}")
                raise AppException("Internal server error", status_code=500)

            try:
                chroma_collection.add(
                    ids=[f"{parent_id}_{c_idx}"],
                    embeddings=[embedding],
                    documents=[child_text],
                    metadatas=[{
                        "parent_id": parent_id,
                        "filename": filename,
                        "username": username,
                        "child_index": c_idx,
                    }],
                )
            except Exception as e:
                logger.error(f"ChromaDB add error for child {c_idx} of parent {p_idx}: {e}")
                raise AppException("Internal server error", status_code=500)

            total_children += 1

    logger.info(
        f"chunk_and_store complete for '{filename}': "
        f"{len(parent_chunks)} parents, {total_children} children stored"
    )
    return total_children
```

**Rules:**
- Parent chunks are processed sequentially, not concurrently.
- Child IDs in ChromaDB follow the pattern `"{parent_id}_{child_index}"` to guarantee uniqueness across multiple uploads of the same file.
- `AppException` is never caught inside `chunk_and_store` — only low-level exceptions (pymongo, openai, chromadb) are caught and converted.
- Any failure on any chunk aborts the entire pipeline — no partial-success handling. The partial MongoDB inserts already made are not rolled back (MongoDB has no multi-document transaction here). This is an acceptable trade-off for MVP; rollback can be added later.
- Do not log `parent_text` or `child_text` at INFO level — they may contain sensitive document content.

---

### 6.5 `src/services/upload.py` — Extend UploadService for PDF

Modify `UploadService.__init__` to instantiate `ChunkingService`, and modify `process_upload` to call `chunk_and_store` after PDF extraction.

**`__init__` change:**

```python
from src.services.chunking import ChunkingService

class UploadService:
    def __init__(self):
        self._repo = UploadRepository()
        self._chunking_svc = ChunkingService()
```

**`process_upload` change — PDF branch only:**

```python
if content_type == "pdf":
    extracted_text = self._extract_pdf(binary_data)
    # existing document insert below (unchanged)
    ...
    try:
        self._repo.insert_document(document)
    except pymongo.errors.PyMongoError as e:
        ...

    # NEW: run chunking pipeline
    self._chunking_svc.chunk_and_store(extracted_text, file.filename, username)
```

The call to `chunk_and_store` is placed **after** the document is inserted into `documents` (so the raw document is safely persisted first), and before `uploaded_count` is incremented.

**Rules:**
- Only PDF files trigger the chunking pipeline. CSV, XLS, XLSX continue unchanged.
- `chunk_and_store` propagates `AppException` directly — `process_upload` does not catch it (no try/except wrapping the call).
- `UploadService` does not need to know the return value of `chunk_and_store`; it is used only for internal logging inside `ChunkingService`.

---

### 6.6 `src/main.py` — Initialize ChromaDB at Startup

Add the ChromaDB initialization call immediately after the existing MongoDB connection setup:

```python
from src.db.chroma_connection import ChromaConnection

# ... existing MongoDBConnection.connect(...) call ...

ChromaConnection.initialize()
```

Place it after `MongoDBConnection.connect(...)` and the index creation calls. The order of the two DB initialization calls does not matter, but ChromaDB must be ready before the first PDF upload request is handled.

---

## 7. ChromaDB Document Shape

Each child chunk is stored in the ChromaDB `child_chunks` collection as follows:

| ChromaDB field | Value                                                                        |
|----------------|------------------------------------------------------------------------------|
| `id`           | `"{parent_mongo_id}_{child_index}"` — e.g. `"6839abc...f_0"`               |
| `embedding`    | `list[float]` — 1536-dimensional vector from `text-embedding-3-small`       |
| `document`     | Raw text of the child chunk                                                  |
| `metadata`     | `{ "parent_id": str, "filename": str, "username": str, "child_index": int }` |

**Metadata field descriptions:**

| Field         | Type | Description                                               |
|---------------|------|-----------------------------------------------------------|
| `parent_id`   | str  | String-form MongoDB `_id` of the parent chunk             |
| `filename`    | str  | Original PDF filename                                     |
| `username`    | str  | JWT sub claim — owner of the document                     |
| `child_index` | int  | Zero-based index of this child within its parent chunk    |

---

## 8. MongoDB Collection

- **Collection name:** `parent_chunks`
- **Index:** Compound index on `(username, filename)` to support future queries that retrieve all chunks for a given user's document.
- Add to `src/main.py` alongside existing index definitions:

```python
MongoDBConnection.get_collection("parent_chunks").create_index(
    [("username", ASCENDING), ("filename", ASCENDING)]
)
```

---

## 9. Token Budget Reference

| Chunk type    | Target tokens | Splitting basis             | Approximate characters |
|---------------|---------------|-----------------------------|------------------------|
| Parent chunk  | ~500          | `cl100k_base` token IDs     | ~2 000 chars           |
| Child chunk   | ~100          | `cl100k_base` token IDs     | ~400 chars             |

A 10-page PDF of typical business text (~5 000 words / ~6 500 tokens) will produce approximately:
- 13 parent chunks
- ~65 child chunks
- ~65 OpenAI embedding API calls

---

## 10. Test Plan

### Unit Tests — `tests/unit/test_chunking_service.py`

Mock `ChunkRepository`, the `openai.OpenAI` client, and `ChromaConnection.get_collection()`. Use `unittest.mock.patch` to patch at import boundaries.

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
| `_split_by_tokens` splits correctly | 1500-token text, max=500 | Returns 3 chunks, each ≤500 tokens |
| `_split_by_tokens` short text | 80-token text, max=500 | Returns 1 chunk equal to full text |
| `_split_by_tokens` empty text | `""` | Returns `[]` |
| `_split_by_tokens` whitespace only | `"   \n  "` | Returns `[]` |
| `chunk_and_store` happy path | Valid text; `insert_parent_chunk` returns `"abc123"`; embedding returns 1536-dim vector; ChromaDB add succeeds | Returns total child count; `insert_parent_chunk` called once per parent; ChromaDB `add` called once per child |
| `chunk_and_store` MongoDB error | `insert_parent_chunk` raises `pymongo.errors.PyMongoError` | Raises `AppException(status_code=500)` |
| `chunk_and_store` OpenAI error | embedding call raises `Exception("rate limit")` | Raises `AppException(status_code=500)` |
| `chunk_and_store` ChromaDB error | `chroma_collection.add` raises `Exception` | Raises `AppException(status_code=500)` |
| `_count_tokens` accuracy | `"hello world"` | Returns 2 |

**Patching guidance:**
- Patch `chromadb.Client` when testing ChromaDB interactions to avoid requiring the package environment.
- Patch `openai.OpenAI` at `src.services.chunking.OpenAI` (where it is imported).
- Do not mock `_split_by_tokens` or `_count_tokens` in the `chunk_and_store` tests — test the real tokeniser. The tiktoken encoding is deterministic and fast.

---

## 11. Error Handling Summary

| Failure point                   | Exception raised by           | Caught by              | Re-raised as                         |
|---------------------------------|-------------------------------|------------------------|--------------------------------------|
| `OPENAI_API_KEY` not set        | `os.environ["OPENAI_API_KEY"]`| (propagates to startup)| `KeyError` at `UploadService.__init__` — surfaces as 500 |
| `ChromaConnection` not init     | `ChromaConnection.get_collection()` | `chunk_and_store` | `AppException(500)` propagated directly |
| MongoDB insert failure          | `pymongo.errors.PyMongoError` | `chunk_and_store`      | `AppException("Internal server error", 500)` |
| OpenAI API failure              | `openai.OpenAIError` (or `Exception`) | `chunk_and_store` | `AppException("Internal server error", 500)` |
| ChromaDB add failure            | `Exception`                   | `chunk_and_store`      | `AppException("Internal server error", 500)` |

---

## 12. Out of Scope

- Querying or searching the stored chunks (future RAG story).
- Persisting ChromaDB to disk — in-memory only per the user story.
- Chunking CSV, XLS, or XLSX files — only PDF content is chunked.
- Overlap between chunks — not specified in the user story.
- Deduplication of chunks across multiple uploads of the same file.
- Deleting chunks when a document is re-uploaded or deleted.
- Async embedding generation (batch API calls to OpenAI).
- Support for embedding models other than `text-embedding-3-small`.
- Multi-tenancy isolation within ChromaDB (all users share one collection; filtered by `username` metadata).
