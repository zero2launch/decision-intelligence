# Spec: Knowledge Graph Retrieval Pipeline (`graph_search` tool)

**ID:** `12-retrieval-workflow-kg`
**Status:** Ready for implementation
**Depends on:** `11-retrieval-workflow-1` (LangGraph agent graph must exist), `09-kg-pipeline` (Neo4j connection and `KnowledgeGraphRepository` must exist)

---

## 1. Context

The `graph_search` tool in `src/agents/tools.py` currently returns a placeholder string. This spec replaces the placeholder with a real 10-step pipeline that translates a natural-language question into a Cypher query, executes it against Neo4j, and returns a natural-language answer.

All pipeline logic lives in a new helper module `src/agents/kg_pipeline.py`. The `graph_search` tool in `tools.py` becomes a thin wrapper that calls into it. This respects the single-responsibility principle and keeps `tools.py` from growing into an unstructured monolith.

---

## 2. Pipeline Overview

```
graph_search(query)
    │
    ▼
1. load_ontology()                ← reads ontology/ontology_context.md
    │
    ▼
2. LLM Semantic Parser            ← LLM(question + ontology) → DSL JSON
    │
    ▼
3. validate_dsl(dsl, schema)      ← checks every label, rel, property against ontology
    │
    ▼
4. build_ast(dsl)                 ← DSL → QueryAST dataclass
    │
    ▼
5. compile_cypher(ast)            ← QueryAST → (cypher_str, params_dict)
    │
    ▼
6. KnowledgeGraphRepository.run_query(cypher, params)  ← Neo4j read query
    │
    ▼
7. serialise_records(records)     ← list[dict] → JSON/text summary string
    │
    ▼
8. LLM Answer Generator           ← LLM(question + raw_result) → natural-language answer
    │
    ▼
9. return answer str              ← consumed by Answer Synthesis Agent
```

---

## 3. Files to Create / Modify

```
src/
  agents/
    tools.py           ← modify: replace graph_search body; import kg_pipeline
    kg_pipeline.py     ← new: all pipeline step functions + QueryAST dataclass

  repository/
    knowledge_graph.py ← modify: add run_query(cypher, params) method

ontology/
  ontology_context.md  ← read-only at runtime; no changes

tests/
  unit/
    test_kg_pipeline.py        ← new: unit tests for all pipeline steps
```

---

## 4. Environment Variables

| Variable | Used by | Notes |
|----------|---------|-------|
| `OPENAI_API_KEY` | `ChatOpenAI` in `kg_pipeline.py` | Must be present; no default |
| `OPENAI_MODEL` | `ChatOpenAI` in `kg_pipeline.py` | Defaults to `"gpt-4o-mini"` if not set |

Read via `os.environ.get()` at module level in `kg_pipeline.py`, same pattern as `agents.py`.

---

## 5. Data Structures

### 5.1 DSL JSON (LLM output)

The LLM is instructed to output a JSON object — never raw Cypher. Structure:

```json
{
  "match": [
    {"label": "Deal", "alias": "d"}
  ],
  "traversals": [
    {"rel": "MANAGED_BY", "to_label": "SalesRep", "to_alias": "s"}
  ],
  "where": [
    {"field": "d.status", "op": "=", "value": "Won"}
  ],
  "return": ["d.name", "d.value", "s.name"]
}
```

| Field | Type | Description |
|---|---|---|
| `match` | `list[dict]` | Primary node(s) to anchor the query. Each entry has `label` and `alias`. The first entry is always the anchor node. |
| `traversals` | `list[dict]` | Relationship hops from anchor. Each has `rel`, `to_label`, `to_alias`. |
| `where` | `list[dict]` | Filter conditions. Each has `field` (e.g. `"d.status"`), `op` (`"="`, `">"`, `"<"`, `">="`), and `value`. |
| `return` | `list[str]` | Dot-notation fields to return (e.g. `"d.name"`). |

**Rules:**
- `match` always has at least one entry.
- `traversals` may be empty (single-node query).
- `where` may be empty (no filters).
- `return` always has at least one entry.
- `op` values are restricted to `"="`, `">"`, `"<"`, `">="`, `"<="`.

---

### 5.2 QueryAST Dataclass

```python
from dataclasses import dataclass, field

@dataclass
class QueryAST:
    anchor_label: str
    anchor_alias: str
    traversals: list[dict]   # each: {"rel": str, "to_label": str, "to_alias": str}
    filters: list[dict]      # each: {"field": str, "op": str, "value": any}
    return_fields: list[str]
```

Built from the validated DSL by `build_ast()`.

---

### 5.3 Ontology Schema Dict

Parsed from `ontology/ontology_context.md` by `load_ontology()` and returned as:

```python
{
  "labels": {"Deal", "Quarter", "Industry", "Region", "ServiceOffering",
             "Technology", "Account", "SalesRep", "PipelineStage",
             "LossReason", "Project", "DeliveryIssue", "Skill", "Employee"},
  "relationships": {"IN_QUARTER", "IN_INDUSTRY", "IN_REGION", "USES_SERVICE",
                    "USES_TECHNOLOGY", "FOR_ACCOUNT", "MANAGED_BY", "AT_STAGE",
                    "LOST_DUE_TO", "REQUIRES_SKILL", "EXECUTES", "HAS_ISSUE",
                    "HAS_SKILL", "WORKS_ON"},
  "properties": {
    "Deal": {"deal_id", "name", "value", "status"},
    "Quarter": {"name", "year", "quarter", "total_revenue", "expected_revenue", "win_rate"},
    "Industry": {"name", "sector"},
    "Region": {"name", "countries"},
    "ServiceOffering": {"name", "category"},
    "Technology": {"name", "category", "type"},
    "Account": {"name", "tier", "annual_revenue"},
    "SalesRep": {"name", "region", "quota", "deals_won", "deals_lost", "performance_score"},
    "PipelineStage": {"name", "order", "avg_conversion_rate", "avg_days_in_stage"},
    "LossReason": {"name", "category", "frequency"},
    "Project": {"project_id", "name", "status", "budget", "actual_cost",
                "is_delayed", "is_over_budget", "delay_days"},
    "DeliveryIssue": {"name", "category", "severity", "description"},
    "Skill": {"name", "category"},
    "Employee": {"employee_id", "name", "role", "level", "department"},
  }
}
```

---

## 6. Layer Specifications

---

### 6.1 `src/agents/kg_pipeline.py` — Pipeline Helper Module

```python
import os
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from langchain_openai import ChatOpenAI
from src.repository.knowledge_graph import KnowledgeGraphRepository
from src.utils.exception import AppException

logger = logging.getLogger(__name__)

_llm = ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
_repo = KnowledgeGraphRepository()
_ONTOLOGY_PATH = Path(__file__).parent.parent.parent / "ontology" / "ontology_context.md"


@dataclass
class QueryAST:
    anchor_label: str
    anchor_alias: str
    traversals: list[dict]
    filters: list[dict]
    return_fields: list[str]


def load_ontology() -> tuple[str, dict]:
    """Read ontology file; return (raw_text, schema_dict)."""
    ...


def parse_dsl(question: str, ontology_text: str) -> dict:
    """Call LLM with question + ontology; parse JSON response into DSL dict."""
    ...


def validate_dsl(dsl: dict, schema: dict) -> None:
    """Validate DSL labels, rels, and properties against schema.
    Raises AppException(400) on first unknown term."""
    ...


def build_ast(dsl: dict) -> QueryAST:
    """Convert validated DSL dict into a QueryAST dataclass."""
    ...


def compile_cypher(ast: QueryAST) -> tuple[str, dict]:
    """Walk AST; emit parameterised Cypher string and params dict.
    No user-value string interpolation."""
    ...


def serialise_records(records: list[dict]) -> str:
    """Convert raw Neo4j records list to a compact JSON/text string."""
    ...


def generate_answer(question: str, raw_result: str) -> str:
    """Call LLM with question + raw_result; return natural-language answer."""
    ...


def run_graph_search(question: str) -> str:
    """Orchestrate all steps. Return final answer string."""
    ...
```

**Rules:**
- `_llm` and `_repo` are module-level singletons — instantiated once at import time.
- `load_ontology()` reads `_ONTOLOGY_PATH` on every call (not cached) so hot-reload works in dev.
- `parse_dsl()` instructs the LLM to respond with **only** a JSON object — no prose. Parse with `json.loads()`. If parsing fails, raise `AppException("Failed to parse LLM DSL output", 500)`.
- `validate_dsl()` checks:
  - Every `label` in `dsl["match"]` exists in `schema["labels"]`.
  - Every `to_label` in `dsl["traversals"]` exists in `schema["labels"]`.
  - Every `rel` in `dsl["traversals"]` exists in `schema["relationships"]`.
  - For each filter in `dsl["where"]`, split `field` on `"."` to get `(alias, prop)`. Resolve `alias` to a label via the `match` + `traversals` entries. Check `prop` in `schema["properties"][label]`.
- `compile_cypher()` generates parameter keys `p0`, `p1`, … (one per filter value). Never interpolate user-supplied values into the Cypher string.
- `serialise_records()` returns `"No results found."` if `records` is empty.
- `generate_answer()` passes the raw result string in the prompt and asks the LLM to produce a concise answer. If the raw result is `"No results found."`, the answer should reflect that.
- `run_graph_search()` calls the steps in order and returns the answer string. Any `AppException` from sub-steps propagates unchanged. Any other exception is caught, logged at `error` level, and re-raised as `AppException("Knowledge graph query failed", 500)`.

---

### 6.2 `src/agents/tools.py` — Modified `graph_search` tool

```python
from langchain_core.tools import tool
from src.agents.kg_pipeline import run_graph_search


@tool
def vector_search(query: str) -> str:
    """Search the vector database for semantically similar content."""
    return f"Vector Result for: {query}"


@tool
def graph_search(query: str) -> str:
    """Search the knowledge graph for structured entity relationships."""
    return run_graph_search(query)
```

**Rules:**
- `graph_search` docstring must remain present and descriptive — it is used as the LangChain tool description.
- The `@tool` decorator must be retained.
- `run_graph_search` is the single entry point — `tools.py` contains no pipeline logic directly.
- `vector_search` is unchanged.

---

### 6.3 `src/repository/knowledge_graph.py` — Add `run_query`

Add this method to `KnowledgeGraphRepository`:

```python
def run_query(self, cypher: str, params: dict) -> list[dict]:
    """Execute a read query and return all records as plain dicts."""
    logger.info(f"Running read query: {cypher[:120]}")
    with Neo4jConnection.get_session() as session:
        result = session.run(cypher, **params)
        return [record.data() for record in result]
```

**Rules:**
- Use `record.data()` to convert each Neo4j `Record` to a plain `dict`.
- Pass `params` as keyword arguments (`**params`) — driver unpacks them.
- Returns an empty list if the query returns no records.
- Follows the same `@property _driver` / `Neo4jConnection.get_session()` pattern as existing methods.
- Log at `logger.info` on entry with the first 120 chars of the Cypher.

---

## 7. Cypher Compilation Rules

Given this AST:
```python
QueryAST(
    anchor_label="Deal", anchor_alias="d",
    traversals=[{"rel": "MANAGED_BY", "to_label": "SalesRep", "to_alias": "s"}],
    filters=[{"field": "d.status", "op": "=", "value": "Won"},
             {"field": "d.value", "op": ">", "value": 50000}],
    return_fields=["d.name", "d.value", "s.name"]
)
```

The compiler emits:

```cypher
MATCH (d:Deal)-[:MANAGED_BY]->(s:SalesRep)
WHERE d.status = $p0 AND d.value > $p1
RETURN d.name, d.value, s.name
```

```python
params = {"p0": "Won", "p1": 50000}
```

Rules:
- No traversals → `MATCH (alias:Label)` (single node, no relationship pattern).
- No filters → omit `WHERE` clause entirely.
- Multiple traversals chain: `(d:Deal)-[:REL1]->(a:Node1)-[:REL2]->(b:Node2)`.
- Multiple filters join with `AND`.
- All user-supplied filter values go into `params` — never interpolated into the string.

---

## 8. LLM Prompt Templates

### 8.1 Semantic Parser Prompt

```
You are a graph query DSL generator. Given a natural language question and a Neo4j schema ontology, 
output ONLY a valid JSON object (no markdown, no explanation) describing the query using the ontology terms.

## Ontology
{ontology_text}

## Question
{question}

## Output Format
Return a single JSON object with these keys:
- "match": list of {{"label": str, "alias": str}} — the primary node(s) to query
- "traversals": list of {{"rel": str, "to_label": str, "to_alias": str}} — relationship traversals
- "where": list of {{"field": str, "op": str, "value": any}} — filter conditions (op: =, >, <, >=, <=)
- "return": list of str — dot-notation fields to return (e.g. "d.name")

Use only labels, relationship types, and properties that exist in the ontology above.
```

### 8.2 Answer Generation Prompt

```
You are an expert business analyst. Answer the user's question using only the data provided.

## Question
{question}

## Data from Knowledge Graph
{raw_result}

Provide a concise, accurate answer. If no data was returned, state that clearly.
```

---

## 9. Unit Test Plan — `tests/unit/test_kg_pipeline.py`

All LLM calls are mocked via `unittest.mock.patch`. All Neo4j calls are mocked via `MagicMock`. Tests are grouped by pipeline step using the prefixes below.

```python
import os
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")

import pytest
import json
from unittest.mock import MagicMock, patch, mock_open
from src.agents.kg_pipeline import (
    load_ontology, parse_dsl, validate_dsl, build_ast,
    compile_cypher, serialise_records, generate_answer,
    run_graph_search, QueryAST,
)
from src.utils.exception import AppException
```

---

### Fixtures

```python
@pytest.fixture()
def sample_schema():
    return {
        "labels": {"Deal", "SalesRep", "Account", "Quarter"},
        "relationships": {"MANAGED_BY", "FOR_ACCOUNT", "IN_QUARTER"},
        "properties": {
            "Deal": {"deal_id", "name", "value", "status"},
            "SalesRep": {"name", "region", "quota", "performance_score"},
            "Account": {"name", "tier", "annual_revenue"},
            "Quarter": {"name", "year", "quarter", "total_revenue"},
        }
    }


@pytest.fixture()
def simple_dsl():
    return {
        "match": [{"label": "Deal", "alias": "d"}],
        "traversals": [{"rel": "MANAGED_BY", "to_label": "SalesRep", "to_alias": "s"}],
        "where": [{"field": "d.status", "op": "=", "value": "Won"}],
        "return": ["d.name", "d.value", "s.name"],
    }


@pytest.fixture()
def simple_ast():
    return QueryAST(
        anchor_label="Deal",
        anchor_alias="d",
        traversals=[{"rel": "MANAGED_BY", "to_label": "SalesRep", "to_alias": "s"}],
        filters=[{"field": "d.status", "op": "=", "value": "Won"}],
        return_fields=["d.name", "d.value", "s.name"],
    )
```

---

### OL — Ontology Loading (`load_ontology`)

| ID | Test | Assertion |
|----|------|-----------|
| OL-01 | Returns a tuple of (str, dict) | `type(text) == str` and `type(schema) == dict` |
| OL-02 | Text is non-empty | `len(text) > 0` |
| OL-03 | Schema has `labels` key | `"labels" in schema` |
| OL-04 | Schema has `relationships` key | `"relationships" in schema` |
| OL-05 | Schema has `properties` key | `"properties" in schema` |
| OL-06 | `labels` contains known node labels | `"Deal" in schema["labels"]` and `"SalesRep" in schema["labels"]` and `"Employee" in schema["labels"]` |
| OL-07 | `relationships` contains known rel types | `"MANAGED_BY" in schema["relationships"]` and `"HAS_SKILL" in schema["relationships"]` |
| OL-08 | `properties["Deal"]` contains all Deal fields | `{"deal_id", "name", "value", "status"}.issubset(schema["properties"]["Deal"])` |
| OL-09 | `properties["SalesRep"]` contains SalesRep fields | `{"name", "region", "quota"}.issubset(schema["properties"]["SalesRep"])` |
| OL-10 | Missing ontology file raises AppException 500 | Mock `Path.open` to raise `FileNotFoundError`; expect `AppException` with `status_code=500` |

---

### SP — Semantic Parser (`parse_dsl`)

Mock `src.agents.kg_pipeline._llm`.

| ID | Test | LLM mock response | Assertion |
|----|------|-------------------|-----------|
| SP-01 | Returns a dict on valid JSON response | `json.dumps({"match": [...], ...})` | `isinstance(result, dict)` |
| SP-02 | Returns dict with all required DSL keys | Valid JSON DSL | `result` has keys `"match"`, `"traversals"`, `"where"`, `"return"` |
| SP-03 | Passes question in LLM prompt | LLM returns valid DSL JSON | Call arg to `_llm.invoke` contains the question string |
| SP-04 | Passes ontology text in LLM prompt | LLM returns valid DSL JSON | Call arg to `_llm.invoke` contains a substring from the ontology text |
| SP-05 | LLM returning invalid JSON raises AppException 500 | `"not valid json {{{"` | `AppException` raised with `status_code=500` |
| SP-06 | LLM returning non-dict JSON raises AppException 500 | `"[1, 2, 3]"` | `AppException` raised with `status_code=500` |
| SP-07 | LLM is called exactly once per invocation | Valid DSL JSON | `_llm.invoke.call_count == 1` |

---

### OV — Ontology Validator (`validate_dsl`)

| ID | Test | Input | Assertion |
|----|------|-------|-----------|
| OV-01 | Valid DSL passes without error | `simple_dsl`, `sample_schema` | No exception raised |
| OV-02 | Unknown node label raises AppException 400 | `dsl["match"] = [{"label": "Unknown", "alias": "x"}]` | `AppException` with `status_code=400`; message mentions `"Unknown"` |
| OV-03 | Unknown traversal `to_label` raises AppException 400 | `dsl["traversals"] = [{"rel": "MANAGED_BY", "to_label": "Ghost", "to_alias": "g"}]` | `AppException` with `status_code=400`; message mentions `"Ghost"` |
| OV-04 | Unknown relationship type raises AppException 400 | `dsl["traversals"] = [{"rel": "FAKE_REL", "to_label": "SalesRep", "to_alias": "s"}]` | `AppException` with `status_code=400`; message mentions `"FAKE_REL"` |
| OV-05 | Unknown property in where filter raises AppException 400 | `dsl["where"] = [{"field": "d.phantom", "op": "=", "value": "x"}]` | `AppException` with `status_code=400`; message mentions `"phantom"` |
| OV-06 | Empty traversals is valid | `dsl["traversals"] = []` | No exception raised |
| OV-07 | Empty where is valid | `dsl["where"] = []` | No exception raised |
| OV-08 | Multiple traversals all valid | Two valid traversal entries | No exception raised |
| OV-09 | First invalid term triggers error, stops early | Multiple invalid labels | Only one `AppException` raised (not multiple) |
| OV-10 | Property validation uses alias-to-label mapping from traversals | Filter on traversal node alias (`s.name`) | No exception when property belongs to the traversal's `to_label` |

---

### QP — Query Planner / AST Builder (`build_ast`)

| ID | Test | Input | Assertion |
|----|------|-------|-----------|
| QP-01 | Returns a `QueryAST` instance | `simple_dsl` | `isinstance(result, QueryAST)` |
| QP-02 | Anchor label set from first match entry | `simple_dsl` | `result.anchor_label == "Deal"` |
| QP-03 | Anchor alias set from first match entry | `simple_dsl` | `result.anchor_alias == "d"` |
| QP-04 | Traversals list matches DSL traversals | `simple_dsl` | `len(result.traversals) == 1` and `result.traversals[0]["rel"] == "MANAGED_BY"` |
| QP-05 | Filters list matches DSL where clause | `simple_dsl` | `len(result.filters) == 1` and `result.filters[0]["value"] == "Won"` |
| QP-06 | Return fields list matches DSL return | `simple_dsl` | `result.return_fields == ["d.name", "d.value", "s.name"]` |
| QP-07 | Empty traversals produces empty list | `dsl["traversals"] = []` | `result.traversals == []` |
| QP-08 | Empty where produces empty filters list | `dsl["where"] = []` | `result.filters == []` |
| QP-09 | Multiple traversals all captured | DSL with 2 traversals | `len(result.traversals) == 2` |

---

### CC — Cypher Compiler (`compile_cypher`)

| ID | Test | Input | Expected Cypher fragment / params |
|----|------|-------|-----------------------------------|
| CC-01 | Returns a tuple of (str, dict) | `simple_ast` | `isinstance(cypher, str)` and `isinstance(params, dict)` |
| CC-02 | MATCH clause includes anchor node | `simple_ast` | `"MATCH (d:Deal)"` in cypher |
| CC-03 | MATCH clause includes relationship pattern | `simple_ast` | `"[:MANAGED_BY]"` in cypher and `"(s:SalesRep)"` in cypher |
| CC-04 | WHERE clause present when filters exist | `simple_ast` | `"WHERE"` in cypher |
| CC-05 | WHERE clause absent when no filters | AST with empty `filters` | `"WHERE"` not in cypher |
| CC-06 | Filter value is parameterised (not interpolated) | `simple_ast` (filter value `"Won"`) | `"$p0"` in cypher; `params["p0"] == "Won"` |
| CC-07 | Multiple filters use sequential param keys | AST with 2 filters | `"$p0"` and `"$p1"` in cypher; both keys in `params` |
| CC-08 | RETURN clause includes all return fields | `simple_ast` | `"RETURN d.name, d.value, s.name"` in cypher |
| CC-09 | No traversals produces single-node MATCH | AST with `traversals=[]` | `"MATCH (d:Deal)"` in cypher; no `-[` in cypher |
| CC-10 | Filter operator `>` used correctly | AST filter `{"field": "d.value", "op": ">", "value": 50000}` | `"d.value > $p0"` in cypher |
| CC-11 | User value never appears literally in cypher string | Filter with `value="Won"` | `"Won"` not in cypher string (only in `params`) |

---

### RQ — Repository `run_query`

Mock `Neo4jConnection.get_session`.

| ID | Test | Neo4j mock setup | Assertion |
|----|------|-----------------|-----------|
| RQ-01 | Returns a list | Session returns 2 records | `isinstance(result, list)` |
| RQ-02 | Each item is a dict | Session returns 2 records with `.data()` → `{"name": "Alice"}` | `all(isinstance(r, dict) for r in result)` |
| RQ-03 | Returns all records | Session returns 3 records | `len(result) == 3` |
| RQ-04 | Returns empty list when no records | Session returns 0 records | `result == []` |
| RQ-05 | Passes cypher string to `session.run` | Any mock records | `session.run.assert_called_once_with(cypher, **params)` |
| RQ-06 | Passes params as kwargs to `session.run` | Params `{"p0": "Won"}` | `session.run` called with `p0="Won"` |
| RQ-07 | Uses context manager (session via `with` block) | — | `get_session().__enter__` called |

---

### GA — Answer Generator (`generate_answer`)

Mock `src.agents.kg_pipeline._llm`.

| ID | Test | LLM mock content | Assertion |
|----|------|-----------------|-----------|
| GA-01 | Returns a non-empty string | `"The top rep is Alice."` | `result == "The top rep is Alice."` |
| GA-02 | Question appears in LLM prompt | LLM returns any content | Call arg contains the question string |
| GA-03 | Raw result appears in LLM prompt | `raw_result="...records..."`, LLM returns content | Call arg contains `"...records..."` |
| GA-04 | LLM called exactly once | LLM returns content | `_llm.invoke.call_count == 1` |
| GA-05 | Empty raw result passes through without error | `raw_result="No results found."` | No exception; LLM called once |

---

### SR — Serialise Records (`serialise_records`)

| ID | Test | Input | Assertion |
|----|------|-------|-----------|
| SR-01 | Non-empty records returns a non-empty string | `[{"name": "Alice", "value": 100}]` | `isinstance(result, str)` and `len(result) > 0` |
| SR-02 | Empty list returns "No results found." | `[]` | `result == "No results found."` |
| SR-03 | Result contains record data | `[{"name": "Alice"}]` | `"Alice"` in result |
| SR-04 | Multiple records all represented | `[{"name": "Alice"}, {"name": "Bob"}]` | Both `"Alice"` and `"Bob"` in result |

---

### GS — Graph Search End-to-End (`run_graph_search`)

Mock all sub-steps: `load_ontology`, `parse_dsl`, `validate_dsl`, `build_ast`, `compile_cypher`, `_repo.run_query`, `serialise_records`, `generate_answer`.

| ID | Test | Setup | Assertion |
|----|------|-------|-----------|
| GS-01 | Returns the answer string from `generate_answer` | All mocks succeed; `generate_answer` returns `"Alice led Won deals."` | `result == "Alice led Won deals."` |
| GS-02 | `load_ontology` is called once | All mocks succeed | `load_ontology` called once |
| GS-03 | `parse_dsl` receives question and ontology text | All mocks succeed | `parse_dsl` called with (question, ontology_text) |
| GS-04 | `validate_dsl` is called with DSL and schema | All mocks succeed | `validate_dsl` called with (dsl, schema) |
| GS-05 | `build_ast` is called with validated DSL | All mocks succeed | `build_ast` called with the DSL dict |
| GS-06 | `compile_cypher` is called with AST | All mocks succeed | `compile_cypher` called with the AST |
| GS-07 | `run_query` is called with cypher and params | All mocks succeed | `_repo.run_query` called with (cypher, params) |
| GS-08 | `generate_answer` receives question and serialised result | All mocks succeed | `generate_answer` called with (question, serialised_str) |
| GS-09 | AppException from `validate_dsl` propagates unchanged | `validate_dsl` raises `AppException(400)` | `AppException` with `status_code=400` raised from `run_graph_search` |
| GS-10 | AppException from `parse_dsl` propagates unchanged | `parse_dsl` raises `AppException(500)` | `AppException` with `status_code=500` raised |
| GS-11 | Unexpected exception becomes AppException 500 | `_repo.run_query` raises `RuntimeError("neo4j down")` | `AppException` with `status_code=500` raised |
| GS-12 | Empty Neo4j result returns descriptive answer | `run_query` returns `[]`; `serialise_records` returns `"No results found."` | `generate_answer` called with `"No results found."` in raw_result arg |

---

## 10. Error Handling Summary

| Failure point | Raised by | Behaviour |
|---|---|---|
| Ontology file not found | `load_ontology` | `AppException("Ontology file not found", 500)` |
| LLM returns non-JSON | `parse_dsl` | `AppException("Failed to parse LLM DSL output", 500)` |
| Unknown ontology term in DSL | `validate_dsl` | `AppException("Unknown <label/rel/property>: <term>", 400)` |
| Any unexpected exception in pipeline | `run_graph_search` | Caught, logged at `error`, re-raised as `AppException("Knowledge graph query failed", 500)` |
| No Neo4j records | `serialise_records` | Returns `"No results found."` — not an error; LLM generates an appropriate empty-result answer |

---

## 11. What Not To Do

- Do not write raw Cypher strings anywhere in the LLM prompt or DSL output — the DSL is an intermediate representation.
- Do not interpolate user-supplied filter values into the Cypher string — always parameterise them.
- Do not call `MongoDBConnection` or any MongoDB repository from `kg_pipeline.py`.
- Do not store `Neo4jConnection.get_session()` result as an instance variable in the repository.
- Do not catch `AppException` in `run_graph_search` and wrap it in another `AppException`.
- Do not add try/except in `graph_search` in `tools.py` — errors propagate to `kg_agent` and then to `ChatService.ask`, which handles them.
- Do not cache the ontology as a module-level variable — read it fresh on each call to support hot-reload during development.
- Do not use `print()` anywhere — use `logger`.
- Do not skip `@tool` decorator on `graph_search`.
- Do not expose raw Neo4j `Record` objects outside the repository — always call `.data()`.
