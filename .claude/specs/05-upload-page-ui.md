# Feature Spec: Upload Page UI

**ID:** `05-upload-page-ui`
**Status:** Ready for implementation
**Route:** `/upload`
**Source story:** Document upload page — select TXT/PDF/Excel files, convert to Base64, POST to `/api/upload`, redirect to `/chatbot`

---

## 1. Overview

A document upload page that allows authenticated users to select one or more TXT, PDF, or Excel (.xls/.xlsx) files, previews the selection with file details, and submits Base64-encoded file content to the backend. The page provides clear feedback at every stage: a validation error for unsupported file types, a staged-file list with per-file removal, an indeterminate progress bar while the upload request is in flight, and automatic navigation to `/chatbot` on success.

Unlike the auth pages (login/signup), this page renders the standard app header but omits the sidebar, keeping the upload flow focused.

---

## 2. Functional Requirements

### FR-01 — Route Registration
The upload page must be registered at the `/upload` route using the `@ui.page('/upload')` decorator. The module `pages.upload` must be imported in `frontend/main.py` so the decorator fires before `ui.run()` is called.

### FR-02 — Page Shell
The page must render a standard app header containing the application name "Decision Intelligence" (`text-xl font-bold text-slate-800`), styled with `bg-white border-b border-slate-200 p-4`. No left sidebar. All main content sits inside a centered column: `w-full max-w-2xl mx-auto p-6 flex flex-col gap-6`.

### FR-03 — File Selection via NiceGUI Upload Component
File selection must use NiceGUI's `ui.upload` component with:
- `multiple=True` — allow selecting multiple files in a single dialog open
- `accept='.txt,.pdf,.xls,.xlsx'` — restrict the OS file picker to supported types at the browser level
- `auto_upload=True` — files transfer to NiceGUI's server immediately on selection, which triggers `on_upload` per file
- `on_upload=_handle_file_selected` — handler fires once per received file

The component must be wrapped in a visually distinct drop-zone card to communicate its purpose (see Section 6.1).

### FR-04 — Per-File Selection Handler
`_handle_file_selected(e: UploadEventArguments)` is called once for each file the user selects. It must:

1. **Clear the previous validation error** by setting the validation error label to invisible.
2. **Validate the file extension** by checking `e.name.rsplit('.', 1)[-1].lower()` is in `{'txt', 'pdf', 'xls', 'xlsx'}`. This guards against browsers that ignore the `accept` attribute.
3. **If invalid:** show the validation error label (FR-06) with the message `"Unsupported file type: <filename>. Only TXT, PDF, XLS, and XLSX files are accepted."` and return without adding the file to the list.
4. **If valid:**
   a. Read all bytes: `raw = e.content.read()`
   b. Encode: `content_b64 = base64.b64encode(raw).decode('utf-8')`
   c. Append to the local `staged_files` list:
      ```python
      {"filename": e.name, "content": content_b64, "size": len(raw)}
      ```
5. **Refresh the staged file list UI** (FR-05).
6. **Update the Upload button state** (FR-07).

### FR-05 — Staged File List Display
A `ui.column` container (`file_list_column`) always exists in the DOM and displays the current staged files. It is cleared and rebuilt on every call to `_refresh_file_list()`.

Each file row must display (in a `ui.row` with `items-center gap-3 w-full`):
- **File name:** `ui.label(file['filename'])` with `text-sm font-medium text-slate-800 flex-1`
- **File size:** `ui.label(_format_file_size(file['size']))` with `text-xs text-slate-500`
- **Remove button:** `ui.button(icon='close')` with `text-slate-400 hover:text-red-500` that removes the entry from `staged_files` by index, calls `_refresh_file_list()`, and calls `_update_upload_button()`.

When `staged_files` is empty, `file_list_column` renders nothing (no placeholder text required).

### FR-06 — Validation Error Display
A `ui.label` (`validation_error_label`) sits below the upload component inside the drop-zone card. It must:
- Be empty on page load with class `invisible` so it occupies space without being seen
- Have classes `text-red-500 text-sm`
- Toggle between `invisible` and `visible` via `.classes(add=..., remove=...)` — never `display:none` — to prevent layout shift
- Clear automatically at the start of every `_handle_file_selected` call (before the extension check)

### FR-07 — Upload Button State
The Upload button (`upload_btn`) must follow these rules:
- **Disabled** on page load (`upload_btn.disable()` on initialization)
- **Enabled** when `len(staged_files) >= 1` (`upload_btn.enable()`)
- **Disabled** immediately when the Upload button is clicked and the request begins
- **Re-enabled** if the request fails (any non-2xx or exception)
- **Re-evaluated** when a file is removed from `staged_files` (disable again if list becomes empty)

The function `_update_upload_button()` encapsulates this logic and is called after every list mutation.

### FR-08 — Auth Token Retrieval
Before issuing the upload POST, the page must retrieve the JWT from `sessionStorage`:
```python
token = await ui.run_javascript("sessionStorage.getItem('auth_token') || ''")
```
This token is passed as `Authorization: Bearer <token>` in the request headers.

Because `ui.run_javascript()` is a coroutine, `_handle_upload_click` **must be declared `async`**.

### FR-09 — Upload API Call
`_handle_upload_click()` must:
1. Disable `upload_btn`.
2. Make `progress_bar` visible: `progress_bar.set_visibility(True)`.
3. Hide any previous upload error: `upload_error_label.classes(add='invisible', remove='visible')`.
4. Retrieve the auth token (FR-08).
5. Send a synchronous `POST` request via `requests`:
   - **URL:** `{API_URL}/api/upload`
   - **Headers:** `{"Authorization": f"Bearer {token}", "Content-Type": "application/json"}`
   - **Body:** `json={"files": staged_files}`
6. Handle response per FR-10 / FR-11.
7. **Always** call `progress_bar.set_visibility(False)` after the request completes, regardless of outcome.

### FR-10 — Success Handling
If `200 <= response.status_code < 300`:
1. Hide the progress bar.
2. Navigate to `/chatbot` via `ui.navigate.to('/chatbot')`.

### FR-11 — Error Handling
If the response is outside the 2xx range or an exception occurs:
1. Hide the progress bar.
2. Re-enable `upload_btn`.
3. Set `upload_error_label` to the appropriate message and make it `visible`:

| Condition | Message |
|---|---|
| `401 Unauthorized` | `"Session expired. Please log in again."` |
| `413 Payload Too Large` | `"Files are too large. Reduce the total size and try again."` |
| Any other 4xx | `detail` from response JSON body, or `"Upload failed. Please try again."` |
| 5xx | `"Server error. Please try again later."` |
| `requests.ConnectionError` | `"Could not reach the server. Check your connection."` |
| `requests.Timeout` | `"Could not reach the server. Check your connection."` |
| Any other exception | `"An unexpected error occurred. Please try again."` |

---

## 3. Non-Functional Requirements

### NFR-01 — Styling
All styling must use Tailwind utility classes via `.classes()`. No inline `style=` attributes and no custom CSS files unless an effect is impossible with Tailwind alone.

### NFR-02 — Responsiveness
The upload card must render correctly at desktop (1280px+) and tablet (768px) widths. Use `w-full max-w-2xl` on the content container. File rows must not overflow horizontally.

### NFR-03 — Modularity
Do not write a monolithic `@ui.page` function body. At minimum, define these named helper functions:

| Function | Responsibility |
|---|---|
| `_build_header()` | Renders the app header |
| `_build_upload_zone(content_col)` | Renders the drop-zone card + `ui.upload` + validation error label |
| `_build_file_list(content_col)` | Creates and returns the `file_list_column` container |
| `_build_actions(content_col)` | Renders the upload error label, progress bar, and Upload button |
| `_refresh_file_list()` | Clears and rebuilds `file_list_column` from `staged_files` |
| `_update_upload_button()` | Enables or disables `upload_btn` based on `staged_files` length |
| `_format_file_size(size_bytes: int) -> str` | Returns human-readable size (e.g., `"42 KB"`, `"1.3 MB"`) |

### NFR-04 — Environment Variable Isolation
`API_URL` must be loaded at module import time using `load_dotenv()` and `os.getenv('API_URL', 'http://localhost:8000')`. It must not be hardcoded.

### NFR-05 — Per-Client State Isolation
`staged_files` and all UI references (`file_list_column`, `upload_btn`, `progress_bar`, `validation_error_label`, `upload_error_label`) must be **local variables** inside the `@ui.page` function body — not module-level — so each browser session gets its own independent state. NiceGUI calls the decorated function once per client connection.

### NFR-06 — Progress Bar Behavior
Use `ui.linear_progress(value=None)` for an indeterminate (animated) bar. Initialize with `set_visibility(False)`. Show only while the POST request is in flight. Hide in both success and error paths before any navigation or error display.

### NFR-07 — Error Label Persistence
Both `validation_error_label` and `upload_error_label` must always be allocated DOM space (`.classes('invisible')` / `.classes('visible')`) to prevent layout shift when errors appear or disappear.

### NFR-08 — Async Handler Scope
Only `_handle_upload_click` needs to be `async` (because it awaits `ui.run_javascript()`). `_handle_file_selected` and all other handlers remain synchronous.

---

## 4. Acceptance Criteria

| ID | Criterion | How to verify |
|---|---|---|
| AC-01 | Navigating to `http://localhost:8080/upload` renders the page without error | Manual browser check |
| AC-02 | The Upload button is disabled on page load | Observe button state before selecting files |
| AC-03 | The file picker dialog is restricted to TXT, PDF, XLS, XLSX files | Open the file picker and observe the type filter in the OS dialog |
| AC-04 | Selecting a valid `.txt` file adds it to the staged list and enables the Upload button | Select a `.txt` file |
| AC-05 | Selecting a valid `.pdf` file adds it to the staged list | Select a `.pdf` file |
| AC-06 | Selecting valid `.xls` and `.xlsx` files adds them to the staged list | Select each file type |
| AC-07 | Selecting multiple files in one picker operation adds all of them to the staged list | Select 3+ files at once |
| AC-08 | Selecting an unsupported file type shows the validation error message containing the filename | Force-select an unsupported type |
| AC-09 | Selecting a valid file after an invalid one clears the validation error | Follow AC-08 with a valid file selection |
| AC-10 | Each staged file row shows the filename, human-readable file size, and a remove button | Inspect the file list after selection |
| AC-11 | Clicking the remove button on a staged file removes only that file from the list | Remove one file from a multi-file selection |
| AC-12 | Removing all staged files disables the Upload button | Remove every staged file |
| AC-13 | Clicking Upload disables the Upload button and shows the progress bar | Click Upload and immediately observe state |
| AC-14 | The Upload request body is `{"files": [{filename, content, size}, ...]}` with valid Base64 `content` | Inspect via backend logs or network tab; decode Base64 to verify byte integrity |
| AC-15 | The request includes `Authorization: Bearer <token>` from `sessionStorage` | Inspect the request headers in the network tab |
| AC-16 | A 2xx response hides the progress bar and navigates to `/chatbot` | Upload against a working backend |
| AC-17 | A 401 response shows "Session expired. Please log in again." and re-enables the button | Simulate a 401 from the backend |
| AC-18 | A 413 response shows the file-size error message | Simulate a 413 from the backend |
| AC-19 | A 5xx response shows "Server error. Please try again later." | Simulate a 500 from the backend |
| AC-20 | A network error shows "Could not reach the server. Check your connection." | Stop the backend and attempt upload |
| AC-21 | After any error, the progress bar is hidden and the Upload button is re-enabled | Trigger any error and observe state |
| AC-22 | The page renders without horizontal overflow at 768px viewport width | Resize the browser to 768px |

---

## 5. Out of Scope

The following are explicitly excluded and must not be implemented:

- Drag-and-drop file upload (not required even if `ui.upload` supports it natively)
- File content preview (showing PDF or text before upload)
- Per-file upload progress (only a single overall progress bar is required)
- Client-side file size validation (the backend returns 413 if the payload exceeds its limit)
- Resumable or chunked uploads
- Authentication guard on `/upload` (no redirect to `/login` if the token is absent — a separate concern)
- The `/chatbot` page itself (this spec only redirects to it)
- Any UI related to file metadata beyond filename and size (no MIME-type display, no icon per file type)

---

## 6. Design Rules

### 6.1 Layout Skeleton

```
┌────────────────────── w-screen min-h-screen bg-slate-50 ──────────────────────┐
│                                                                                │
│  ┌── Header ──────────────────────────────────────────────────────────────┐   │
│  │  bg-white border-b border-slate-200 p-4                               │   │
│  │  [Decision Intelligence]   text-xl font-bold text-slate-800           │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
│                                                                                │
│       ┌─── max-w-2xl w-full mx-auto p-6 flex flex-col gap-6 ───────────┐     │
│       │                                                                  │     │
│       │  [Upload Documents]        text-xl font-semibold text-slate-900 │     │
│       │  [Select files subtitle]   text-sm text-slate-500               │     │
│       │                                                                  │     │
│       │  ┌── Drop-zone Card ──────────────────────────────────────────┐ │     │
│       │  │  bg-white border-2 border-dashed border-slate-300          │ │     │
│       │  │  rounded-xl p-8 flex flex-col items-center gap-4           │ │     │
│       │  │                                                            │ │     │
│       │  │  [upload icon]    text-5xl text-slate-300                 │ │     │
│       │  │  [ui.upload]      (NiceGUI component, multiple, accept)   │ │     │
│       │  │  [accepted types] text-xs text-slate-400                  │ │     │
│       │  │  [validation err] text-red-500 text-sm invisible          │ │     │
│       │  └────────────────────────────────────────────────────────────┘ │     │
│       │                                                                  │     │
│       │  ┌── Staged File List ────────────────────────────────────────┐ │     │
│       │  │  bg-white border border-slate-200 rounded-lg p-4          │ │     │
│       │  │  (shown when staged_files is non-empty; empty otherwise)  │ │     │
│       │  │  ┌─ file row ──────────────────────────────────────────┐  │ │     │
│       │  │  │  [filename flex-1]  [size text-xs]  [× close btn]  │  │ │     │
│       │  │  └──────────────────────────────────────────────────── ┘  │ │     │
│       │  └────────────────────────────────────────────────────────────┘ │     │
│       │                                                                  │     │
│       │  [upload error label]   text-red-500 text-sm invisible          │     │
│       │  [progress bar]         ui.linear_progress(value=None) hidden   │     │
│       │  [Upload button]        w-full bg-blue-600 text-white disabled  │     │
│       │                                                                  │     │
│       └──────────────────────────────────────────────────────────────────┘     │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Color & Typography Tokens

| Element | Tailwind classes |
|---|---|
| Page background | `bg-slate-50` |
| Header | `bg-white border-b border-slate-200 p-4` |
| App title | `text-xl font-bold text-slate-800` |
| Page heading | `text-xl font-semibold text-slate-900` |
| Page subtitle | `text-sm text-slate-500` |
| Drop-zone card | `bg-white border-2 border-dashed border-slate-300 rounded-xl p-8` |
| Upload icon | `text-5xl text-slate-300` |
| Accepted-types hint | `text-xs text-slate-400` |
| File list card | `bg-white border border-slate-200 rounded-lg p-4` |
| File name | `text-sm font-medium text-slate-800 flex-1` |
| File size | `text-xs text-slate-500` |
| Remove button | `text-slate-400 hover:text-red-500` (flat, icon-only) |
| Validation error | `text-red-500 text-sm` + `invisible`/`visible` |
| Upload error | `text-red-500 text-sm` + `invisible`/`visible` |
| Upload button | `w-full bg-blue-600 text-white hover:bg-blue-700` |

### 6.3 Spacing & Structure

- Content column outer padding: `p-6`
- Content column gap between sections: `gap-6`
- Drop-zone card padding: `p-8`, internal gap: `gap-4`, children centered: `items-center`
- File list card padding: `p-4`
- File row gap: `gap-3`, alignment: `items-center w-full`

### 6.4 Component Naming Conventions

- Page module file: `frontend/pages/upload.py`
- `@ui.page('/upload')` function name: `upload_page()`
- State variables (local to `upload_page`): `staged_files`, `file_list_column`, `validation_error_label`, `upload_error_label`, `upload_btn`, `progress_bar`
- Helper functions: `_build_header`, `_build_upload_zone`, `_build_file_list`, `_build_actions`, `_refresh_file_list`, `_update_upload_button`, `_format_file_size`
- Event handlers: `_handle_file_selected` (sync), `_handle_upload_click` (async)

---

## 7. API Contract

### Endpoint
`POST {API_URL}/api/upload`

### Request Headers
```
Authorization: Bearer <jwt-from-sessionStorage>
Content-Type: application/json
```

### Request Body
```json
{
  "files": [
    {
      "filename": "document.pdf",
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

The `content` field is a Base64-encoded string of the raw file bytes produced by:
```python
base64.b64encode(raw_bytes).decode('utf-8')
```

### Success Response
- **Status:** `200 OK` or `201 Created`
- **Body:** Not consumed by the frontend — any 2xx status triggers the redirect to `/chatbot`.

### Error Responses

| Status | Meaning | Frontend action |
|---|---|---|
| `401 Unauthorized` | Token missing or expired | `"Session expired. Please log in again."` |
| `413 Payload Too Large` | Total payload exceeds server limit | `"Files are too large. Reduce the total size and try again."` |
| `400 Bad Request` | Malformed request | `detail` from JSON, or `"Upload failed. Please try again."` |
| `422 Unprocessable Entity` | Schema mismatch | `detail` from JSON, or `"Upload failed. Please try again."` |
| `500 Internal Server Error` | Backend failure | `"Server error. Please try again later."` |
| `requests.ConnectionError` | Backend unreachable | `"Could not reach the server. Check your connection."` |
| `requests.Timeout` | Request timed out | `"Could not reach the server. Check your connection."` |
| Any other exception | Unexpected failure | `"An unexpected error occurred. Please try again."` |

### Accepted File Types (Client-Side Validation)

| Extension | Browser `accept` value |
|---|---|
| `.txt` | included in `accept='.txt,.pdf,.xls,.xlsx'` |
| `.pdf` | included |
| `.xls` | included |
| `.xlsx` | included |

Extension validation is re-checked in `_handle_file_selected` regardless of the browser filter.

### Environment Variable

| Variable | Default | Source |
|---|---|---|
| `API_URL` | `http://localhost:8000` | `.env` in project root |

---

## 8. File & Module Layout

```
frontend/
├── main.py                   # add: import pages.upload  # noqa: F401
└── pages/
    ├── signup.py             # existing
    ├── login.py              # existing
    └── upload.py             # new — @ui.page('/upload'), self-contained module
```

`frontend/main.py` must contain:
```python
import pages.upload  # noqa: F401 — registers @ui.page('/upload')
```
alongside the existing auth page imports, before `ui.run()` is called.

---

## 9. Dependencies

All required packages are already tracked in `pyproject.toml`. No new dependencies are needed.

| Package | Purpose | Status |
|---|---|---|
| `nicegui` | UI framework and `ui.upload` component | Already added |
| `requests` | Synchronous HTTP POST to backend | Already added |
| `python-dotenv` | Load `.env` at module import time | Already added |
| `base64` | Encode file bytes to Base64 string | Python standard library |

---

## 10. Open Questions / Assumptions

| # | Question | Current Assumption |
|---|---|---|
| Q1 | Does the `POST /api/upload` endpoint exist in the backend? | Not yet implemented. This spec defines the frontend contract; the backend spec must match the request shape (`files` array with `filename`, `content`, `size`). |
| Q2 | What exact JSON field names does the backend expect? | `files`, each element with `filename` (str), `content` (Base64 str), `size` (int). Verify against the backend upload schema when available. |
| Q3 | Is there a server-enforced maximum payload size? | Unknown. The frontend surfaces a 413 message if the server rejects the payload. |
| Q4 | Should `/upload` redirect unauthenticated users to `/login`? | Out of scope for this spec. No auth guard is implemented. |
| Q5 | Does `/chatbot` exist? | Assumed to exist or will exist. The spec navigates there unconditionally on 2xx. |
| Q6 | Should `staged_files` persist if the user navigates away and back? | No. NiceGUI re-invokes the page function on each client visit; state resets per session. |
| Q7 | Should the `size` field in the payload be bytes, KB, or MB? | Raw bytes (int), matching `len(raw_bytes)`. The backend is responsible for interpreting units. |
