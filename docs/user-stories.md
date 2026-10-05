## User Stories

---

# User Signup API

## Description

Develop a **POST** `/api/signup` endpoint that allows new users to register. The API should use a reusable MongoDB connection class, validate that the username is unique, securely hash the password before storing it, and return a JWT token upon successful registration.

## Acceptance Criteria

* Implement a reusable MongoDB connection class.
* Create a **POST** `/api/signup` endpoint.
* Accept **username** and **password** in the request body.
* Check if the username already exists in MongoDB.
* Return an error message if the username is already taken.
* Hash the password before storing it in the database.
* Store the username and hashed password in MongoDB.
* Generate and return a JWT token upon successful signup.
* Return appropriate HTTP status codes for success and failure.

---

---

 # User Login API

## Description

Develop a **POST** `/api/login` endpoint that authenticates registered users. The API should validate the provided username and password against the stored credentials in MongoDB. Upon successful authentication, generate a JWT token and return it to the frontend. The frontend should store the received JWT token in the browser's **sessionStorage** and redirect the user to the `/upload` page.


## Acceptance Criteria

* Create a **POST** `/api/login` endpoint.
* Accept **username** and **password** in the request body.
* Verify that the username exists in MongoDB.
* Compare the provided password with the stored hashed password.
* Return **401 Unauthorized** if the username or password is invalid.
* Generate and return a JWT token upon successful authentication.
* Store the received JWT token in the browser's **sessionStorage**.
* Redirect the user to the **`/upload`** page after a successful login.
* Return appropriate HTTP status codes for success and failure.


---

---
 
# Upload Documents API

## Description

Develop a **POST** `/api/upload` endpoint that accepts a list of Base64-encoded files. Process each file one at a time by converting the Base64 string into binary data. If the file is a PDF, extract its content using **PyMuPDF**. If the file is a **CSV**, **XLS**, or **XLSX** file, extract its contents using the appropriate parser for further processing.


## Acceptance Criteria

* Create a **POST** `/api/upload` endpoint.
* Accept a list of Base64-encoded files in the request body.
* Process one file at a time from the list.
* Convert each Base64 string into binary format.
* Extract text from PDF files using **PyMuPDF**.
* Extract data from **CSV**, **XLS**, and **XLSX** files.
* Return an appropriate success or error response for the upload request.


---

---

# PDF Chunking and Vector Storage

## Description

Develop a document processing pipeline that performs **parent-child chunking** on extracted PDF content. Create parent chunks of approximately **500 tokens** and child chunks of approximately **100 tokens**. Store each parent chunk in MongoDB and capture its generated ID. Generate embeddings for each child chunk using the **OpenAI Embedding** model (API key loaded from the `.env` file). Store each child chunk in an in-memory ChromaDB collection along with the corresponding parent chunk ID as metadata.


## Acceptance Criteria

* Split the extracted PDF text into **parent chunks** of approximately **500 tokens**.
* Split each parent chunk into **child chunks** of approximately **100 tokens**.
* Store each parent chunk in **MongoDB** and collect its generated ID.
* Generate embeddings for every child chunk using the **OpenAI Embedding** model.
* Load the OpenAI API key from the **`.env`** file.
* Store each child chunk in an **in-memory ChromaDB** collection.
* Attach the corresponding **parent chunk ID** as metadata to every child chunk stored in ChromaDB.
* Return a success response after all chunks have been processed and stored.

---

---

# CSV/XLSX Chunking and Vector Storage

## Description

Develop a processing pipeline for **CSV** and **XLSX** files. Convert each row into a human-readable key-value representation using the column headers. Group every **10 rows** into a single chunk (instead of token-based chunking). Generate embeddings for each chunk using the **OpenAI Embedding** model (API key loaded from the `.env` file) and store the chunks along with their embeddings in an in-memory ChromaDB collection.

## Acceptance Criteria

* Support processing of **CSV**, **XLS**, and **XLSX** files.
* Convert each row into a readable **key-value** format using the column names.
* Group every **10 rows** into a single chunk.
* Generate embeddings for each chunk using the **OpenAI Embedding** model.
* Load the OpenAI API key from the **`.env`** file.
* Store each chunk and its embedding in an **in-memory ChromaDB** collection.
* Return a success response after all chunks have been processed and stored.


---

---

# Data Ingestion Pipeline

## Description

Create a common service class named **`DataIngestion`** to process both **PDF** and **CSV/XLS/XLSX** documents. The service should identify the document type and execute the appropriate processing pipeline.

The Knowledge Graph (KG) pipeline should follow this flow:

**Input Data → Ontology Design → LLM → Structured JSON → Validation Layer → Entity Resolution Layer → Neo4j**

* **Input Data:** Receive the extracted document text or chunks.
* **Ontology Design:** Load the ontology definition from **`/ontology/ontology_context.md`** and use it to define the entities, relationships, and properties to extract.
* **LLM:** Extract entities and relationships based on the ontology and return structured JSON.
* **Structured JSON:** Produce a standardized JSON representation of the extracted knowledge.
* **Validation Layer:** Validate the JSON schema and remove invalid or incomplete records.
* **Entity Resolution Layer:** Deduplicate and normalize entities before persistence.
* **Neo4j:** Store the final entities and relationships using the Python Neo4j driver. Load the Neo4j connection URI, username, and password from the **`.env`** file.


## Acceptance Criteria

* Create a reusable **`DataIngestion`** service for all supported document types.
* Automatically detect the uploaded file type and invoke the corresponding processing pipeline.
* Load the ontology from **`/ontology/ontology_context.md`**.
* Load the Neo4j URI, username, and password from the **`.env`** file.
* Implement the Knowledge Graph pipeline:

  * Input Data → Ontology Design → LLM → Structured JSON → Validation Layer → Entity Resolution Layer → Neo4j.
* For **PDF** files:

  * Execute the KG pipeline independently of the existing parent-child chunking pipeline.
  * If a PDF is too large, split it into smaller chunks before sending them to the KG pipeline.
  * Continue the existing parent-child chunking and vector storage pipeline without modification.
* For **CSV/XLS/XLSX** files:

  * Continue using the existing row-based chunking (10 rows per chunk).
  * Remove the vector embedding and ChromaDB storage.
  * Execute the KG pipeline on each chunk and persist the extracted graph in Neo4j.
* Ensure the solution is modular and extensible for additional document types in the future.


---

---

# Chatbot UI

## Description

Develop a modern and responsive chatbot interface using **Python NiceGUI**. The chatbot page should be accessible through the **`/chatbot`** route. When the user submits a question, send it to the **POST** `/api/chat` endpoint and display the returned response in the chat window. No WebSocket implementation is required.

## Acceptance Criteria

* Develop the chatbot page using **Python NiceGUI**.
* The page is accessible through the **`/chatbot`** route.
* The UI has a clean, modern, and responsive chat interface.
* Display chat messages in a conversation format (user and assistant).
* Provide a text input and **Send** button for submitting questions.
* Clicking **Send** issues a **POST** request to **`/api/chat`**.
* Display the assistant's response in the chat window.
* Disable the **Send** button while waiting for the API response.
* Display an appropriate error message if the API request fails.


---

---

# User Story: Implement LangGraph Multi-Agent Orchestration Framework

## Story

**As a** developer,

**I want** to implement a LangGraph-based multi-agent orchestration framework exposed via a `POST /api/chat` endpoint,

**So that** authenticated users can submit questions through the API, have their requests routed to the appropriate specialized agent, and receive synthesized answers while maintaining conversation state across interactions.

## Scope

Implement the following components:

**Agent Workflow (`src/agents/`):**

* Define a shared LangGraph state to exchange data between agents.
* Create a Planner Agent responsible for determining which downstream agent(s) should handle a user request.
* Implement separate agent nodes for:

  * Vector Agent
  * Knowledge Graph Agent
  * Direct Response Agent
  * Answer Synthesis Agent
* Configure conditional routing from the Planner Agent to the appropriate downstream agent(s).
* Support parallel execution when both Vector and Knowledge Graph agents are selected.
* Implement conversation memory using LangGraph messages/state.
* Configure checkpointing to persist workflow state using `thread_id`.
* Ensure each user maintains an isolated execution state by using their username as the `thread_id`.
* Implement placeholder tools/interfaces for downstream agents. (Business logic for Vector Retrieval and Knowledge Graph Retrieval is out of scope and will be implemented separately.)
* Compile and expose the LangGraph workflow for application integration.

**API Endpoint (`POST /api/chat`):**

* Accept a `question` string in the request body.
* Require a valid JWT Bearer token in the `Authorization` header.
* Extract the authenticated username from the JWT and use it as the `thread_id`.
* Invoke the LangGraph workflow with the user's question.
* Return the synthesized answer in the response body.
* Return appropriate HTTP status codes for auth failures, validation errors, and workflow errors.

## Acceptance Criteria

* A LangGraph workflow is successfully created with Planner, Vector, Knowledge Graph, Direct Response, and Answer Synthesis nodes.
* The Planner Agent routes requests using conditional edges based on the question type.
* Parallel execution is supported when both Vector and Knowledge Graph agents are selected.
* Conversation state is shared correctly across all nodes via the shared `AgentState`.
* Memory is maintained across user interactions using LangGraph state and `add_messages`.
* Checkpointing is enabled to support resumable conversations via `MemorySaver`.
* Multiple concurrent users are supported through isolated `thread_id`-based state management (one `thread_id` per username).
* Placeholder tool interfaces (`vector_search`, `graph_search`) are available for downstream agent integration.
* The implementation is modular and allows future addition of new agents without significant changes to the workflow.
* `POST /api/chat` accepts `{"question": "..."}` with a valid JWT and returns `{"answer": "..."}`.
* `POST /api/chat` returns `401` for missing or invalid JWT tokens.
* `POST /api/chat` returns `422` for an empty or missing `question` field.
* `POST /api/chat` returns `500` with `{"success": false, "error": "Chat workflow failed"}` if the agent workflow fails.
* Vector Retrieval implementation is **not** included in this story.
* Knowledge Graph Retrieval implementation is **not** included in this story.

## Out of Scope

* Vector database retrieval implementation.
* Knowledge Graph query implementation.
* Embedding generation.
* Cypher query generation.
* RAG retrieval logic.
* Knowledge Graph retrieval workflow.
* Prompt engineering for retrieval agents.
* Multiple conversations per user (one persistent conversation state per username).
* Persistent checkpointing across process restarts (`MemorySaver` is in-memory only).
* Storing chat history in MongoDB.
* Streaming responses from the chat endpoint.
* Frontend/UI implementation.

---

---

# Knowledge Graph Retrieval

## Description

Implement the retrieval logic inside the `graph_search` tool in `src/agents/tools.py`, replacing the existing placeholder. When invoked, the tool should translate the user's natural language question into a Cypher query through a multi-step pipeline and return a formatted answer by querying Neo4j.

The pipeline follows this flow, with each step described below:

1. **LLM Semantic Parser** — The LLM reads the user question and the ontology from `ontology/ontology_context.md` to extract intent: which node labels, relationship types, filters, and properties are relevant.
2. **Graph Query DSL** — The LLM outputs a structured intermediate JSON object (a simple DSL) describing the query in ontology terms (e.g. `match`, `where`, `return` fields) rather than raw Cypher — keeping the LLM away from syntax.
3. **Ontology Validator** — Validate every label, relationship type, and property name in the DSL against the known ontology. Reject and raise an error if unknown terms are found.
4. **Graph Query Planner** — Determine the optimal traversal pattern: which node is the anchor, which relationships to traverse, and which filters to apply.
5. **Query AST** — Represent the planned query as a Python dataclass/dict (Abstract Syntax Tree) capturing anchor node, traversals, filters, and return fields in a structured form.
6. **Graph Compiler (AST → Cypher)** — Walk the AST and emit a parameterised Cypher string with a separate `params` dict. No string interpolation of user values.
7. **Neo4j Execute** — Run the compiled Cypher query against Neo4j using `KnowledgeGraphRepository`. Add a new `run_query(cypher: str, params: dict) -> list[dict]` method to `KnowledgeGraphRepository` for read queries.
8. **Result** — Collect the raw Neo4j records and serialise them into a plain text or JSON summary string.
9. **LLM** — Pass the raw result and the original question to the LLM to produce a natural language answer.
10. **Response** — Return the final answer string to the downstream Answer Synthesis Agent.

## Acceptance Criteria

* Load the ontology from `ontology/ontology_context.md` and pass it to the LLM semantic parser prompt.
* The LLM outputs a structured DSL JSON (not raw Cypher) describing the query in ontology terms.
* Validate all labels, relationship types, and property names in the DSL against the ontology; raise `AppException` with `status_code=400` for unknown terms.
* Build a query AST from the validated DSL describing the traversal pattern, filters, and return fields.
* Compile the AST into a parameterised Cypher query string with a separate `params` dict (no user-value string interpolation).
* Add `run_query(cypher: str, params: dict) -> list[dict]` to `KnowledgeGraphRepository` for executing read queries against Neo4j.
* Pass the compiled Cypher and params to `KnowledgeGraphRepository.run_query()` and collect the result records.
* Pass the raw result and the original question to the LLM to generate a natural language answer.
* Return the final answer string to be consumed by the downstream Answer Synthesis Agent.
* Return a descriptive empty-result message if Neo4j returns no records.
* Load the OpenAI API key and model from `.env` (`OPENAI_API_KEY`, `OPENAI_MODEL`).

---

# Vector RAG Retrieval

## Description

Implement the RAG retrieval logic inside the `vector_search` tool in `src/agents/tools.py`, replacing the existing placeholder. When invoked, the tool should embed the user query using the OpenAI Embedding model, perform a semantic search over the child chunks stored in ChromaDB, retrieve the top 3 results, fetch the corresponding parent chunks from MongoDB, deduplicate them, and return a combined context string for the Answer Synthesis Agent.

## Acceptance Criteria

* Generate an embedding for the user query using the OpenAI Embedding model (load API key from `.env`).
* Query the in-memory ChromaDB `child_chunks` collection and retrieve the top **3** semantically similar child chunks.
* Extract the `parent_id` from the metadata of each returned child chunk.
* Deduplicate the collected `parent_id` values.
* Add a `find_parent_chunks_by_ids(parent_ids: list[str])` method to `ChunkRepository` that fetches parent chunk documents from MongoDB by their IDs.
* Concatenate the `text` field of each fetched parent chunk into a single context string.
* Return the context string to be consumed by the downstream Answer Synthesis Agent.
* Return an empty string if ChromaDB returns no results.

---