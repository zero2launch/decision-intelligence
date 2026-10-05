# Spec: Knowledge Graph Ingestion Pipeline

**ID:** `09-kg-pipeline`
**Status:** Ready for implementation
**Depends on:** `08-csv-chunking` (`ChunkingService` with `chunk_and_store` and `chunk_and_store_tabular` must exist), `06-upload-api-file-conversion` (`UploadService` text extraction methods must exist)

---

## 1. Context

`UploadService.process_upload()` currently routes uploaded files to a vector store pipeline: PDFs go through `chunk_and_store` (parent-child token chunking → ChromaDB); CSV/XLS/XLSX files go through `chunk_and_store_tabular` (row chunking → ChromaDB).

This spec adds a **Knowledge Graph (KG) Ingestion Pipeline** that extracts structured entities and relationships from document text and writes them to a Neo4j graph database via six sequential stages:

1. **Data + Ontology** — combine extracted text with `ontology/ontology_context.md` as LLM system context
2. **LLM** — call Claude to extract entities and relationships that match the ontology schema
3. **Structured JSON** — parse LLM output into `{ "nodes": [...], "relationships": [...] }`
4. **Validation** — drop nodes/relationships that violate ontology constraints (wrong label, missing required fields, invalid enum values); warn via logger, do not fail
5. **Entity Resolution** — check Neo4j for existing nodes by unique key; merge properties if found; skip duplicate relationships
6. **Neo4j MERGE** — write idempotently via Cypher `MERGE`

**File type behavior changes:**

- **PDF**: run `chunk_and_store` (vector store) AND the KG pipeline in **parallel** using `ThreadPoolExecutor`. KG failure is caught and logged; it must not fail the upload.
- **CSV/XLS/XLSX**: **replace** `chunk_and_store_tabular` with the KG pipeline only. KG failure propagates as `AppException(500)`.

No new HTTP endpoint is introduced. The HTTP response remains `UploadResponse(success=True, uploaded=<n>)`.

---

## 2. Pipeline Overview

```
UploadService.process_upload()   [existing, modified]
    │
    ├─ PDF branch
    │     ├─ ThreadPoolExecutor(max_workers=2)
    │     │     ├─ Future A: _chunking_svc.chunk_and_store(...)   [existing — unchanged]
    │     │     └─ Future B: _kg_svc.process_document(...)        [NEW]
    │     ├─ future_A.result()   → propagates AppException if failed
    │     └─ future_B.result()   → caught + logged; never fails upload
    │
    └─ CSV/XLS/XLSX branch
          └─ _kg_svc.process_document(...)   [NEW — replaces chunk_and_store_tabular]


KnowledgeGraphService.process_document(extracted_text, filename)
    │
    ├─ Stage 1: build LLM prompt
    │     ├─ system: ontology_context.md (loaded at service init, cached in self._ontology)
    │     └─ user:   extracted_text (truncated to MAX_EXTRACTION_CHARS = 50_000)
    │
    ├─ Stage 2: _call_llm(text) → raw_json_str  [OpenAI chat completions, model from OPENAI_MODEL]
    │
    ├─ Stage 3: _parse_llm_output(raw_json_str) → { "nodes": [...], "relationships": [...] }
    │
    ├─ Stage 4: _validate(parsed, result)
    │     ├─ drop nodes with unknown label (log warning per node)
    │     ├─ drop nodes missing required fields (log warning per node)
    │     ├─ drop nodes with invalid enum values (log warning per node)
    │     └─ drop relationships with unknown type / invalid from-to label combo (log warning per rel)
    │
    ├─ Stage 5+6: _write_nodes(valid_nodes, result)
    │               → _repo.merge_node(label, unique_key, props) per node
    │             _write_relationships(valid_rels, result)
    │               → _repo.relationship_exists(...) → skip if true
    │               → _repo.create_relationship(...) if not exists
    │
    └─ return KGIngestResult(nodes_created, nodes_merged, relationships_created,
                             relationships_skipped, nodes_dropped, relationships_dropped)
```

---

## 3. Files to Create / Modify

```
src/
  db/
    neo4j_connection.py               ← NEW: Neo4jConnection singleton
  repository/
    knowledge_graph.py                ← NEW: KnowledgeGraphRepository
  services/
    knowledge_graph.py                ← NEW: KnowledgeGraphService + KGIngestResult
    upload.py                         ← MODIFY: PDF parallel + CSV/XLS/XLSX KG-only
  main.py                             ← MODIFY: init Neo4jConnection at startup

ontology/
  ontology_context.md                 ← existing (read-only; consumed at service init)

tests/
  unit/
    test_knowledge_graph_service.py   ← NEW: unit tests
```

---

## 4. Dependencies to Add

```bash
uv add neo4j
```

| Package  | Purpose                                                 |
|----------|---------------------------------------------------------|
| `neo4j`  | Official Neo4j Python driver (synchronous, thread-safe) |
| `openai` | OpenAI Python SDK for calling chat completions API (already installed) |

---

## 5. Environment Variables

Add to `.env`:

```
NEO4J_URL=neo4j://127.0.0.1:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-neo4j-password>
OPENAI_API_KEY=<your-openai-key>
OPENAI_MODEL=gpt-4o-mini
```

`NEO4J_PASSWORD` has no default — a missing key raises `KeyError` at startup.
`OPENAI_API_KEY` is shared with the chunking service (already required). `OPENAI_MODEL` defaults to `gpt-4o-mini` if not set.

---

## 6. Layer Specifications

---

### 6.1 `src/db/neo4j_connection.py` — Neo4jConnection Singleton

Mirrors `MongoDBConnection` exactly in structure: class-level driver state, idempotent `connect()`, `get_driver()` raises `AppException(500)` if called before `connect()`, `close()` cleans up.

```python
import logging

from src.utils.exception import AppException

logger = logging.getLogger(__name__)


class Neo4jConnection:
    _driver = None

    @classmethod
    def connect(cls, uri: str, user: str, password: str) -> None:
        if cls._driver is not None:
            return
        from neo4j import GraphDatabase
        cls._driver = GraphDatabase.driver(uri, auth=(user, password))
        logger.info(f"Connected to Neo4j: {uri}")

    @classmethod
    def get_driver(cls):
        if cls._driver is None:
            raise AppException("Neo4j not initialized. Call connect() first.", status_code=500)
        return cls._driver

    @classmethod
    def close(cls) -> None:
        if cls._driver:
            cls._driver.close()
            cls._driver = None
            logger.info("Neo4j connection closed")
```

**Rules:**
- `connect()` is idempotent — guards on `_driver is not None`.
- `GraphDatabase` is imported lazily inside `connect()` so the module can be imported without the `neo4j` package present (test isolation).
- The neo4j driver manages a connection pool internally and is thread-safe — one driver instance is shared across all threads.
- `get_driver()` must only be called from `KnowledgeGraphRepository`. No other layer accesses `Neo4jConnection` directly.

---

### 6.2 `src/repository/knowledge_graph.py` — KnowledgeGraphRepository

Contains only Neo4j Cypher query logic. No business logic, no LLM calls, no validation.

```python
import logging

from src.db.neo4j_connection import Neo4jConnection

logger = logging.getLogger(__name__)


class KnowledgeGraphRepository:

    @property
    def _driver(self):
        return Neo4jConnection.get_driver()

    def merge_node(self, label: str, unique_key: str, properties: dict) -> bool:
        """MERGE node by unique key; set all properties on create, merge on match.
        Returns True if the node was newly created, False if it already existed."""
        logger.info(f"Merging node label={label} {unique_key}={properties.get(unique_key)}")
        query = (
            f"MERGE (n:{label} {{{unique_key}: $key_value}}) "
            f"ON CREATE SET n = $props "
            f"ON MATCH SET n += $props "
            f"RETURN n"
        )
        with self._driver.session() as session:
            result = session.run(query, key_value=properties[unique_key], props=properties)
            summary = result.consume()
            return summary.counters.nodes_created > 0

    def relationship_exists(
        self,
        from_label: str,
        from_key: str,
        from_value,
        to_label: str,
        to_key: str,
        to_value,
        rel_type: str,
    ) -> bool:
        logger.info(
            f"Checking ({from_label})-[:{rel_type}]->({to_label}) "
            f"{from_key}={from_value} → {to_key}={to_value}"
        )
        query = (
            f"MATCH (a:{from_label} {{{from_key}: $from_value}})"
            f"-[r:{rel_type}]->"
            f"(b:{to_label} {{{to_key}: $to_value}}) "
            f"RETURN count(r) AS cnt"
        )
        with self._driver.session() as session:
            result = session.run(query, from_value=from_value, to_value=to_value)
            record = result.single()
            return (record["cnt"] > 0) if record else False

    def create_relationship(
        self,
        from_label: str,
        from_key: str,
        from_value,
        to_label: str,
        to_key: str,
        to_value,
        rel_type: str,
    ) -> None:
        logger.info(f"Creating ({from_label})-[:{rel_type}]->({to_label})")
        query = (
            f"MATCH (a:{from_label} {{{from_key}: $from_value}}) "
            f"MATCH (b:{to_label} {{{to_key}: $to_value}}) "
            f"MERGE (a)-[:{rel_type}]->(b)"
        )
        with self._driver.session() as session:
            session.run(query, from_value=from_value, to_value=to_value)
```

**Rules:**
- `@property _driver` fetches lazily from the singleton — never stored as an instance attribute.
- Each method opens its own short-lived session with `with self._driver.session()` — sessions are not shared across calls.
- **Parameterized values**: node property values, relationship endpoint values use `$param` placeholders. Label names and relationship types are interpolated into the query template because Neo4j does not support parameterized label/type names; they are always validated against the ontology whitelist by the service layer before reaching this repo.
- `MERGE` on nodes: `ON CREATE SET n = $props` sets all properties at creation; `ON MATCH SET n += $props` merges (does not clobber) existing properties on match.
- `MERGE` on relationships uses `MATCH ... MATCH ... MERGE (a)-[:TYPE]->(b)` — requires both endpoint nodes to exist first. The service layer guarantees all nodes are written before relationships.
- Raises native `neo4j.exceptions.Neo4jError` on failures; the service layer converts these to `AppException`.
- Never raise `AppException` from this layer.
- Every public method must log at `logger.info` on entry.

---

### 6.3 `src/services/knowledge_graph.py` — KnowledgeGraphService

Orchestrates all six pipeline stages. Reads the ontology file once at `__init__` and caches it in `self._ontology`.

```python
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from src.repository.knowledge_graph import KnowledgeGraphRepository
from src.utils.exception import AppException

logger = logging.getLogger(__name__)

MAX_EXTRACTION_CHARS = 50_000

_ONTOLOGY_PATH = Path(__file__).parent.parent.parent / "ontology" / "ontology_context.md"

_UNIQUE_KEYS: dict[str, str] = {
    "Deal": "deal_id",
    "Quarter": "name",
    "Industry": "name",
    "Region": "name",
    "ServiceOffering": "name",
    "Technology": "name",
    "Account": "name",
    "SalesRep": "name",
    "PipelineStage": "name",
    "LossReason": "name",
    "Project": "project_id",
    "DeliveryIssue": "name",
    "Skill": "name",
    "Employee": "employee_id",
}

_REQUIRED_FIELDS: dict[str, set[str]] = {
    "Deal": {"deal_id", "name", "value", "status"},
    "Quarter": {"name", "year", "quarter"},
    "Industry": {"name"},
    "Region": {"name"},
    "ServiceOffering": {"name"},
    "Technology": {"name"},
    "Account": {"name"},
    "SalesRep": {"name"},
    "PipelineStage": {"name"},
    "LossReason": {"name"},
    "Project": {"project_id", "name"},
    "DeliveryIssue": {"name"},
    "Skill": {"name"},
    "Employee": {"employee_id", "name"},
}

_ENUM_CONSTRAINTS: dict[tuple[str, str], set[str]] = {
    ("Deal", "status"): {"Won", "Lost", "Active"},
    ("Account", "tier"): {"Enterprise", "Mid-Market", "Government"},
    ("DeliveryIssue", "category"): {"HR", "Engineering", "Management"},
    ("DeliveryIssue", "severity"): {"High", "Medium", "Low"},
    ("Employee", "level"): {"Junior", "Mid", "Senior"},
}

_VALID_RELATIONSHIPS: set[tuple[str, str, str]] = {
    ("Deal", "IN_QUARTER", "Quarter"),
    ("Deal", "IN_INDUSTRY", "Industry"),
    ("Deal", "IN_REGION", "Region"),
    ("Deal", "USES_SERVICE", "ServiceOffering"),
    ("Deal", "USES_TECHNOLOGY", "Technology"),
    ("Deal", "FOR_ACCOUNT", "Account"),
    ("Deal", "MANAGED_BY", "SalesRep"),
    ("Deal", "AT_STAGE", "PipelineStage"),
    ("Deal", "LOST_DUE_TO", "LossReason"),
    ("Deal", "REQUIRES_SKILL", "Skill"),
    ("Account", "IN_INDUSTRY", "Industry"),
    ("Account", "IN_REGION", "Region"),
    ("Project", "EXECUTES", "Deal"),
    ("Project", "USES_TECHNOLOGY", "Technology"),
    ("Project", "HAS_ISSUE", "DeliveryIssue"),
    ("Employee", "HAS_SKILL", "Skill"),
    ("Employee", "WORKS_ON", "Project"),
}


@dataclass
class KGIngestResult:
    nodes_created: int = 0
    nodes_merged: int = 0
    relationships_created: int = 0
    relationships_skipped: int = 0
    nodes_dropped: int = 0
    relationships_dropped: int = 0


class KnowledgeGraphService:
    def __init__(self):
        self._repo = KnowledgeGraphRepository()
        self._openai_api_key = os.environ["OPENAI_API_KEY"]
        self._openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._ontology = _ONTOLOGY_PATH.read_text(encoding="utf-8")

    def process_document(self, extracted_text: str, filename: str) -> KGIngestResult:
        logger.info(f"KG pipeline started for '{filename}'")
        text = extracted_text[:MAX_EXTRACTION_CHARS]

        raw = self._call_llm(text)
        parsed = self._parse_llm_output(raw, filename)
        result = KGIngestResult()
        valid_nodes, valid_rels = self._validate(parsed, result)
        self._write_nodes(valid_nodes, result)
        self._write_relationships(valid_rels, result)

        logger.info(
            f"KG pipeline complete for '{filename}': "
            f"nodes created={result.nodes_created} merged={result.nodes_merged} "
            f"dropped={result.nodes_dropped}; "
            f"rels created={result.relationships_created} "
            f"skipped={result.relationships_skipped} dropped={result.relationships_dropped}"
        )
        return result

    def _call_llm(self, text: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=self._openai_api_key)
        response = client.chat.completions.create(
            model=self._openai_model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": text},
            ],
        )
        return response.choices[0].message.content

    def _build_system_prompt(self) -> str:
        return f"""You are a knowledge graph extraction assistant.

Given document text, extract entities and relationships that match the following ontology:

{self._ontology}

Return ONLY valid JSON in this exact format — no markdown fences, no explanation:
{{
  "nodes": [
    {{"label": "<NodeLabel>", "properties": {{"<field>": "<value>", ...}}}}
  ],
  "relationships": [
    {{
      "from_label": "<Label>",
      "from_value": "<unique_key_value>",
      "to_label": "<Label>",
      "to_value": "<unique_key_value>",
      "type": "<RELATIONSHIP_TYPE>"
    }}
  ]
}}

Rules:
- Only extract entities and relationships explicitly present in the document text.
- Only use node labels and relationship types defined in the ontology.
- Every node must include all required fields (marked with ! in the ontology).
- Respect enum constraints exactly as specified (case-sensitive).
- If an optional field value cannot be determined from the text, omit the field entirely.
- Do not invent or hallucinate values not present in the document."""

    def _parse_llm_output(self, raw: str, filename: str) -> dict:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(
                f"LLM returned non-JSON for '{filename}': {e}. "
                f"Raw (first 200 chars): {raw[:200]}"
            )
            raise AppException("KG extraction failed: LLM returned invalid JSON", status_code=500)
        if not isinstance(parsed, dict):
            raise AppException("KG extraction failed: LLM JSON is not an object", status_code=500)
        parsed.setdefault("nodes", [])
        parsed.setdefault("relationships", [])
        return parsed

    def _validate(
        self, parsed: dict, result: KGIngestResult
    ) -> tuple[list[dict], list[dict]]:
        valid_nodes: list[dict] = []
        for node in parsed.get("nodes", []):
            label = node.get("label")
            props = node.get("properties", {})

            if label not in _UNIQUE_KEYS:
                logger.warning(f"Dropping node: unknown label '{label}'")
                result.nodes_dropped += 1
                continue

            required = _REQUIRED_FIELDS.get(label, set())
            missing = [f for f in required if not props.get(f)]
            if missing:
                logger.warning(f"Dropping {label} node: missing required fields {missing}")
                result.nodes_dropped += 1
                continue

            invalid_enum = False
            for (lbl, field), allowed in _ENUM_CONSTRAINTS.items():
                if lbl == label and field in props and props[field] not in allowed:
                    logger.warning(
                        f"Dropping {label} node: '{field}' value '{props[field]}' "
                        f"not in {allowed}"
                    )
                    invalid_enum = True
                    break
            if invalid_enum:
                result.nodes_dropped += 1
                continue

            valid_nodes.append(node)

        valid_rels: list[dict] = []
        for rel in parsed.get("relationships", []):
            from_label = rel.get("from_label")
            to_label = rel.get("to_label")
            rel_type = rel.get("type")
            from_value = rel.get("from_value")
            to_value = rel.get("to_value")

            if not all([from_label, to_label, rel_type, from_value is not None, to_value is not None]):
                logger.warning(f"Dropping relationship: missing required fields in {rel}")
                result.relationships_dropped += 1
                continue

            if (from_label, rel_type, to_label) not in _VALID_RELATIONSHIPS:
                logger.warning(
                    f"Dropping relationship: ({from_label})-[:{rel_type}]->({to_label}) "
                    f"not in ontology"
                )
                result.relationships_dropped += 1
                continue

            valid_rels.append(rel)

        return valid_nodes, valid_rels

    def _write_nodes(self, nodes: list[dict], result: KGIngestResult) -> None:
        for node in nodes:
            label = node["label"]
            props = node["properties"]
            unique_key = _UNIQUE_KEYS[label]
            try:
                created = self._repo.merge_node(label, unique_key, props)
            except Exception as e:
                logger.error(f"Neo4j node MERGE failed for {label}: {e}")
                raise AppException("KG write failed", status_code=500)
            if created:
                result.nodes_created += 1
            else:
                result.nodes_merged += 1

    def _write_relationships(self, rels: list[dict], result: KGIngestResult) -> None:
        for rel in rels:
            from_label = rel["from_label"]
            to_label = rel["to_label"]
            rel_type = rel["type"]
            from_key = _UNIQUE_KEYS[from_label]
            to_key = _UNIQUE_KEYS[to_label]
            from_value = rel["from_value"]
            to_value = rel["to_value"]
            try:
                exists = self._repo.relationship_exists(
                    from_label, from_key, from_value,
                    to_label, to_key, to_value,
                    rel_type,
                )
            except Exception as e:
                logger.error(f"Neo4j relationship check failed: {e}")
                raise AppException("KG write failed", status_code=500)
            if exists:
                result.relationships_skipped += 1
                continue
            try:
                self._repo.create_relationship(
                    from_label, from_key, from_value,
                    to_label, to_key, to_value,
                    rel_type,
                )
                result.relationships_created += 1
            except Exception as e:
                logger.error(f"Neo4j relationship create failed: {e}")
                raise AppException("KG write failed", status_code=500)
```

**Rules:**
- `process_document` does not catch `AppException` — it propagates to the upload handler.
- `_call_llm` instantiates the OpenAI client per call (the SDK manages HTTP keep-alive).
- `_call_llm` never logs the input text — it may contain sensitive document content.
- `MAX_EXTRACTION_CHARS = 50_000` protects against LLM token overflow for large documents. Truncation is silent (logged at INFO in `process_document`).
- `_validate` never raises `AppException` — it only logs `logger.warning` and increments drop counters.
- `_write_nodes` must complete before `_write_relationships` — relationships require their endpoint nodes to already exist in Neo4j.
- The `from_key` and `to_key` for relationships are always derived from `_UNIQUE_KEYS`, not from LLM output.

---

### 6.4 `src/services/upload.py` — Modify UploadService

**Import additions (top of file):**
```python
from concurrent.futures import ThreadPoolExecutor, Future
from src.services.knowledge_graph import KnowledgeGraphService
```

**`__init__` addition:**
```python
self._kg_svc = KnowledgeGraphService()
```

**`process_upload` — replace the file-type dispatch block:**

Current code (lines 51–54):
```python
if content_type == "pdf":
    self._chunking_svc.chunk_and_store(extracted_text, file.filename, username)
elif content_type in {"csv", "xls", "xlsx"}:
    self._chunking_svc.chunk_and_store_tabular(extracted_text, file.filename, username)
```

Replacement:
```python
if content_type == "pdf":
    with ThreadPoolExecutor(max_workers=2) as executor:
        vector_future: Future = executor.submit(
            self._chunking_svc.chunk_and_store,
            extracted_text, file.filename, username,
        )
        kg_future: Future = executor.submit(
            self._kg_svc.process_document,
            extracted_text, file.filename,
        )
    vector_future.result()
    try:
        kg_future.result()
    except Exception as e:
        logger.warning(f"KG pipeline failed for '{file.filename}', continuing: {e}")

elif content_type in {"csv", "xls", "xlsx"}:
    self._kg_svc.process_document(extracted_text, file.filename)
```

**Rules:**
- The `ThreadPoolExecutor` context manager waits for both futures to complete before the `with` block exits. `.result()` calls are placed **outside** the `with` block — this avoids a subtle deadlock where calling `.result()` inside the executor's own thread pool can block indefinitely.
- `vector_future.result()` is called before `kg_future.result()` — vector store failure preserves existing error behavior (propagates `AppException`).
- `kg_future.result()` is always evaluated even if `vector_future.result()` raises, because the `with` block completes before either `.result()` call runs. If `vector_future` raises, the `kg_future.result()` line is never reached — this is acceptable since the upload fails anyway.
- KG failure for PDF is caught by `except Exception` — this catches both `AppException` and any Anthropic/Neo4j exceptions that propagated out of `process_document`.
- `chunk_and_store_tabular` is removed entirely. No tabular vector store path remains after this change.
- `username` is **not** passed to `process_document` — the KG is a shared global graph, not user-scoped.

---

### 6.5 `src/main.py` — Initialize Neo4j at Startup

Add after existing `ChromaConnection.initialize()` call:

```python
from src.db.neo4j_connection import Neo4jConnection

Neo4jConnection.connect(
    uri=os.environ.get("NEO4J_URL", "bolt://localhost:7687"),
    user=os.environ.get("NEO4J_USERNAME", "neo4j"),
    password=os.environ["NEO4J_PASSWORD"],
)
```

**Rules:**
- `NEO4J_PASSWORD` has no default — a missing key raises `KeyError` at startup.
- Place after `ChromaConnection.initialize()` and before `app = FastAPI(...)`.
- Do not add Neo4j index/constraint creation in `main.py` — this is managed by a separate DB migration script (out of scope).

---

## 7. Ontology Validation Reference

### 7.1 Unique Keys Per Label (for MERGE and entity resolution)

| Label | Unique key |
|-------|-----------|
| Deal | `deal_id` |
| Quarter | `name` |
| Industry | `name` |
| Region | `name` |
| ServiceOffering | `name` |
| Technology | `name` |
| Account | `name` |
| SalesRep | `name` |
| PipelineStage | `name` |
| LossReason | `name` |
| Project | `project_id` |
| DeliveryIssue | `name` |
| Skill | `name` |
| Employee | `employee_id` |

### 7.2 Required Fields Per Label

| Label | Required fields |
|-------|----------------|
| Deal | `deal_id`, `name`, `value`, `status` |
| Quarter | `name`, `year`, `quarter` |
| Industry | `name` |
| Region | `name` |
| ServiceOffering | `name` |
| Technology | `name` |
| Account | `name` |
| SalesRep | `name` |
| PipelineStage | `name` |
| LossReason | `name` |
| Project | `project_id`, `name` |
| DeliveryIssue | `name` |
| Skill | `name` |
| Employee | `employee_id`, `name` |

### 7.3 Enum Constraints

| Label | Field | Allowed values |
|-------|-------|----------------|
| Deal | `status` | `Won`, `Lost`, `Active` |
| Account | `tier` | `Enterprise`, `Mid-Market`, `Government` |
| DeliveryIssue | `category` | `HR`, `Engineering`, `Management` |
| DeliveryIssue | `severity` | `High`, `Medium`, `Low` |
| Employee | `level` | `Junior`, `Mid`, `Senior` |

### 7.4 Valid Relationship Triples

| From | Type | To |
|------|------|----|
| Deal | IN_QUARTER | Quarter |
| Deal | IN_INDUSTRY | Industry |
| Deal | IN_REGION | Region |
| Deal | USES_SERVICE | ServiceOffering |
| Deal | USES_TECHNOLOGY | Technology |
| Deal | FOR_ACCOUNT | Account |
| Deal | MANAGED_BY | SalesRep |
| Deal | AT_STAGE | PipelineStage |
| Deal | LOST_DUE_TO | LossReason |
| Deal | REQUIRES_SKILL | Skill |
| Account | IN_INDUSTRY | Industry |
| Account | IN_REGION | Region |
| Project | EXECUTES | Deal |
| Project | USES_TECHNOLOGY | Technology |
| Project | HAS_ISSUE | DeliveryIssue |
| Employee | HAS_SKILL | Skill |
| Employee | WORKS_ON | Project |

---

## 8. LLM Output Format

The LLM must return a bare JSON object (no markdown fences, no explanation). Example for a document containing deal data:

```json
{
  "nodes": [
    {
      "label": "Deal",
      "properties": {
        "deal_id": "D-001",
        "name": "Acme Corp Expansion",
        "value": 150000.0,
        "status": "Won"
      }
    },
    {
      "label": "Account",
      "properties": {
        "name": "Acme Corp",
        "tier": "Enterprise"
      }
    }
  ],
  "relationships": [
    {
      "from_label": "Deal",
      "from_value": "D-001",
      "to_label": "Account",
      "to_value": "Acme Corp",
      "type": "FOR_ACCOUNT"
    }
  ]
}
```

**Notes:**
- `from_value` and `to_value` must be the unique key values for their respective labels (e.g., `deal_id` value for `Deal`, `name` value for `Account`).
- The service always resolves the actual unique key field name from `_UNIQUE_KEYS` — the LLM does not need to specify key field names in relationships.

---

## 9. Test Plan

### Unit Tests — `tests/unit/test_knowledge_graph_service.py`

Mock `KnowledgeGraphRepository` and the Anthropic client using `unittest.mock.patch`.

```python
@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    ontology_file = tmp_path / "ontology_context.md"
    ontology_file.write_text("## Schema\nDeal: deal_id:STRING!")
    with patch("src.services.knowledge_graph._ONTOLOGY_PATH", ontology_file):
        svc = KnowledgeGraphService.__new__(KnowledgeGraphService)
        svc._repo = MagicMock()
        svc._openai_api_key = "test-key"
        svc._openai_model = "gpt-4o-mini"
        svc._ontology = ontology_file.read_text()
        return svc
```

| Test case | Setup | Expected |
|-----------|-------|----------|
| `_parse_llm_output` valid JSON with both keys | `'{"nodes": [], "relationships": []}'` | Returns dict with both keys |
| `_parse_llm_output` missing `relationships` key | `'{"nodes": []}'` | Returns dict with `relationships: []` via `setdefault` |
| `_parse_llm_output` invalid JSON | `"not json"` | Raises `AppException(status_code=500)` |
| `_parse_llm_output` JSON array instead of object | `"[]"` | Raises `AppException(status_code=500)` |
| `_validate` unknown node label | node `{"label": "Unknown", "properties": {}}` | `nodes_dropped=1`; `valid_nodes` is empty |
| `_validate` missing required field | Deal node missing `deal_id` | `nodes_dropped=1` |
| `_validate` invalid enum value | Deal with `"status": "Pending"` | `nodes_dropped=1` |
| `_validate` valid node passes through | Deal with all required fields, valid status | `nodes_dropped=0`; node in returned `valid_nodes` |
| `_validate` invalid relationship triple | `("Deal", "INVALID", "Account")` | `relationships_dropped=1` |
| `_validate` relationship missing `from_value` | rel dict without `from_value` key | `relationships_dropped=1` |
| `_validate` valid relationship passes through | `("Deal", "FOR_ACCOUNT", "Account")` with all fields | `relationships_dropped=0` |
| `_write_nodes` node created | `_repo.merge_node` returns `True` | `result.nodes_created=1`, `result.nodes_merged=0` |
| `_write_nodes` node merged | `_repo.merge_node` returns `False` | `result.nodes_merged=1`, `result.nodes_created=0` |
| `_write_nodes` Neo4j error | `_repo.merge_node` raises `Exception("connection refused")` | Raises `AppException(status_code=500)` |
| `_write_relationships` rel skipped (exists) | `_repo.relationship_exists` returns `True` | `result.relationships_skipped=1`; `create_relationship` not called |
| `_write_relationships` rel created | `_repo.relationship_exists` returns `False` | `_repo.create_relationship` called once; `result.relationships_created=1` |
| `_write_relationships` check error | `_repo.relationship_exists` raises `Exception` | Raises `AppException(status_code=500)` |
| `_write_relationships` create error | `_repo.create_relationship` raises `Exception` | Raises `AppException(status_code=500)` |
| `process_document` happy path | LLM returns JSON with 2 valid nodes, 1 valid rel; `merge_node` returns True; `relationship_exists` returns False | Returns `KGIngestResult(nodes_created=2, relationships_created=1)` |
| `process_document` text truncation | `extracted_text` is 60 000 chars | LLM called with text of exactly `MAX_EXTRACTION_CHARS` chars |
| `process_document` LLM failure | `_call_llm` raises `Exception("rate limit")` | Exception propagates unchanged to caller |

**Patching guidance:**
- Patch `src.services.knowledge_graph.KnowledgeGraphRepository` to inject a `MagicMock`.
- Patch the OpenAI client at `src.services.knowledge_graph.OpenAI` when testing `_call_llm`.
- Do not mock `_validate` — test the real validator against `_VALID_RELATIONSHIPS`, `_REQUIRED_FIELDS`, and `_ENUM_CONSTRAINTS`.
- For `process_document` tests, stub `_call_llm` on the service instance directly (`svc._call_llm = MagicMock(return_value=...)`) to avoid Anthropic SDK import requirements.

---

## 10. Error Handling Summary

| Failure point | Exception raised by | Caught by | Behavior |
|---|---|---|---|
| `OPENAI_API_KEY` missing | `os.environ["OPENAI_API_KEY"]` | propagates to startup | `KeyError` at `KnowledgeGraphService.__init__` — app fails to start |
| `NEO4J_PASSWORD` missing | `os.environ["NEO4J_PASSWORD"]` | propagates to startup | `KeyError` at `src/main.py` — app fails to start |
| `Neo4jConnection` not initialized | `Neo4jConnection.get_driver()` | propagates through `_driver` property | `AppException(500)` — propagates to upload handler |
| LLM returns invalid JSON | `json.loads` | `_parse_llm_output` | `AppException("KG extraction failed", 500)` |
| OpenAI API error | `openai.OpenAIError` | not caught in service | propagates to PDF handler (logged + suppressed) or tabular handler (HTTP 500) |
| Node fails validation | (no exception) | `_validate` | `nodes_dropped += 1`; warning logged; upload continues with remaining valid nodes |
| Relationship fails validation | (no exception) | `_validate` | `relationships_dropped += 1`; warning logged; upload continues |
| Neo4j MERGE failure | `neo4j.exceptions.Neo4jError` | `_write_nodes` / `_write_relationships` | `AppException("KG write failed", 500)` |
| KG failure during PDF upload | Any `Exception` from `kg_future.result()` | `process_upload` PDF branch | Logged as `logger.warning`; vector store result is still returned; upload count increments |
| KG failure during CSV/XLS/XLSX upload | `AppException(500)` from `process_document` | global handler in `main.py` | HTTP 500 `{"success": false, "error": "KG write failed"}` |

---

## 11. Distinction from Vector Store Pipeline

| Aspect | PDF vector store (spec `07`) | CSV tabular (spec `08`) | KG pipeline (this spec) |
|--------|------------------------------|-------------------------|-------------------------|
| Output store | ChromaDB (in-memory) | ChromaDB (in-memory) | Neo4j |
| Trigger | PDF only | CSV/XLS/XLSX only | All file types |
| PDF behavior | Primary path | — | Parallel with vector store; failure suppressed |
| CSV behavior | — | Primary path (removed by this spec) | Replaces tabular chunking |
| Failure behavior | Propagates (fails upload) | Propagates (fails upload) | PDF: suppressed; CSV: propagates |
| Content shape | Unstructured text chunks | Unstructured row text chunks | Structured nodes + relationships |
| Deduplication | UUID-based (no dedup) | UUID-based (no dedup) | Neo4j MERGE (idempotent) |

---

## 12. Out of Scope

- Querying the knowledge graph (future graph query / RAG story).
- Neo4j index and constraint creation — managed by a separate DB migration script, not `main.py`.
- Chunking large documents before LLM extraction — text is truncated to `MAX_EXTRACTION_CHARS` (50 000 chars); full-document extraction over very large files is a future enhancement.
- LLM retry logic — Anthropic API errors propagate immediately without retry.
- Async / concurrent Neo4j writes — nodes and relationships are written sequentially within `process_document`.
- Rollback on partial failure — nodes already merged to Neo4j are not removed if a later write fails. This is an acceptable MVP trade-off.
- User-scoped graph isolation — all nodes are shared across users (global knowledge graph).
- Deleting graph nodes when a document is deleted or re-uploaded.
- Graph API endpoints or visualization.
- LLM model selection beyond `OPENAI_MODEL` env var — all OpenAI chat completion models are supported.
