# Spec: LangGraph Multi-Agent Orchestration Framework + POST /api/chat

**ID:** `11-retrieval-workflow-1`
**Status:** Ready for implementation
**Depends on:** `04-login-api` (JWT token generation and `AuthUtils.decode_access_token` must exist)

---

## 1. Context

The application requires a multi-agent orchestration layer to intelligently route user questions to the appropriate retrieval agents (vector search or knowledge graph) or answer them directly. This spec introduces:

1. A LangGraph-based multi-agent workflow (`src/agents/`) that routes questions, supports parallel execution, and maintains per-user conversation state via checkpointing.
2. A `POST /api/chat` HTTP endpoint that accepts a user question, invokes the workflow, and returns the synthesized answer. Auth follows the same JWT Bearer pattern used by `/api/upload`.

Vector database retrieval and Knowledge Graph query logic are **out of scope** for this story and will be implemented separately. Placeholder tool interfaces are wired in their place.

---

## 2. Workflow Overview

```
POST /api/chat
    │
    ▼
chat_router  →  ChatService.ask(question, username)
                    │
                    ▼
             graph.invoke({"question": question}, config={"configurable": {"thread_id": username}})
                    │
                    ▼
             Planner Agent        (routes to: "vector" | "kg" | "both" | "direct")
                    │
                    ├── "vector" ──────────────────────────────► Vector Agent
                    │                                                  │
                    ├── "kg" ────────────────────────────────────► KG Agent
                    │                                                  │
                    ├── "both" ──► Vector Agent ──┬────────────► Answer Agent ──► answer
                    │              KG Agent ───────┘
                    │
                    └── "direct" ────────────────────────────────► Direct Agent ──► answer
                    │
                    ▼
             ChatResponse(answer=...)
```

Each `username` maps to an isolated `thread_id` in LangGraph's checkpointer, maintaining a separate conversation state per user.

---

## 3. Endpoint Contract

### Request

```
POST /api/chat
Content-Type: application/json
Authorization: Bearer <jwt-token>
```

```json
{
  "question": "Who bought Samsung products and what is their warranty?"
}
```

| Field      | Type   | Constraints               |
|------------|--------|---------------------------|
| `question` | string | required, min length 1    |

### Success Response — `200 OK`

```json
{
  "answer": "Based on the retrieved data, the following customers purchased Samsung products..."
}
```

| Field    | Type   | Description                                |
|----------|--------|--------------------------------------------|
| `answer` | string | Synthesized answer from the agent workflow |

### Error Responses

| Scenario                       | Status | Body                                                              |
|--------------------------------|--------|-------------------------------------------------------------------|
| Missing or invalid token       | 401    | `{ "success": false, "error": "Invalid or expired token" }`      |
| Validation failure (bad input) | 422    | FastAPI default (Pydantic validation error with `detail` list)    |
| Workflow execution failure     | 500    | `{ "success": false, "error": "Chat workflow failed" }`          |

---

## 4. Files to Create / Modify

```
src/
  agents/
    __init__.py                   ← new: empty
    state.py                      ← new: AgentState TypedDict
    tools.py                      ← new: placeholder @tool functions
    agents.py                     ← new: agent node functions + llm instance
    graph.py                      ← new: StateGraph, routing, checkpointing
  schemas/
    chat.py                       ← new: ChatRequest, ChatResponse
  services/
    chat.py                       ← new: ChatService
  api/
    chat.py                       ← new: chat_router (POST /api/chat)
  main.py                         ← modify: include chat_router

tests/
  unit/
    test_retrieval_workflow.py    ← new: agent/graph unit tests
    test_chat_service.py          ← new: ChatService unit tests
  e2e/
    test_chat_api.py              ← new: end-to-end API tests
```

---

## 5. Dependencies to Add

```bash
uv add langgraph langchain-openai langchain-core
```

| Package | Purpose |
|---------|---------|
| `langgraph` | StateGraph orchestration, checkpointing, conditional routing |
| `langchain-openai` | `ChatOpenAI` wrapper for LLM calls |
| `langchain-core` | `@tool` decorator, `BaseMessage`, `add_messages` |

---

## 6. Environment Variables

No new variables required. The workflow uses:

| Variable | Used by | Notes |
|----------|---------|-------|
| `OPENAI_API_KEY` | `ChatOpenAI` in `agents.py` | Already required by existing services |
| `OPENAI_MODEL` | `ChatOpenAI` in `agents.py` | Defaults to `"gpt-4o-mini"` if not set |

---

## 7. Layer Specifications

---

### 7.1 `src/agents/state.py` — Shared Workflow State

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    route: str
    vector_result: str
    kg_result: str
    answer: str
```

**Rules:**
- `messages` uses `add_messages` from LangGraph — enables incremental append semantics for conversation memory.
- All fields are declared at TypedDict level; individual agent nodes return only the subset they update.
- `route`, `vector_result`, `kg_result`, and `answer` are plain `str` — no `Optional` needed because LangGraph applies partial updates at runtime.

---

### 7.2 `src/agents/tools.py` — Placeholder Tool Interfaces

```python
from langchain_core.tools import tool


@tool
def vector_search(query: str) -> str:
    """Search the vector database for semantically similar content."""
    return f"Vector Result for: {query}"


@tool
def graph_search(query: str) -> str:
    """Search the knowledge graph for structured entity relationships."""
    return f"Knowledge Graph Result for: {query}"
```

**Rules:**
- Both functions are decorated with `@tool` — exposes `.invoke()`, `.name`, and `.description` used by LangChain tooling.
- Return strings are deterministic placeholders. No I/O, no network calls, no database access.
- Docstrings serve as tool descriptions for LLM tool-calling — they must be present and descriptive.
- Do **not** implement actual vector retrieval or KG query logic here.

---

### 7.3 `src/agents/agents.py` — Agent Node Functions

```python
import os
from langchain_openai import ChatOpenAI
from src.agents.tools import vector_search, graph_search

llm = ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))


def planner(state: dict) -> dict:
    question = state["question"]
    prompt = f"""You are a planner. Given the question below, decide which agent(s) should handle it.

Question: {question}

Return ONLY one word — no explanation, no punctuation:
vector   (use when the question requires semantic document search)
kg       (use when the question requires structured entity/relationship lookup)
both     (use when both vector and knowledge graph search are needed)
direct   (use when the question can be answered without retrieval)
"""
    route = llm.invoke(prompt).content.strip().lower()
    return {"route": route}


def vector_agent(state: dict) -> dict:
    result = vector_search.invoke(state["question"])
    return {"vector_result": result}


def kg_agent(state: dict) -> dict:
    result = graph_search.invoke(state["question"])
    return {"kg_result": result}


def direct_answer(state: dict) -> dict:
    answer = llm.invoke(state["question"]).content
    return {"answer": answer}


def answer_agent(state: dict) -> dict:
    prompt = f"""Answer the following question using the retrieved context below.

Question:
{state["question"]}

Vector Search Results:
{state.get("vector_result", "")}

Knowledge Graph Results:
{state.get("kg_result", "")}

Provide a clear, concise answer based on the context provided.
"""
    answer = llm.invoke(prompt).content
    return {"answer": answer}
```

**Rules:**
- `llm` is a module-level singleton — instantiated once at import time, shared across all agent functions.
- Each agent function returns only the keys it updates; LangGraph merges partial updates into shared state.
- `planner` only sets `"route"`. Never sets `"answer"`, `"vector_result"`, or `"kg_result"`.
- `vector_agent` calls `vector_search.invoke()` — uses the LangChain tool interface, not the raw function.
- `kg_agent` calls `graph_search.invoke()` — same reasoning.
- `direct_answer` invokes the LLM with the raw question — no retrieval context.
- `answer_agent` uses `state.get("vector_result", "")` and `state.get("kg_result", "")` — both optional because only one branch may have run.
- No agent function catches exceptions. Errors propagate to the service layer.
- No `print()` statements.

---

### 7.4 `src/agents/graph.py` — Workflow Graph, Routing, and Checkpointing

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Send

from src.agents.state import AgentState
from src.agents.agents import planner, vector_agent, kg_agent, direct_answer, answer_agent


def router(state: dict):
    route = state["route"]
    if route == "both":
        return [Send("vector", state), Send("kg", state)]
    return route


builder = StateGraph(AgentState)

builder.add_node("planner", planner)
builder.add_node("vector", vector_agent)
builder.add_node("kg", kg_agent)
builder.add_node("answer", answer_agent)
builder.add_node("direct", direct_answer)

builder.set_entry_point("planner")

builder.add_conditional_edges(
    "planner",
    router,
    {
        "vector": "vector",
        "kg": "kg",
        "direct": "direct",
    },
)

builder.add_edge("vector", "answer")
builder.add_edge("kg", "answer")
builder.add_edge("answer", END)
builder.add_edge("direct", END)

memory = MemorySaver()
graph = builder.compile(checkpointer=memory)
```

**Rules:**
- `router` returns a list of `Send` objects for `"both"` to enable parallel fan-out. For all other routes it returns a plain string matching the node name.
- The conditional edges mapping covers `"vector"`, `"kg"`, and `"direct"` only — `"both"` is handled by the `Send` return path, which bypasses the mapping.
- Both `"vector"` and `"kg"` connect to `"answer"` via unconditional edges. LangGraph waits for all parallel branches before proceeding.
- `MemorySaver` is used as the checkpointer — state is persisted in-memory per `thread_id`. Resets on process restart.
- `builder`, `memory`, and `graph` are module-level. `graph` is the compiled object imported by `ChatService`.
- Do not call `setup_logging()` in this module — it is called once in `src/main.py`.

---

### 7.5 `src/schemas/chat.py` — Pydantic Models

```python
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)


class ChatResponse(BaseModel):
    answer: str
```

**Rules:**
- `question` must be at least 1 character — an empty string is rejected at the Pydantic layer (422).
- `ChatResponse` never exposes internal state fields (`route`, `vector_result`, `kg_result`, `messages`).
- Separate request and response models — never reuse `ChatRequest` as the response.

---

### 7.6 `src/services/chat.py` — ChatService

```python
import logging
from src.agents.graph import graph
from src.utils.exception import AppException

logger = logging.getLogger(__name__)


class ChatService:

    def ask(self, question: str, username: str) -> str:
        logger.info(f"Chat request from '{username}': {question[:80]}")
        config = {"configurable": {"thread_id": username}}
        try:
            result = graph.invoke({"question": question}, config=config)
        except Exception as e:
            logger.error(f"Graph invocation failed for '{username}': {e}")
            raise AppException("Chat workflow failed", status_code=500)
        answer = result.get("answer", "")
        if not answer:
            logger.warning(f"Graph returned empty answer for '{username}'")
            raise AppException("Chat workflow failed", status_code=500)
        return answer
```

**Rules:**
- `ChatService` has no `__init__` repository — conversation state is managed by LangGraph's `MemorySaver` in `graph.py`, not MongoDB.
- `thread_id` is always the `username` extracted from the JWT. This gives each user one persistent conversation state. Multiple conversations per user are out of scope.
- The `graph` import is module-level — the compiled graph is a singleton shared across all service calls.
- Any exception from `graph.invoke()` (including LangGraph internal errors, LLM failures, tool failures) is caught and re-raised as `AppException(500)`. The original exception is logged at `error` level before re-raising.
- An empty `"answer"` in the graph result is treated as a failure — raises `AppException(500)`.
- `AppException` raised inside this method is not caught here — it propagates to the router and then to the global exception handler.
- No `print()`. Use `logger.info()`, `logger.warning()`, `logger.error()`.

---

### 7.7 `src/api/chat.py` — chat_router

```python
from fastapi import APIRouter, Header
from src.schemas.chat import ChatRequest, ChatResponse
from src.services.chat import ChatService
from src.utils.auth import AuthUtils
from src.utils.exception import AppException
import logging

chat_router = APIRouter(prefix="/api", tags=["Chat"])
logger = logging.getLogger(__name__)

_service = ChatService()


def _get_current_user(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise AppException("Invalid or expired token", status_code=401)
    token = authorization.removeprefix("Bearer ")
    claims = AuthUtils.decode_access_token(token)
    username = claims.get("sub")
    if not username:
        raise AppException("Invalid or expired token", status_code=401)
    return username


@chat_router.post("/chat", response_model=ChatResponse, status_code=200)
async def chat(payload: ChatRequest, authorization: str = Header(default="")):
    username = _get_current_user(authorization)
    answer = _service.ask(payload.question, username)
    return ChatResponse(answer=answer)
```

**Rules:**
- `_get_current_user` is a plain function — not a FastAPI `Depends`. Called directly in the route body, consistent with how `/api/upload` handles auth.
- No try/except in the router — `AppException` is caught globally by the handler registered in `main.py`.
- `response_model=ChatResponse` is mandatory.
- Route function must be `async`.
- `_service` is instantiated once at module level.
- No `print()`.

---

### 7.8 `src/main.py` — Register chat_router

Add the following import and `include_router` call:

```python
from src.api.chat import chat_router
# ...
app.include_router(chat_router)
```

Place the import after the existing router imports and the `include_router` call after the existing `include_router` calls.

---

## 8. Authentication Flow

```
POST /api/chat  with  Authorization: Bearer <jwt>
    ↓
_get_current_user() strips "Bearer " prefix
    ↓
AuthUtils.decode_access_token(token) → claims dict   [raises AppException(401) on bad/expired token]
    ↓
claims["sub"] → username string                       [raises AppException(401) if sub is missing]
    ↓
username passed to ChatService.ask(question, username)
    ↓
username used as thread_id in LangGraph config
```

**Rules:**
- A request with no `Authorization` header, a non-Bearer scheme, an expired token, or a tampered token all return `401` with message `"Invalid or expired token"`.
- The `username` from the token is trusted as-is — no second database lookup.

---

## 9. Unit Test Plan

---

### 9.1 Agent Workflow Tests — `tests/unit/test_retrieval_workflow.py`

All external dependencies (LLM, tools, graph nodes) are mocked.

#### Fixtures

```python
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage


@pytest.fixture()
def base_state():
    return {
        "messages": [],
        "question": "Who bought Samsung products?",
        "route": "",
        "vector_result": "",
        "kg_result": "",
        "answer": "",
    }
```

#### State — `AgentState` Structure

| # | Test | Assertion |
|---|------|-----------|
| S-01 | State has all required fields | `AgentState.__annotations__` contains `messages`, `question`, `route`, `vector_result`, `kg_result`, `answer` |
| S-02 | `messages` uses `add_messages` reducer | `get_type_hints(AgentState, include_extras=True)["messages"]` metadata contains `add_messages` |
| S-03 | State can be constructed with all fields | No `TypeError` when constructing a full `AgentState` dict |

#### Tools — Placeholder Interfaces

| # | Test | Assertion |
|---|------|-----------|
| T-01 | `vector_search` is a LangChain tool | `hasattr(vector_search, "invoke")` is `True`; `vector_search.name == "vector_search"` |
| T-02 | `vector_search` returns a string | `isinstance(vector_search.invoke("Samsung"), str)` and result is not empty |
| T-03 | `vector_search` result reflects query | `"Samsung"` appears in `vector_search.invoke("Samsung")` |
| T-04 | `graph_search` is a LangChain tool | `hasattr(graph_search, "invoke")` is `True`; `graph_search.name == "graph_search"` |
| T-05 | `graph_search` returns a string | `isinstance(graph_search.invoke("Samsung"), str)` and result is not empty |
| T-06 | `graph_search` result reflects query | `"Samsung"` appears in `graph_search.invoke("Samsung")` |
| T-07 | `vector_search` has a non-empty description | `len(vector_search.description) > 0` |
| T-08 | `graph_search` has a non-empty description | `len(graph_search.description) > 0` |

#### Planner Agent

Mock `src.agents.agents.llm`.

| # | Test | LLM mock `.content` | Expected `result` |
|---|------|---------------------|-------------------|
| P-01 | Routes to vector | `"vector"` | `{"route": "vector"}` |
| P-02 | Routes to kg | `"kg"` | `{"route": "kg"}` |
| P-03 | Routes to both | `"both"` | `{"route": "both"}` |
| P-04 | Routes to direct | `"direct"` | `{"route": "direct"}` |
| P-05 | Strips whitespace | `"  vector  "` | `{"route": "vector"}` |
| P-06 | Lowercases response | `"VECTOR"` | `{"route": "vector"}` |
| P-07 | Only sets `"route"` key | `"vector"` | `result.keys() == {"route"}` |
| P-08 | Passes question to LLM | `"direct"` (question=`"What is 2+2?"`) | `llm.invoke` called once; call arg contains `"What is 2+2?"` |

#### Vector Agent

Mock `src.agents.agents.vector_search`.

| # | Test | Setup | Assertion |
|---|------|-------|-----------|
| VA-01 | Returns `vector_result` key | `mock_tool.invoke` → `"some result"` | `result == {"vector_result": "some result"}` |
| VA-02 | Only sets `vector_result` | — | `result.keys() == {"vector_result"}` |
| VA-03 | Calls `invoke` with question | `state["question"] = "Samsung warranty"` | `mock_tool.invoke.assert_called_once_with("Samsung warranty")` |
| VA-04 | Result is a string | — | `isinstance(result["vector_result"], str)` |

#### KG Agent

Mock `src.agents.agents.graph_search`.

| # | Test | Setup | Assertion |
|---|------|-------|-----------|
| KG-01 | Returns `kg_result` key | `mock_tool.invoke` → `"some kg result"` | `result == {"kg_result": "some kg result"}` |
| KG-02 | Only sets `kg_result` | — | `result.keys() == {"kg_result"}` |
| KG-03 | Calls `invoke` with question | `state["question"] = "Samsung warranty"` | `mock_tool.invoke.assert_called_once_with("Samsung warranty")` |
| KG-04 | Result is a string | — | `isinstance(result["kg_result"], str)` |

#### Direct Answer Agent

Mock `src.agents.agents.llm`.

| # | Test | Setup | Assertion |
|---|------|-------|-----------|
| DA-01 | Returns `answer` key | LLM → `"The answer is 42."` | `result == {"answer": "The answer is 42."}` |
| DA-02 | Only sets `answer` | — | `result.keys() == {"answer"}` |
| DA-03 | Passes question to LLM | `state["question"] = "What is 2+2?"` | `llm.invoke.assert_called_once_with("What is 2+2?")` |
| DA-04 | Does not call tools | — | `vector_search.invoke` not called; `graph_search.invoke` not called |

#### Answer Synthesis Agent

Mock `src.agents.agents.llm`.

| # | Test | Setup | Assertion |
|---|------|-------|-----------|
| AA-01 | Returns `answer` key | LLM → `"Synthesized answer."` | `result == {"answer": "Synthesized answer."}` |
| AA-02 | Only sets `answer` | — | `result.keys() == {"answer"}` |
| AA-03 | Prompt includes question | `state["question"] = "Samsung warranty"` | LLM call arg contains `"Samsung warranty"` |
| AA-04 | Prompt includes vector_result | `state["vector_result"] = "some docs"` | LLM call arg contains `"some docs"` |
| AA-05 | Prompt includes kg_result | `state["kg_result"] = "entity data"` | LLM call arg contains `"entity data"` |
| AA-06 | Missing `vector_result` key — no error | State has no `"vector_result"` key | No `KeyError`; LLM called once |
| AA-07 | Missing `kg_result` key — no error | State has no `"kg_result"` key | No `KeyError`; LLM called once |

#### Router Function

```python
from src.agents.graph import router
from langgraph.types import Send
```

| # | Test | `state["route"]` | Expected return |
|---|------|-----------------|-----------------|
| R-01 | Routes to vector | `"vector"` | `"vector"` (string) |
| R-02 | Routes to kg | `"kg"` | `"kg"` (string) |
| R-03 | Routes to direct | `"direct"` | `"direct"` (string) |
| R-04 | Routes both — returns list of Sends | `"both"` | A `list` with exactly 2 `Send` objects |
| R-05 | Both Sends target vector and kg nodes | `"both"` | `{s.node for s in result} == {"vector", "kg"}` |

#### Graph Compilation

| # | Test | Assertion |
|---|------|-----------|
| GC-01 | Graph compiles without error | `graph` is not `None`; no exception on import |
| GC-02 | `MemorySaver` is used | `isinstance(memory, MemorySaver)` |
| GC-03 | Graph has "planner" node | `"planner" in graph.nodes` |
| GC-04 | Graph has "vector" node | `"vector" in graph.nodes` |
| GC-05 | Graph has "kg" node | `"kg" in graph.nodes` |
| GC-06 | Graph has "answer" node | `"answer" in graph.nodes` |
| GC-07 | Graph has "direct" node | `"direct" in graph.nodes` |

#### Checkpointing and Thread Isolation

Mock node functions so graph invocation makes no LLM calls.

| # | Test | Assertion |
|---|------|-----------|
| CP-01 | Graph accepts config with `thread_id` | Invoke with `{"configurable": {"thread_id": "test_user"}}` — no `TypeError` |
| CP-02 | Different thread_ids produce isolated states | Invoke with `thread_id="user_a"` then `thread_id="user_b"` — state from user_a is not visible in user_b |
| CP-03 | Same thread_id accumulates state | Invoke twice with same `thread_id` — second invocation has access to first checkpoint |

#### End-to-End Workflow (Mocked Nodes)

Patch node functions at the graph module level.

| # | Test | Planner route | Nodes executed | Final state |
|---|------|--------------|----------------|-------------|
| E2E-01 | vector route | `"vector"` | planner → vector_agent → answer_agent | `result["answer"]` is non-empty |
| E2E-02 | kg route | `"kg"` | planner → kg_agent → answer_agent | `result["answer"]` is non-empty |
| E2E-03 | direct route | `"direct"` | planner → direct_answer | `result["answer"]` is non-empty |
| E2E-04 | both route | `"both"` | planner → vector_agent + kg_agent → answer_agent | `result["answer"]` non-empty; both `vector_result` and `kg_result` set |

---

### 9.2 ChatService Unit Tests — `tests/unit/test_chat_service.py`

Mock `src.services.chat.graph`.

```python
@pytest.fixture()
def service():
    return ChatService()
```

| # | Test | `graph.invoke` mock | Expected |
|---|------|---------------------|----------|
| CS-01 | Returns answer from graph result | Returns `{"answer": "Here is the answer."}` | `service.ask("q", "alice") == "Here is the answer."` |
| CS-02 | Passes question in graph input | Returns `{"answer": "ok"}` | `graph.invoke` called with dict containing `"question": "q"` |
| CS-03 | Sets thread_id from username | Returns `{"answer": "ok"}` | `graph.invoke` called with `config={"configurable": {"thread_id": "alice"}}` |
| CS-04 | Different usernames produce different thread_ids | Returns `{"answer": "ok"}` | First call uses `thread_id="alice"`, second uses `thread_id="bob"` |
| CS-05 | Graph exception raises AppException 500 | Raises `Exception("LLM error")` | `AppException` with `status_code=500` raised; message is `"Chat workflow failed"` |
| CS-06 | Empty answer raises AppException 500 | Returns `{"answer": ""}` | `AppException` with `status_code=500` raised |
| CS-07 | Missing `answer` key raises AppException 500 | Returns `{}` | `AppException` with `status_code=500` raised |
| CS-08 | AppException from graph is caught and re-raised as 500 | Raises `AppException("downstream error", 400)` | Re-raised as `AppException` with `status_code=500`, not 400 |

---

## 10. End-to-End Test Plan — `tests/e2e/test_chat_api.py`

Use `fastapi.testclient.TestClient`. Patch `src.services.chat.graph` to return a controlled answer without invoking the LLM. Use a fixture that signs up a test user via `POST /api/signup` and logs in via `POST /api/login` to obtain a valid JWT.

```python
@pytest.fixture(scope="module")
def auth_token(client):
    client.post("/api/signup", json={"username": "chatuser", "password": "Pass123!"})
    resp = client.post("/api/login", json={"username": "chatuser", "password": "Pass123!"})
    return resp.json()["token"]
```

| # | Test | Request | Mock `graph.invoke` | Expected status | Expected body |
|---|------|---------|---------------------|-----------------|---------------|
| E2E-01 | Valid question returns answer | Valid JWT, `{"question": "Who bought Samsung?"}` | Returns `{"answer": "Customer A bought Samsung."}` | `200` | `{"answer": "Customer A bought Samsung."}` |
| E2E-02 | Answer reflects graph output | Valid JWT, any question | Returns `{"answer": "Custom answer."}` | `200` | `{"answer": "Custom answer."}` |
| E2E-03 | Missing Authorization header | No header, valid body | — | `401` | `{"success": false, "error": "Invalid or expired token"}` |
| E2E-04 | Invalid Bearer token | `Authorization: Bearer bad-token` | — | `401` | `{"success": false, "error": "Invalid or expired token"}` |
| E2E-05 | Non-Bearer scheme | `Authorization: Basic dXNlcjpwYXNz` | — | `401` | `{"success": false, "error": "Invalid or expired token"}` |
| E2E-06 | Empty question string | Valid JWT, `{"question": ""}` | — | `422` | FastAPI validation error (min_length=1 violated) |
| E2E-07 | Missing `question` field | Valid JWT, `{}` | — | `422` | FastAPI validation error (required field missing) |
| E2E-08 | Graph failure returns 500 | Valid JWT, valid question | Raises `Exception("graph error")` | `500` | `{"success": false, "error": "Chat workflow failed"}` |
| E2E-09 | Different users produce isolated thread_ids | Two JWTs (alice, bob) | Returns `{"answer": "ok"}` for both | `200` for both | `graph.invoke` called twice with different `thread_id` values |

---

## 11. Error Handling Summary

| Failure point | Exception raised by | Caught by | Behaviour |
|---|---|---|---|
| Missing/invalid JWT | `_get_current_user` via `AuthUtils.decode_access_token` | Global handler | HTTP 401 `{"success": false, "error": "Invalid or expired token"}` |
| JWT `sub` claim missing | `_get_current_user` | Global handler | HTTP 401 same message |
| Empty `question` | Pydantic `Field(min_length=1)` | FastAPI 422 handler | HTTP 422 validation error |
| LangGraph execution error | Any exception inside `graph.invoke()` | `ChatService.ask` | Caught, logged, re-raised as `AppException(500)` |
| Empty or missing `answer` in graph result | `ChatService.ask` | `ChatService.ask` | Raises `AppException(500)` |
| Unknown `route` from planner | LangGraph `InvalidUpdateError` | `ChatService.ask` catches all exceptions | Re-raised as `AppException(500)` |

---

## 12. Out of Scope

- Vector database retrieval implementation (ChromaDB / FAISS / Pinecone).
- Knowledge Graph Cypher query generation and execution.
- Embedding generation for vector search.
- Prompt engineering for retrieval quality.
- Multiple conversations per user (one `thread_id` per username).
- Persistent checkpointing across process restarts (`MemorySaver` is in-memory only).
- Streaming responses from the chat endpoint.
- Storing chat history in MongoDB.
- Async graph invocation.
- Frontend/UI integration for the chat page.
- Adding new agent nodes beyond the five defined here.
