# Feature Spec: Chatbot UI

**ID:** `10-chatbot-ui`
**Status:** Ready for implementation
**Route:** `/chatbot`
**Source story:** Chatbot interface — user submits a question, frontend POSTs to `/api/chat`, assistant response is displayed in the chat window

---

## 1. Overview

A modern, responsive chat interface built with NiceGUI that allows authenticated users to converse with the AI assistant. The page is accessible at `/chatbot` and is the destination users land on after a successful document upload.

Users type a question into a text input at the bottom of the page and click Send. The frontend issues a synchronous `POST` to `/api/chat` with the message and the session's JWT token, then appends both the user message and the returned assistant response to a scrollable conversation window. While the request is in flight the Send button is disabled. If the request fails an inline error label shows a contextual message without clearing the conversation history.

Unlike the authentication pages (login/signup), this page renders the standard app header. Unlike the upload page, it has no staged-state list — all client state is the growing conversation history.

---

## 2. Functional Requirements

### FR-01 — Route Registration
The chatbot page must be registered at the `/chatbot` route using the `@ui.page('/chatbot')` decorator. The module `pages.chatbot` must be imported in `frontend/main.py` so the decorator fires before `ui.run()` is called.

### FR-02 — Page Shell
The page must render the standard app header containing the application name "Decision Intelligence" (`text-xl font-bold text-slate-800`), styled with `bg-white border-b border-slate-200 p-4 shadow-none`. No left sidebar. The main content must use a two-part vertical layout:
- A **chat area** that fills the available vertical space (`flex-1 overflow-y-auto`) and contains the message history.
- An **input area** pinned to the bottom of the viewport (`sticky bottom-0`) containing the text input, error label, and Send button.

### FR-03 — Conversation Message Display
All messages must be rendered inside a `ui.column` (`chat_column`) that is cleared and rebuilt by `_render_messages()` on each update.

Each message is rendered as a `ui.row` that controls horizontal alignment:
- **User message** (`role == "user"`): `justify-end` row, bubble styled `bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-2 max-w-prose text-sm`
- **Assistant message** (`role == "assistant"`): `justify-start` row, bubble styled `bg-white border border-slate-200 text-slate-800 rounded-2xl rounded-tl-sm px-4 py-2 max-w-prose text-sm shadow-sm`

An empty state — when `messages` is empty — must render a centered hint inside `chat_column`:
```
text-slate-400 text-sm italic text-center
"Ask a question to get started."
```

### FR-04 — Auto-Scroll to Latest Message
After every call to `_render_messages()`, the chat area must scroll to the bottom so the newest message is visible. Use `ui.run_javascript("document.getElementById('chat-scroll').scrollTop = document.getElementById('chat-scroll').scrollHeight")`. The scrollable chat container must carry the HTML id `chat-scroll` (set via `.props('id="chat-scroll"')`).

### FR-05 — Text Input Field
The input area must contain a `ui.input` (`message_input`) with:
- `placeholder='Type your question…'`
- `.classes('flex-1')` so it expands to fill the available row width
- An `on('keydown.enter', ...)` handler that calls `_handle_send()` when Enter is pressed, but only if the input contains non-whitespace content and the Send button is not disabled

### FR-06 — Send Button State
The Send button (`send_btn`) must follow these rules:
- **Disabled** on page load (input is empty)
- **Enabled** when `message_input.value` contains at least one non-whitespace character — enforced via an `on('input', ...)` handler on `message_input`
- **Disabled** immediately when Send is clicked and the request begins
- **Re-enabled** after the response arrives (success) or after an error, if `message_input.value` is still non-empty; otherwise remains disabled
- The function `_update_send_button()` encapsulates enable/disable logic and is called after every state change

### FR-07 — Auth Token Retrieval
Before issuing the POST, the handler must retrieve the JWT from `sessionStorage`:
```python
token = await ui.run_javascript("sessionStorage.getItem('auth_token') || ''")
```
This token is passed as `Authorization: Bearer <token>` in the request headers.

Because `ui.run_javascript()` is a coroutine, `_handle_send` **must be declared `async`**.

### FR-08 — Chat API Call
`_handle_send()` must:
1. Read and strip `message_input.value`; do nothing if blank.
2. Append the user message to `messages`: `{"role": "user", "content": user_text}`.
3. Clear `message_input.value` and call `_update_send_button()` (button becomes disabled since input is now empty).
4. Call `_render_messages()` to show the user bubble immediately.
5. Hide any previous error: `error_label.classes(add='invisible', remove='visible')`.
6. Disable `send_btn`.
7. Retrieve the auth token (FR-07).
8. Send a synchronous `POST` via `requests`:
   - **URL:** `{API_URL}/api/chat`
   - **Headers:** `{"Authorization": f"Bearer {token}", "Content-Type": "application/json"}`
   - **Body:** `json={"message": user_text}`
9. Handle response per FR-09 / FR-10.

### FR-09 — Success Handling
If `200 <= response.status_code < 300`:
1. Parse the response JSON and extract the assistant's reply from the `"response"` key.
2. Append to `messages`: `{"role": "assistant", "content": reply_text}`.
3. Call `_render_messages()` to display the assistant bubble.
4. Re-evaluate send button state via `_update_send_button()`.

### FR-10 — Error Handling
If the response is outside the 2xx range or an exception occurs:
1. Set `error_label` to the appropriate message and make it `visible`.
2. Re-evaluate send button state via `_update_send_button()` (re-enables if input has text).
3. Do **not** remove the failed user message from `messages` — leave it in the history so the user can see what they sent.

| Condition | Message |
|---|---|
| `401 Unauthorized` | `"Session expired. Please log in again."` |
| `429 Too Many Requests` | `"Too many requests. Please wait a moment and try again."` |
| Any other 4xx | `detail` from response JSON, or `"Request failed. Please try again."` |
| 5xx | `"Server error. Please try again later."` |
| `requests.ConnectionError` | `"Could not reach the server. Check your connection."` |
| `requests.Timeout` | `"Could not reach the server. Check your connection."` |
| Any other exception | `"An unexpected error occurred. Please try again."` |

---

## 3. Non-Functional Requirements

### NFR-01 — Styling
All styling must use Tailwind utility classes via `.classes()`. No inline `style=` attributes and no custom CSS files unless an effect is impossible with Tailwind alone.

### NFR-02 — Responsiveness
The chat layout must render correctly at desktop (1280px+) and tablet (768px) widths. Message bubbles must not overflow horizontally — use `max-w-prose` on each bubble.

### NFR-03 — Modularity
Do not write a monolithic `@ui.page` function body. At minimum, define these named helper functions:

| Function | Responsibility |
|---|---|
| `_build_header()` | Renders the standard app header |
| `_build_chat_area(content_col)` | Creates and returns the scrollable `chat_column` container |
| `_build_input_area(content_col)` | Renders the error label, text input, and Send button |
| `_render_messages()` | Clears and rebuilds `chat_column` from `messages`; triggers auto-scroll |
| `_update_send_button()` | Enables or disables `send_btn` based on `message_input.value` |

### NFR-04 — Environment Variable Isolation
`API_URL` must be loaded at module import time using `load_dotenv()` and `os.getenv('API_URL', 'http://localhost:8000')`. It must not be hardcoded.

### NFR-05 — Per-Client State Isolation
`messages` and all UI references (`chat_column`, `message_input`, `send_btn`, `error_label`) must be **local variables** inside the `@ui.page` function body — not module-level — so each browser session gets its own independent state.

### NFR-06 — Async Handler Scope
Only `_handle_send` needs to be `async` (because it awaits `ui.run_javascript()`). All other helpers remain synchronous.

### NFR-07 — Error Label Persistence
`error_label` must always be allocated DOM space (`.classes('invisible')` / `.classes('visible')`) to prevent layout shift when errors appear or disappear.

### NFR-08 — Blocking HTTP Call Acceptable
The `requests.post(...)` call is synchronous and blocking. This is consistent with the existing upload and login page patterns and is acceptable within the NiceGUI per-client handler model. Do not introduce `asyncio`, `httpx`, or background threads.

---

## 4. Acceptance Criteria

| ID | Criterion | How to verify |
|---|---|---|
| AC-01 | Navigating to `http://localhost:8080/chatbot` renders the page without error | Manual browser check |
| AC-02 | The page displays the standard header with "Decision Intelligence" title | Observe the header |
| AC-03 | The chat area displays the empty-state hint when no messages have been sent | Load the page fresh, observe hint text |
| AC-04 | The Send button is disabled on page load | Observe button state before typing |
| AC-05 | The Send button is enabled after typing non-whitespace text in the input | Type text, observe button |
| AC-06 | The Send button is disabled when the input is cleared | Clear the input field, observe button |
| AC-07 | Pressing Enter in the input field sends the message when the input is non-empty | Type a question, press Enter |
| AC-08 | Pressing Enter when the input is empty does nothing | Leave input empty, press Enter |
| AC-09 | Clicking Send appends the user's message as a right-aligned blue bubble immediately | Click Send, observe UI before response arrives |
| AC-10 | The input field is cleared after clicking Send | Observe input field after clicking Send |
| AC-11 | The Send button is disabled while the API request is in flight | Click Send, observe button state immediately |
| AC-12 | A 2xx response appends the assistant's reply as a left-aligned bubble | Send a question against a working backend |
| AC-13 | The request body is `{"message": "<user text>"}` with `Authorization: Bearer <token>` header | Inspect via network tab or backend logs |
| AC-14 | A 401 response shows "Session expired. Please log in again." inline | Simulate a 401 from the backend |
| AC-15 | A 429 response shows the rate-limit error message inline | Simulate a 429 from the backend |
| AC-16 | A 5xx response shows "Server error. Please try again later." inline | Simulate a 500 from the backend |
| AC-17 | A network error shows "Could not reach the server. Check your connection." | Stop the backend and send a message |
| AC-18 | After any error the user message remains visible in the chat history | Trigger an error, observe the message list |
| AC-19 | After any error the Send button is re-enabled if the input still has text | Trigger an error, check button state |
| AC-20 | The chat area auto-scrolls to the latest message after each exchange | Send multiple messages until they overflow the visible area |
| AC-21 | Message bubbles do not overflow horizontally at 768px viewport width | Resize browser to 768px |
| AC-22 | Multiple exchanges accumulate in the conversation without clearing prior messages | Send three questions in sequence |

---

## 5. Out of Scope

The following are explicitly excluded and must not be implemented:

- WebSocket or streaming responses (all responses are returned in a single POST reply)
- Conversation persistence across browser sessions (state resets on page reload per NiceGUI's per-client model)
- Message editing or deletion
- Markdown / rich-text rendering inside message bubbles (plain text only)
- Typing indicator / loading spinner inside the chat area
- Copy-to-clipboard button on message bubbles
- Conversation export (PDF, TXT, etc.)
- File attachments inside the chatbot (handled by the separate upload page)
- Model selector or system-prompt configuration
- Authentication guard on `/chatbot` (no redirect to `/login` if token is absent)
- The `/api/chat` backend endpoint itself (this spec covers the frontend only)

---

## 6. Design Rules

### 6.1 Layout Skeleton

```
┌────────────────────── w-screen min-h-screen bg-slate-50 ──────────────────────┐
│                                                                                │
│  ┌── Header ──────────────────────────────────────────────────────────────┐   │
│  │  bg-white border-b border-slate-200 p-4 shadow-none                   │   │
│  │  [Decision Intelligence]   text-xl font-bold text-slate-800           │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
│                                                                                │
│  ┌── Chat Wrapper (flex-1 flex flex-col max-w-3xl mx-auto w-full) ───────┐   │
│  │                                                                        │   │
│  │  ┌── Chat Area (flex-1 overflow-y-auto p-6) id="chat-scroll" ──────┐  │   │
│  │  │                                                                  │  │   │
│  │  │  [empty state]  "Ask a question to get started."  (italic/muted)│  │   │
│  │  │                                                                  │  │   │
│  │  │  ── after messages exist ────────────────────────────────────── │  │   │
│  │  │                                                                  │  │   │
│  │  │  ┌─ user bubble (justify-end row) ──────────────────────────┐  │  │   │
│  │  │  │  [user text]  bg-blue-600 text-white rounded-2xl         │  │  │   │
│  │  │  └──────────────────────────────────────────────────────────┘  │  │   │
│  │  │                                                                  │  │   │
│  │  │  ┌─ assistant bubble (justify-start row) ───────────────────┐  │  │   │
│  │  │  │  [assistant text]  bg-white border border-slate-200      │  │  │   │
│  │  │  │                    rounded-2xl shadow-sm text-slate-800  │  │  │   │
│  │  │  └──────────────────────────────────────────────────────────┘  │  │   │
│  │  │                                                                  │  │   │
│  │  └──────────────────────────────────────────────────────────────────┘  │   │
│  │                                                                        │   │
│  │  ┌── Input Area (sticky bottom-0 bg-slate-50 border-t border-slate-200 p-4)│
│  │  │                                                                    │   │
│  │  │  [error label]   text-red-500 text-sm mb-2 invisible             │   │
│  │  │                                                                    │   │
│  │  │  ┌── input row (flex gap-3 items-center) ───────────────────┐    │   │
│  │  │  │  [ui.input flex-1 placeholder='Type your question…']     │    │   │
│  │  │  │  [Send button  bg-blue-600 text-white  disabled]         │    │   │
│  │  │  └──────────────────────────────────────────────────────────┘    │   │
│  │  └────────────────────────────────────────────────────────────────────│   │
│  └────────────────────────────────────────────────────────────────────────┘   │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Color & Typography Tokens

| Element | Tailwind classes |
|---|---|
| Page background | `bg-slate-50` |
| Header | `bg-white border-b border-slate-200 p-4 shadow-none` |
| App title | `text-xl font-bold text-slate-800` |
| Chat area | `flex-1 overflow-y-auto p-6 flex flex-col gap-4` |
| Empty-state hint | `text-slate-400 text-sm italic text-center` |
| User bubble row | `w-full flex justify-end` |
| User bubble | `bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-2 max-w-prose text-sm` |
| Assistant bubble row | `w-full flex justify-start` |
| Assistant bubble | `bg-white border border-slate-200 text-slate-800 rounded-2xl rounded-tl-sm px-4 py-2 max-w-prose text-sm shadow-sm` |
| Input area | `sticky bottom-0 bg-slate-50 border-t border-slate-200 p-4` |
| Error label | `text-red-500 text-sm mb-2` + `invisible`/`visible` |
| Text input | `flex-1` |
| Send button | `bg-blue-600 text-white hover:bg-blue-700` |

### 6.3 Spacing & Structure

- Chat area vertical padding: `p-6`, gap between messages: `gap-4`
- Input area padding: `p-4`
- Input row gap: `gap-3`, alignment: `items-center`
- Error label margin below: `mb-2`
- Chat wrapper max width: `max-w-3xl mx-auto w-full`

### 6.4 Component Naming Conventions

- Page module file: `frontend/pages/chatbot.py`
- `@ui.page('/chatbot')` function name: `chatbot_page()`
- State variables (local to `chatbot_page`): `messages`, `chat_column`, `message_input`, `send_btn`, `error_label`
- Helper functions: `_build_header`, `_build_chat_area`, `_build_input_area`, `_render_messages`, `_update_send_button`
- Event handler: `_handle_send` (async)

---

## 7. API Contract

### Endpoint
`POST {API_URL}/api/chat`

### Request Headers
```
Authorization: Bearer <jwt-from-sessionStorage>
Content-Type: application/json
```

### Request Body
```json
{
  "message": "What are the key trends in the dataset?"
}
```

### Success Response
- **Status:** `200 OK`
- **Body:**
```json
{
  "response": "Based on the uploaded documents, the key trends are..."
}
```
The frontend reads `response.json()["response"]` to extract the assistant reply text.

### Error Responses

| Status | Meaning | Frontend action |
|---|---|---|
| `401 Unauthorized` | Token missing or expired | `"Session expired. Please log in again."` |
| `429 Too Many Requests` | Rate limit exceeded | `"Too many requests. Please wait a moment and try again."` |
| `400 Bad Request` | Malformed request | `detail` from JSON, or `"Request failed. Please try again."` |
| `422 Unprocessable Entity` | Schema mismatch | `detail` from JSON, or `"Request failed. Please try again."` |
| `500 Internal Server Error` | Backend failure | `"Server error. Please try again later."` |
| `requests.ConnectionError` | Backend unreachable | `"Could not reach the server. Check your connection."` |
| `requests.Timeout` | Request timed out | `"Could not reach the server. Check your connection."` |
| Any other exception | Unexpected failure | `"An unexpected error occurred. Please try again."` |

### Environment Variable

| Variable | Default | Source |
|---|---|---|
| `API_URL` | `http://localhost:8000` | `.env` in project root |

---

## 8. File & Module Layout

```
frontend/
├── main.py                   # add: import pages.chatbot  # noqa: F401
└── pages/
    ├── signup.py             # existing
    ├── login.py              # existing
    ├── upload.py             # existing
    └── chatbot.py            # new — @ui.page('/chatbot'), self-contained module
```

`frontend/main.py` must contain:
```python
import pages.chatbot  # noqa: F401 — registers @ui.page('/chatbot')
```
alongside the existing page imports, before `ui.run()` is called.

---

## 9. Dependencies

All required packages are already tracked in `pyproject.toml`. No new dependencies are needed.

| Package | Purpose | Status |
|---|---|---|
| `nicegui` | UI framework | Already added |
| `requests` | Synchronous HTTP POST to backend | Already added |
| `python-dotenv` | Load `.env` at module import time | Already added |

---

## 10. Open Questions / Assumptions

| # | Question | Current Assumption |
|---|---|---|
| Q1 | Does `POST /api/chat` exist in the backend? | Not yet implemented. This spec defines the frontend contract; the backend spec must match the request shape (`message` string) and response shape (`response` string). |
| Q2 | Does the API expect the full conversation history in each request, or just the latest message? | Assumed just the latest message (`{"message": "..."}`) for simplicity. If the backend requires history for context, update the request body to include a `history` array and add the spec amendment. |
| Q3 | What is the exact JSON key for the assistant reply in the response? | Assumed `"response"`. Verify against the backend chat schema when available. |
| Q4 | Should the chatbot redirect unauthenticated users to `/login`? | Out of scope for this spec. No auth guard is implemented. |
| Q5 | Is there a server-enforced rate limit on `/api/chat`? | Unknown. The frontend surfaces a 429 message if the backend returns one. |
| Q6 | Should conversation history persist if the user navigates away and back? | No. NiceGUI re-invokes the page function on each client visit; state resets per session. |
| Q7 | Should the input support multi-line messages? | Single-line `ui.input` only. Multi-line `ui.textarea` is out of scope unless the user story is updated. |
