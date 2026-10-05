# Spec: Vector RAG Retrieval (`vector_search` tool)

**ID:** `13-retrieval-workflow-rag`
**Status:** Ready for implementation
**Depends on:** `11-retrieval-workflow-1` (LangGraph agent graph and `vector_search` placeholder must exist), `07-pdf-chunking` / `08-csv-chunking` (ChromaDB `child_chunks` collection and MongoDB `parent_chunks` collection must be populated)

---

## 1. Context

The `vector_search` tool in `src/agents/tools.py` currently returns a placeholder string. This spec replaces the placeholder with a real retrieval pipeline that:

1. Embeds the incoming query using the OpenAI Embedding model.
2. Queries the in-memory ChromaDB `child_chunks` collection for the top-3 semantically similar results.
3. Extracts the `parent_id` from each result's metadata and deduplicates the list.
4. Fetches the corresponding parent chunk documents from MongoDB.
5. Concatenates their `text` fields into a single context string.
6. Returns that context string to the Answer Synthesis Agent.

All pipeline logic lives in a new helper module `src/agents/rag_pipeline.py`. The `vector_search` tool in `tools.py` becomes a thin wrapper, mirroring the existing `graph_search` / `kg_pipeline.py` pattern.

---

## 2. Pipeline Overview

```
vector_search(query)
    │
    ▼
run_vector_search(query)                  ← src/agents/rag_pipeline.py
    │
    ▼
1. _generate_query_embedding(query)       ← OpenAI text-embedding-3-small
    │
    ▼
2. ChromaConnection.get_collection()
   .query(query_embeddings=[embedding], n_results=3)
    │
    ▼
3. Extract parent_id from each result's metadata
    │
    ▼
4. Deduplicate parent_ids (preserve order)
    │
    ▼
5. ChunkRepository.find_parent_chunks_by_ids(parent_ids)  ← MongoDB
    │
    ▼
6. Concatenate text fields  →  context string
    │
    ▼
7. Return context string (or "" if ChromaDB returned no results)
```

---

## 3. Files to Create / Modify

```
src/
  agents/
    tools.py          ← modify: replace vector_search body; import rag_pipeline
    rag_pipeline.py   ← new: run_vector_search + _generate_query_embedding

  repository/
    chunks.py         ← modify: add find_parent_chunks_by_ids method

tests/
  unit/
    test_rag_pipeline.py  ← new: unit tests for all pipeline steps
```

---

## 4. Environment Variables

| Variable | Used by | Notes |
|----------|---------|-------|
| `OPENAI_API_KEY` | `_generate_query_embedding` in `rag_pipeline.py` | Must be present; no default. Read via `os.environ["OPENAI_API_KEY"]` at call time, not module level. |

No new variables are needed beyond what `ChunkingService` already requires.

---

## 5. Data Flows

### 5.1 ChromaDB Query Response Shape

`ChromaConnection.get_collection().query(query_embeddings=[embedding], n_results=3)` returns:

```python
{
    "ids": [["parent1_0", "parent2_1", "parent3_0"]],
    "documents": [["child text...", ...]],
    "metadatas": [[
        {"parent_id": "<mongo_object_id_str>", "filename": "...", "username": "...", "child_index": 0},
        {"parent_id": "<mongo_object_id_str>", ...},
        {"parent_id": "<mongo_object_id_str>", ...},
    ]],
    "distances": [[0.12, 0.23, 0.34]],
}
```

- Results are grouped under a single outer list (batch dimension). Access via `result["metadatas"][0]`.
- `parent_id` is a string representation of the MongoDB `_id` ObjectId.
- Multiple child chunks can share the same `parent_id` (sibling children of one parent).

### 5.2 MongoDB Parent Chunk Document Shape

```python
{
    "_id": ObjectId("..."),
    "filename": "report.pdf",
    "username": "alice",
    "chunk_index": 2,
    "text": "The full parent text block up to 500 tokens...",
    "token_count": 487,
    "created_at": datetime(...),
}
```

Only the `text` field is consumed by the pipeline. `_id` is not exposed to the caller.

---

## 6. Layer Specifications

---

### 6.1 `src/agents/rag_pipeline.py` — Pipeline Helper Module

```python
import logging
import os

from src.db.chroma_connection import ChromaConnection
from src.repository.chunks import ChunkRepository
from src.utils.exception import AppException

logger = logging.getLogger(__name__)

_repo = ChunkRepository()


def _generate_query_embedding(query: str) -> list[float]:
    """Embed a query string using OpenAI text-embedding-3-small."""
    ...


def run_vector_search(query: str) -> str:
    """Orchestrate RAG retrieval. Return context string or '' if no results."""
    ...
```

**Rules:**

- `_repo` is a module-level singleton — instantiated once at import time, consistent with `kg_pipeline.py`.
- `_generate_query_embedding`:
  - Reads `OPENAI_API_KEY` from `os.environ["OPENAI_API_KEY"]` at call time.
  - Uses the `openai` SDK directly (same pattern as `ChunkingService._generate_embedding`): `OpenAI(api_key=...).embeddings.create(model="text-embedding-3-small", input=query)`.
  - Returns `response.data[0].embedding` as `list[float]`.
  - On any exception: log at `error`, raise `AppException("Embedding generation failed", status_code=500)`.
- `run_vector_search`:
  1. Call `_generate_query_embedding(query)`.
  2. Call `ChromaConnection.get_collection().query(query_embeddings=[embedding], n_results=3)`.
  3. Extract `metadatas[0]` from the result. If the list is empty, log at `warning` and return `""`.
  4. Collect `parent_id` from each metadata dict; deduplicate while preserving insertion order (use `dict.fromkeys`).
  5. Call `_repo.find_parent_chunks_by_ids(deduplicated_parent_ids)`.
  6. Concatenate the `text` field of each returned document, separated by `"\n\n"`.
  7. Return the concatenated string.
  8. Any exception from ChromaDB access: log at `error`, raise `AppException("Vector search failed", status_code=500)`.
  9. Any exception from MongoDB access: let it propagate from the repository — do not re-wrap `AppException`.
  10. Do not catch and re-wrap `AppException` raised by `_generate_query_embedding` — let it propagate unchanged.

---

### 6.2 `src/agents/tools.py` — Modified `vector_search` tool

```python
from langchain_core.tools import tool
from src.agents.kg_pipeline import run_graph_search
from src.agents.rag_pipeline import run_vector_search


@tool
def vector_search(query: str) -> str:
    """Search the vector database for semantically similar content."""
    return run_vector_search(query)


@tool
def graph_search(query: str) -> str:
    """Search the knowledge graph for structured entity relationships."""
    return run_graph_search(query)
```

**Rules:**
- `vector_search` docstring must remain present — it is the LangChain tool description.
- `@tool` decorator must be retained.
- `run_vector_search` is the single entry point — `tools.py` contains no pipeline logic directly.
- `graph_search` is unchanged.

---

### 6.3 `src/repository/chunks.py` — Add `find_parent_chunks_by_ids`

Add this method to `ChunkRepository`:

```python
def find_parent_chunks_by_ids(self, parent_ids: list[str]) -> list[dict]:
    """Fetch parent chunk documents from MongoDB by their string IDs."""
    from bson import ObjectId
    logger.info(f"Fetching {len(parent_ids)} parent chunk(s) by ID")
    if not parent_ids:
        return []
    object_ids = [ObjectId(pid) for pid in parent_ids]
    return list(self._collection.find({"_id": {"$in": object_ids}}))
```

**Rules:**
- Log at `logger.info` on entry with the count of IDs requested.
- Short-circuit and return `[]` immediately when `parent_ids` is empty — avoids a no-op query.
- Convert each string ID to `bson.ObjectId` before querying (same pattern as `KnowledgeGraphRepository`).
- Use `$in` for a single batched query rather than iterating per ID.
- Return raw dicts from pymongo (the `_id` field will be an `ObjectId`, but only `text` is consumed upstream — no need to convert).
- Do not raise `AppException` here — let pymongo exceptions propagate to the service layer (`run_vector_search`).

---

## 7. Embedding Model

| Property | Value |
|----------|-------|
| Provider | OpenAI |
| Model | `text-embedding-3-small` |
| SDK | `openai` (direct, not LangChain wrapper) |
| Input | Query string |
| Output | `list[float]` (1536 dimensions) |

This is the **same model and SDK pattern** used in `ChunkingService._generate_embedding` — ensures embedding space compatibility between stored child chunks and query vectors.

---

## 8. Deduplication Logic

Multiple child chunks stored under the same parent produce multiple hits in ChromaDB. Because we always want whole parent chunks as context, we deduplicate `parent_id` values before the MongoDB fetch:

```python
# Result: metadatas = [{"parent_id": "aaa"}, {"parent_id": "bbb"}, {"parent_id": "aaa"}]
parent_ids = [m["parent_id"] for m in metadatas]
unique_parent_ids = list(dict.fromkeys(parent_ids))  # ["aaa", "bbb"] — order preserved
```

`dict.fromkeys` removes duplicates while preserving the order in which IDs first appeared (closest-match-first, since ChromaDB orders by ascending cosine distance).

---

## 9. Unit Test Plan — `tests/unit/test_rag_pipeline.py`

All external calls (OpenAI, ChromaDB, MongoDB) are mocked via `unittest.mock`.

```python
import os
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")

import pytest
from unittest.mock import MagicMock, patch
from src.agents.rag_pipeline import _generate_query_embedding, run_vector_search
from src.utils.exception import AppException
```

---

### Fixtures

```python
@pytest.fixture()
def chroma_result_3():
    """Simulates ChromaDB returning 3 child chunks from 2 distinct parents."""
    return {
        "ids": [["aaa_0", "bbb_0", "aaa_1"]],
        "documents": [["child1", "child2", "child3"]],
        "metadatas": [[
            {"parent_id": "aaa", "filename": "f.pdf", "username": "u", "child_index": 0},
            {"parent_id": "bbb", "filename": "f.pdf", "username": "u", "child_index": 0},
            {"parent_id": "aaa", "filename": "f.pdf", "username": "u", "child_index": 1},
        ]],
        "distances": [[0.1, 0.2, 0.3]],
    }


@pytest.fixture()
def chroma_result_empty():
    return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


@pytest.fixture()
def parent_docs():
    return [
        {"_id": "aaa", "text": "Parent A text.", "chunk_index": 0},
        {"_id": "bbb", "text": "Parent B text.", "chunk_index": 0},
    ]
```

---

### GE — Embedding Generation (`_generate_query_embedding`)

Mock `src.agents.rag_pipeline.OpenAI` (or `openai.OpenAI`).

| ID | Test | Setup | Assertion |
|----|------|-------|-----------|
| GE-01 | Returns a list of floats | Mock response with `data[0].embedding = [0.1, 0.2]` | `isinstance(result, list)` and `result == [0.1, 0.2]` |
| GE-02 | Uses `text-embedding-3-small` model | Valid mock response | `client.embeddings.create` called with `model="text-embedding-3-small"` |
| GE-03 | Passes query as `input` | Query `"test query"` | `client.embeddings.create` called with `input="test query"` |
| GE-04 | Reads API key from env | `os.environ["OPENAI_API_KEY"] = "sk-xyz"` | `OpenAI` instantiated with `api_key="sk-xyz"` |
| GE-05 | OpenAI exception raises AppException 500 | Mock `embeddings.create` raises `Exception("quota exceeded")` | `AppException` raised with `status_code=500` |
| GE-06 | AppException message is descriptive | Same setup as GE-05 | `"Embedding generation failed"` in `exc.message` |

---

### VS — Vector Search (`run_vector_search`)

Mock `src.agents.rag_pipeline._generate_query_embedding`, `src.agents.rag_pipeline.ChromaConnection`, and `src.agents.rag_pipeline._repo`.

| ID | Test | Setup | Assertion |
|----|------|-------|-----------|
| VS-01 | Returns a non-empty string on success | 3 child results → 2 parent docs | `isinstance(result, str)` and `len(result) > 0` |
| VS-02 | Returned string contains parent chunk text | Parent docs with `text="Parent A text."` | `"Parent A text."` in result |
| VS-03 | Multiple parent texts are concatenated | 2 parent docs | Both texts present in result |
| VS-04 | Texts are separated by double newline | 2 parent docs | `"\n\n"` present in result |
| VS-05 | Returns empty string when ChromaDB returns no results | `chroma_result_empty` fixture | `result == ""` |
| VS-06 | `_generate_query_embedding` is called with the query | Valid results | `_generate_query_embedding` called once with the query string |
| VS-07 | ChromaDB query called with embedding | `_generate_query_embedding` returns `[0.1, 0.2]` | `collection.query` called with `query_embeddings=[[0.1, 0.2]]` |
| VS-08 | ChromaDB query requests top 3 results | Valid setup | `collection.query` called with `n_results=3` |
| VS-09 | Duplicate parent_ids are deduplicated before MongoDB fetch | `chroma_result_3` (2 "aaa", 1 "bbb") | `_repo.find_parent_chunks_by_ids` called with list containing "aaa" exactly once |
| VS-10 | MongoDB is not called when ChromaDB returns empty | `chroma_result_empty` | `_repo.find_parent_chunks_by_ids` not called |
| VS-11 | All unique parent_ids are fetched | `chroma_result_3` → 2 unique IDs | `_repo.find_parent_chunks_by_ids` called with a list of length 2 |
| VS-12 | Closest-match parent appears first in context | `chroma_result_3` (aaa first) | Context starts with parent "aaa"'s text |
| VS-13 | ChromaDB access error raises AppException 500 | `collection.query` raises `Exception("chroma down")` | `AppException` raised with `status_code=500` |
| VS-14 | AppException from embedding propagates unchanged | `_generate_query_embedding` raises `AppException(500)` | Same `AppException` raised (not re-wrapped) |
| VS-15 | Empty parent docs list produces empty string | `_repo.find_parent_chunks_by_ids` returns `[]` | `result == ""` |

---

### FR — `ChunkRepository.find_parent_chunks_by_ids`

Mock `src.repository.chunks.MongoDBConnection`.

| ID | Test | Setup | Assertion |
|----|------|-------|-----------|
| FR-01 | Returns a list | Mock `find` yields 2 docs | `isinstance(result, list)` |
| FR-02 | Returns all matching docs | Mock `find` yields 2 docs | `len(result) == 2` |
| FR-03 | Empty `parent_ids` returns `[]` immediately | Call with `[]` | `result == []`; `find` never called |
| FR-04 | Uses `$in` query with ObjectId list | Call with `["aaa123", "bbb456"]` | `collection.find` called with `{"_id": {"$in": [ObjectId("aaa123"), ObjectId("bbb456")]}}` |
| FR-05 | Single ID works | Call with one ID | `result` has one item; `find` called once |
| FR-06 | All fetched documents are returned | Mock returns 3 docs | `len(result) == 3` |

---

## 10. Error Handling Summary

| Failure point | Raised by | Behaviour |
|---|---|---|
| OpenAI quota / network error | `_generate_query_embedding` | `AppException("Embedding generation failed", 500)` |
| ChromaDB unavailable / query error | `run_vector_search` | `AppException("Vector search failed", 500)` |
| ChromaDB returns no results | `run_vector_search` | Returns `""` — not an error; Answer Agent handles empty context gracefully |
| MongoDB query error (pymongo) | `ChunkRepository.find_parent_chunks_by_ids` → propagates to `run_vector_search` | pymongo exception propagates; not caught in `run_vector_search` — handled by `ChatService.ask` |
| `AppException` from sub-steps | `run_vector_search` | Propagates unchanged — not re-wrapped |

---

## 11. What Not To Do

- Do not use `langchain_openai` embeddings — use the `openai` SDK directly to match the embedding space used during chunking.
- Do not use a different embedding model than `text-embedding-3-small` — mixing models produces incompatible vector spaces.
- Do not store `ChromaConnection.get_collection()` as a module-level variable — follow the same call-per-use pattern as `ChunkingService`.
- Do not iterate MongoDB with one query per `parent_id` — use `$in` for a single batched fetch.
- Do not catch and re-wrap `AppException` inside `run_vector_search`.
- Do not add try/except in `vector_search` in `tools.py` — errors propagate to `vector_agent` and then to `ChatService.ask`.
- Do not expose `_id` or other internal MongoDB fields in the return value — only `text` is consumed.
- Do not cache the embedding or ChromaDB collection as module-level state between calls.
- Do not use `print()` anywhere — use `logger`.
- Do not skip the `@tool` decorator on `vector_search`.
