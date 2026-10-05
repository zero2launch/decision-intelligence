# Test Spec: Upload Page UI

**ID:** `05-upload-page-test-ui`
**Status:** Ready for implementation
**Covers spec:** [05-upload-page-ui.md](05-upload-page-ui.md)
**Test file location:** `frontend/tests/test_upload_page.py`

---

## 1. Overview

This document defines the full test plan for the upload page UI (`frontend/pages/upload.py`). Tests cover page rendering, file extension validation, Base64 encoding correctness, staged file list management, upload button state, API integration, progress bar behaviour, authentication header handling, security, and edge cases.

The test suite uses **pytest** with **NiceGUI's `User` testing class** (`nicegui.testing.User`) for browser-level interaction, **`unittest.mock.patch`** to intercept `requests.post` and `ui.run_javascript` calls, and direct handler invocation for testing file-processing logic in isolation.

> **Key differences from login/signup test suites:**
> - File upload events must be simulated by constructing mock `UploadEventArguments` objects and invoking `_handle_file_selected` directly via the captured handler reference.
> - `_handle_upload_click` is `async` and awaits `ui.run_javascript()` — mock this with `AsyncMock`.
> - The request body contains a `files` array with Base64-encoded content — tests must verify encoding correctness.
> - The Upload button state depends on the `staged_files` list, not text inputs — tests use file injection rather than `.type()`.

---

## 2. Test Framework & Setup

### 2.1 Dependencies

| Package | Purpose |
|---|---|
| `pytest` | Test runner |
| `pytest-asyncio` | Required by NiceGUI's async `User` fixture |
| `nicegui[testing]` | `nicegui.testing.User` for page interaction |
| `unittest.mock` | `patch`, `MagicMock`, `AsyncMock` for mocking |

All are already present from the signup/login test suites. No new packages required.

### 2.2 Fixture Pattern

```python
# frontend/tests/conftest.py  (already exists — no changes needed)
import pytest
from nicegui.testing import User

@pytest.fixture
def user(user: User):
    return user
```

All test functions receive the `user` fixture. Core interaction methods used: `user.open('/upload')`, `user.find('Upload').click()`, `user.should_see('...')`, `user.should_not_see('...')`.

### 2.3 Simulating File Upload Events

NiceGUI's `ui.upload` component fires `on_upload` with an `UploadEventArguments` object. Since the test harness cannot open a real OS file dialog, file events are injected by constructing a mock argument object and calling the handler directly.

**Pattern — create a fake upload event:**

```python
from io import BytesIO
from unittest.mock import MagicMock

def _make_upload_event(filename: str, content: bytes) -> MagicMock:
    e = MagicMock()
    e.name = filename
    e.content = BytesIO(content)
    e.type = "text/plain"
    return e
```

**Pattern — capture and invoke the handler:**

```python
# Capture the handler reference from the upload component
# after the page is rendered, then call it directly:
upload_component = user.find(nicegui.ui.upload)  # or equivalent selector
upload_component.props['on_upload'](_make_upload_event('test.txt', b'hello'))
```

> Alternatively, if NiceGUI's `User` exposes a file-upload simulation method, use that instead. Check the NiceGUI `testing` API version in use before implementing.

### 2.4 Mocking `ui.run_javascript` (Async Token Retrieval)

`_handle_upload_click` awaits `ui.run_javascript(...)` to retrieve the JWT from `sessionStorage`. Mock it with `AsyncMock`:

```python
from unittest.mock import patch, AsyncMock

with patch('nicegui.ui.run_javascript', new_callable=AsyncMock) as mock_js:
    mock_js.return_value = 'test-jwt-token'
    # ... trigger upload click
```

### 2.5 Mocking `requests.post`

```python
from unittest.mock import patch, MagicMock

with patch('frontend.pages.upload.requests.post') as mock_post:
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
    # ... test body
```

### 2.6 Environment Variable Isolation

```python
# At the top of test_upload_page.py, before importing the page module
import os
os.environ.setdefault('API_URL', 'http://test-backend:8000')

import frontend.pages.upload  # noqa: F401
```

Tests that need a different `API_URL`:
```python
with patch('frontend.pages.upload.API_URL', 'http://custom-host:9000'):
    ...
```

---

## 3. Unit Test Cases

### 3.1 Page Rendering

#### UT-R01 — Page loads at `/upload` without error
- **Setup:** Open `/upload`.
- **Assert:** Page renders without exception.

#### UT-R02 — App header displays "Decision Intelligence"
- **Setup:** Open `/upload`.
- **Assert:** Element containing "Decision Intelligence" is visible in the header.

#### UT-R03 — Page title "Upload Documents" is visible
- **Setup:** Open `/upload`.
- **Assert:** Element containing "Upload Documents" is present.

#### UT-R04 — Page subtitle is visible
- **Setup:** Open `/upload`.
- **Assert:** A subtitle element containing guidance text (e.g., "Select files to upload") is visible.

#### UT-R05 — `ui.upload` component is rendered
- **Setup:** Open `/upload`.
- **Assert:** A `ui.upload` element exists on the page.

#### UT-R06 — Accepted file types hint is visible
- **Setup:** Open `/upload`.
- **Assert:** Text indicating accepted types (TXT, PDF, XLS, XLSX) is visible in the drop-zone area.

#### UT-R07 — Upload button is rendered with label "Upload"
- **Setup:** Open `/upload`.
- **Assert:** A button with text "Upload" exists.

#### UT-R08 — Upload button is disabled on page load
- **Setup:** Open `/upload`. Do not select any files.
- **Assert:** "Upload" button has `disabled` attribute / is not interactable.

#### UT-R09 — Progress bar is not visible on page load
- **Setup:** Open `/upload`.
- **Assert:** The `ui.linear_progress` element is not visible (has `display:none` or `visibility:hidden`).

#### UT-R10 — Validation error label exists but is invisible on page load
- **Setup:** Open `/upload`.
- **Assert:** Validation error label element exists in the DOM with the `invisible` class. No error text is displayed.

#### UT-R11 — Upload error label exists but is invisible on page load
- **Setup:** Open `/upload`.
- **Assert:** Upload error label element exists in the DOM with the `invisible` class.

#### UT-R12 — Staged file list container is empty on page load
- **Setup:** Open `/upload`.
- **Assert:** The `file_list_column` container contains no file rows.

#### UT-R13 — Page renders a standard app header (not the auth-page full-screen layout)
- **Setup:** Open `/upload`.
- **Assert:** A header element is present. The page does NOT use the `w-screen h-screen flex items-center justify-center` full-screen centering used by login/signup.

---

### 3.2 File Extension Validation

All tests in this section invoke `_handle_file_selected` directly with a mock `UploadEventArguments`.

#### UT-V01 — `.txt` file is accepted
- **Setup:** Inject upload event with `filename='report.txt'`, content=`b'hello'`.
- **Assert:** No validation error displayed; file added to `staged_files`.

#### UT-V02 — `.pdf` file is accepted
- **Setup:** Inject upload event with `filename='document.pdf'`, content=`b'%PDF-1.4...'`.
- **Assert:** No validation error displayed; file added to `staged_files`.

#### UT-V03 — `.xls` file is accepted
- **Setup:** Inject upload event with `filename='data.xls'`, content=`b'\xD0\xCF\x11\xE0...'`.
- **Assert:** No validation error displayed; file added to `staged_files`.

#### UT-V04 — `.xlsx` file is accepted
- **Setup:** Inject upload event with `filename='spreadsheet.xlsx'`, content=`b'PK\x03\x04...'`.
- **Assert:** No validation error displayed; file added to `staged_files`.

#### UT-V05 — `.jpg` file is rejected
- **Setup:** Inject upload event with `filename='photo.jpg'`, content=`b'\xFF\xD8\xFF'`.
- **Assert:** Validation error label becomes visible; message contains "photo.jpg". File not added to `staged_files`.

#### UT-V06 — `.docx` file is rejected
- **Setup:** Inject upload event with `filename='letter.docx'`, content=`b'PK\x03\x04'`.
- **Assert:** Validation error label becomes visible; message contains "letter.docx". File not added to `staged_files`.

#### UT-V07 — `.exe` file is rejected
- **Setup:** Inject upload event with `filename='program.exe'`, content=`b'MZ\x90\x00'`.
- **Assert:** Validation error label becomes visible. File not added to `staged_files`.

#### UT-V08 — `.csv` file is rejected
- **Setup:** Inject upload event with `filename='data.csv'`, content=`b'a,b,c'`.
- **Assert:** Validation error label becomes visible. File not added to `staged_files`.

#### UT-V09 — Extension check is case-insensitive (`.PDF` accepted)
- **Setup:** Inject upload event with `filename='DOCUMENT.PDF'`, content=`b'%PDF'`.
- **Assert:** File accepted; no validation error shown.

#### UT-V10 — Extension check is case-insensitive (`.TXT` accepted)
- **Setup:** Inject upload event with `filename='NOTES.TXT'`, content=`b'text'`.
- **Assert:** File accepted; no validation error shown.

#### UT-V11 — Extension check is case-insensitive (`.XLS` and `.XLSX` accepted)
- **Setup:** Inject upload events with `filename='DATA.XLS'` and `filename='DATA.XLSX'`.
- **Assert:** Both files accepted; no validation error shown.

#### UT-V12 — File with multiple dots uses the last extension
- **Setup:** Inject upload event with `filename='report.2024.final.pdf'`, content=`b'%PDF'`.
- **Assert:** File accepted (`.pdf` is the last segment); no validation error.

#### UT-V13 — File with no extension is rejected
- **Setup:** Inject upload event with `filename='README'`, content=`b'readme content'`.
- **Assert:** Validation error label visible. File not added to `staged_files`.

#### UT-V14 — Validation error message contains the rejected filename
- **Setup:** Inject upload event with `filename='badfile.mp4'`, content=`b'\x00'`.
- **Assert:** Validation error label text contains `"badfile.mp4"`.

#### UT-V15 — Validation error message mentions supported file types
- **Setup:** Inject upload event with `filename='image.png'`, content=`b'\x89PNG'`.
- **Assert:** Validation error label text mentions "TXT", "PDF", "XLS", and "XLSX".

#### UT-V16 — Validation error clears on the next file selection attempt (valid file)
- **Setup:** Inject an invalid file (error appears). Then inject a valid `.txt` file.
- **Assert:** Validation error label becomes invisible again.

#### UT-V17 — Validation error clears on the next file selection attempt (another invalid file)
- **Setup:** Inject `filename='bad.jpg'` (error appears with "bad.jpg"). Inject `filename='worse.mp4'` (second invalid file).
- **Assert:** Validation error label now shows message for "worse.mp4", not the stale "bad.jpg" message.

---

### 3.3 Base64 Encoding

#### UT-B01 — Text file bytes are Base64-encoded correctly
- **Setup:** Inject upload event with `filename='hello.txt'`, `content=b'Hello, World!'`.
- **Assert:** The `content` field stored in `staged_files[0]` equals `base64.b64encode(b'Hello, World!').decode('utf-8')`.

#### UT-B02 — Binary (PDF) file bytes are Base64-encoded correctly
- **Setup:** Inject upload event with `filename='doc.pdf'`, `content=b'\x00\x01\x02\xFF\xFE\xFD'`.
- **Assert:** The stored Base64 string, when decoded, exactly matches the original bytes.

#### UT-B03 — Base64 string is valid (no padding or character errors)
- **Setup:** Inject upload event with `filename='data.xlsx'`, `content=b'any binary content'`.
- **Assert:** `base64.b64decode(staged_files[0]['content'])` does not raise an exception.

#### UT-B04 — Empty file produces a valid (empty) Base64 string
- **Setup:** Inject upload event with `filename='empty.txt'`, `content=b''`.
- **Assert:** The stored `content` equals `""` (Base64 of empty bytes). No exception raised.

#### UT-B05 — `size` field records the original byte count
- **Setup:** Inject upload event with `filename='data.txt'`, `content=b'12345'` (5 bytes).
- **Assert:** `staged_files[0]['size']` equals `5`.

---

### 3.4 Staged File List Management

#### UT-L01 — Selecting one valid file adds it to the staged list
- **Setup:** Open `/upload`. Inject a valid `.txt` file upload event.
- **Assert:** `file_list_column` displays exactly one file row containing the filename.

#### UT-L02 — Selecting two valid files adds both to the staged list
- **Setup:** Open `/upload`. Inject two valid file upload events.
- **Assert:** `file_list_column` displays two file rows.

#### UT-L03 — Selecting three valid files adds all three to the staged list
- **Setup:** Inject three valid file upload events.
- **Assert:** `file_list_column` displays three file rows.

#### UT-L04 — Each file row displays the correct filename
- **Setup:** Inject `filename='report.pdf'`, `content=b'content'`.
- **Assert:** A row containing the text "report.pdf" is visible in the file list.

#### UT-L05 — Each file row displays a human-readable file size
- **Setup:** Inject `filename='file.txt'`, `content=b'x' * 2048` (2 KB).
- **Assert:** The file row contains the formatted size string (e.g., "2.0 KB").

#### UT-L06 — Each file row displays a remove button
- **Setup:** Inject a valid file upload event.
- **Assert:** The file row contains a button with icon "close".

#### UT-L07 — Clicking the remove button removes only that file from the list
- **Setup:** Inject two files: `file_a.txt` and `file_b.pdf`. Click the remove button on `file_a.txt`'s row.
- **Assert:** The list contains only one row displaying `file_b.pdf`. `staged_files` has one entry.

#### UT-L08 — Removing the last file leaves the staged list empty
- **Setup:** Inject one file. Click its remove button.
- **Assert:** `file_list_column` contains no file rows. `staged_files` is empty.

#### UT-L09 — Invalid file selection does not add an entry to the staged list
- **Setup:** Inject `filename='photo.jpg'`, `content=b'\xFF\xD8\xFF'`.
- **Assert:** `file_list_column` remains empty. `staged_files` remains empty.

---

### 3.5 Upload Button State

#### UT-UB01 — Upload button disabled on page load (no files)
- **Setup:** Open `/upload`. Make no file selections.
- **Assert:** "Upload" button is disabled.

#### UT-UB02 — Upload button enabled after adding one valid file
- **Setup:** Open `/upload`. Inject one valid `.txt` file.
- **Assert:** "Upload" button is enabled.

#### UT-UB03 — Upload button enabled after adding multiple valid files
- **Setup:** Inject three valid files.
- **Assert:** "Upload" button is enabled.

#### UT-UB04 — Upload button remains disabled after an invalid file (no valid files in list)
- **Setup:** Open `/upload`. Inject one invalid `.jpg` file.
- **Assert:** "Upload" button is still disabled.

#### UT-UB05 — Upload button disabled again when the last file is removed
- **Setup:** Inject one valid file (button enables). Click the remove button.
- **Assert:** "Upload" button is disabled again.

#### UT-UB06 — Upload button remains enabled when one of two files is removed
- **Setup:** Inject two valid files. Remove one.
- **Assert:** "Upload" button is still enabled.

#### UT-UB07 — Upload button is disabled while upload request is in flight
- **Setup:** Inject a valid file. Mock `requests.post` with a blocking `side_effect`. Click "Upload".
- **Assert:** "Upload" button is disabled while the mock is blocking (before it returns).

#### UT-UB08 — Upload button re-enabled after upload failure
- **Setup:** Inject a valid file. Mock `requests.post` returning `status_code=500`. Click "Upload".
- **Assert:** "Upload" button is enabled after the handler completes.

---

### 3.6 Upload API Call

#### UT-A01 — POST is sent to the correct URL on click
- **Setup:** Inject a valid file. Mock `requests.post` returning 200. Click "Upload".
- **Assert:** `requests.post` was called with URL `http://test-backend:8000/api/upload`.

#### UT-A02 — Request body contains the `files` array
- **Setup:** Inject `filename='report.txt'`, `content=b'hello'`. Mock `requests.post` returning 200. Click "Upload".
- **Assert:** `requests.post` called with `json` kwarg whose value has key `"files"`.

#### UT-A03 — Each file entry has `filename`, `content`, and `size` fields
- **Setup:** Inject `filename='report.txt'`, `content=b'hello'`. Mock `requests.post`. Click "Upload".
- **Assert:** `request_body["files"][0]` has keys `filename`, `content`, `size`.

#### UT-A04 — The `filename` field matches the original filename
- **Setup:** Inject `filename='my_report.pdf'`. Mock `requests.post`. Click "Upload".
- **Assert:** `request_body["files"][0]["filename"]` equals `"my_report.pdf"`.

#### UT-A05 — The `content` field is a valid Base64 string of the file bytes
- **Setup:** Inject `filename='data.txt'`, `content=b'test content'`. Mock `requests.post`. Click "Upload".
- **Assert:** `base64.b64decode(request_body["files"][0]["content"])` equals `b'test content'`.

#### UT-A06 — The `size` field matches the byte length of the file
- **Setup:** Inject `filename='data.txt'`, `content=b'abcde'` (5 bytes). Mock `requests.post`. Click "Upload".
- **Assert:** `request_body["files"][0]["size"]` equals `5`.

#### UT-A07 — Multiple staged files are all sent in a single request
- **Setup:** Inject two files: `a.txt` (3 bytes) and `b.pdf` (5 bytes). Mock `requests.post`. Click "Upload".
- **Assert:** `request_body["files"]` has length 2; both filenames are present.

#### UT-A08 — Request includes `Content-Type: application/json` header
- **Setup:** Inject a valid file. Mock `requests.post`. Click "Upload".
- **Assert:** `headers` kwarg includes `"Content-Type": "application/json"`.

#### UT-A09 — Request includes `Authorization: Bearer <token>` header
- **Setup:** Mock `ui.run_javascript` to return `"test-jwt-token"`. Inject a valid file. Mock `requests.post`. Click "Upload".
- **Assert:** `headers` kwarg includes `"Authorization": "Bearer test-jwt-token"`.

#### UT-A10 — `API_URL` is sourced from the environment variable
- **Setup:** Patch `frontend.pages.upload.API_URL` to `http://custom-host:9000`. Inject a valid file. Mock `requests.post`. Click "Upload".
- **Assert:** `requests.post` URL starts with `http://custom-host:9000`.

#### UT-A11 — Upload is only triggered by button click (not by file selection)
- **Setup:** Inject a valid file. Do NOT click "Upload".
- **Assert:** `requests.post` is **not** called.

---

### 3.7 Progress Bar Behaviour

#### UT-P01 — Progress bar is hidden on page load
- **Setup:** Open `/upload`.
- **Assert:** Progress bar element is not visible.

#### UT-P02 — Progress bar appears when upload starts
- **Setup:** Inject a valid file. Mock `requests.post` with a blocking call. Click "Upload".
- **Assert:** Progress bar is visible while the mock is blocking.

#### UT-P03 — Progress bar hidden after successful upload
- **Setup:** Inject a valid file. Mock `requests.post` returning 200. Click "Upload".
- **Assert:** Progress bar is not visible after the handler completes.

#### UT-P04 — Progress bar hidden after upload failure (4xx)
- **Setup:** Inject a valid file. Mock `requests.post` returning 401. Click "Upload".
- **Assert:** Progress bar is not visible after the handler completes.

#### UT-P05 — Progress bar hidden after upload failure (5xx)
- **Setup:** Inject a valid file. Mock `requests.post` returning 500. Click "Upload".
- **Assert:** Progress bar is not visible after the handler completes.

#### UT-P06 — Progress bar hidden after network error
- **Setup:** Inject a valid file. Mock `requests.post` raising `ConnectionError`. Click "Upload".
- **Assert:** Progress bar is not visible after the handler completes.

---

### 3.8 Success Handling

#### UT-S01 — Redirects to `/chatbot` on 200 response
- **Setup:** Inject a valid file. Mock `requests.post` returning 200. Click "Upload".
- **Assert:** Current URL path is `/chatbot`.

#### UT-S02 — Redirects to `/chatbot` on 201 response
- **Setup:** Inject a valid file. Mock `requests.post` returning 201. Click "Upload".
- **Assert:** Current URL path is `/chatbot`.

#### UT-S03 — No upload error label is shown on successful upload
- **Setup:** Inject a valid file. Mock `requests.post` returning 200. Click "Upload".
- **Assert:** Upload error label remains invisible before the redirect fires.

#### UT-S04 — Redirect fires even if response body has no JSON
- **Setup:** Inject a valid file. Mock `requests.post` returning `status_code=200` where `.json()` raises `ValueError("no body")`. Click "Upload".
- **Assert:** No `ValueError` propagates; redirect to `/chatbot` fires.

---

### 3.9 Error Handling

#### UT-E01 — 401 response shows "Session expired. Please log in again."
- **Setup:** Inject a valid file. Mock `requests.post` returning 401. Click "Upload".
- **Assert:** Upload error label is visible and contains "Session expired. Please log in again."

#### UT-E02 — 413 response shows the file-size error message
- **Setup:** Inject a valid file. Mock `requests.post` returning 413. Click "Upload".
- **Assert:** Upload error label is visible and contains "Files are too large."

#### UT-E03 — 400 response shows `detail` from the response body
- **Setup:** Inject a valid file. Mock `requests.post` returning `status_code=400, json={"detail": "Invalid file format"}`. Click "Upload".
- **Assert:** Upload error label shows "Invalid file format".

#### UT-E04 — 400 response with no `detail` shows the generic fallback message
- **Setup:** Inject a valid file. Mock `requests.post` returning `status_code=400, json={}`. Click "Upload".
- **Assert:** Upload error label shows "Upload failed. Please try again."

#### UT-E05 — 422 response shows `detail` from the response body
- **Setup:** Inject a valid file. Mock `requests.post` returning `status_code=422, json={"detail": "Schema mismatch"}`. Click "Upload".
- **Assert:** Upload error label shows "Schema mismatch".

#### UT-E06 — 500 response shows "Server error. Please try again later."
- **Setup:** Inject a valid file. Mock `requests.post` returning 500. Click "Upload".
- **Assert:** Upload error label is visible and contains "Server error. Please try again later."

#### UT-E07 — `ConnectionError` shows "Could not reach the server. Check your connection."
- **Setup:** Inject a valid file. Mock `requests.post` raising `requests.exceptions.ConnectionError`. Click "Upload".
- **Assert:** Upload error label is visible and contains "Could not reach the server. Check your connection."

#### UT-E08 — `Timeout` shows "Could not reach the server. Check your connection."
- **Setup:** Inject a valid file. Mock `requests.post` raising `requests.exceptions.Timeout`. Click "Upload".
- **Assert:** Upload error label contains "Could not reach the server. Check your connection."

#### UT-E09 — Generic exception shows "An unexpected error occurred. Please try again."
- **Setup:** Inject a valid file. Mock `requests.post` raising `Exception("unexpected")`. Click "Upload".
- **Assert:** Upload error label contains "An unexpected error occurred. Please try again."

#### UT-E10 — Upload button re-enabled after 4xx error
- **Setup:** Inject a valid file. Mock `requests.post` returning 401. Click "Upload".
- **Assert:** "Upload" button is enabled after the handler completes.

#### UT-E11 — Upload button re-enabled after 5xx error
- **Setup:** Inject a valid file. Mock `requests.post` returning 500. Click "Upload".
- **Assert:** "Upload" button is enabled after the handler completes.

#### UT-E12 — Upload button re-enabled after network error
- **Setup:** Inject a valid file. Mock `requests.post` raising `ConnectionError`. Click "Upload".
- **Assert:** "Upload" button is enabled after the handler completes.

#### UT-E13 — Page remains on `/upload` after any error
- **Setup:** Inject a valid file. Mock `requests.post` returning 500. Click "Upload".
- **Assert:** Current URL path is `/upload`.

#### UT-E14 — Previous upload error is hidden when a new upload attempt begins
- **Setup:** Inject a valid file. Mock `requests.post` returning 500 (error label appears). Click "Upload" again (same mock). 
- **Assert:** Upload error label is hidden at the start of the second attempt (before the response is processed), not stale-visible throughout.

---

### 3.10 Helper Function: `_format_file_size`

These tests call `_format_file_size` directly — no page rendering or mocking required.

#### UT-F01 — 0 bytes renders as "0 Bytes"
- **Assert:** `_format_file_size(0)` returns `"0 Bytes"`.

#### UT-F02 — 1 byte renders as "1 Bytes" (or "1 Byte")
- **Assert:** `_format_file_size(1)` returns a string containing "1" and "Byte".

#### UT-F03 — 500 bytes renders as "500 Bytes"
- **Assert:** `_format_file_size(500)` returns `"500 Bytes"`.

#### UT-F04 — 1024 bytes renders as "1.0 KB"
- **Assert:** `_format_file_size(1024)` returns `"1.0 KB"`.

#### UT-F05 — 1536 bytes renders as "1.5 KB"
- **Assert:** `_format_file_size(1536)` returns `"1.5 KB"`.

#### UT-F06 — 1048576 bytes (1 MiB) renders as "1.0 MB"
- **Assert:** `_format_file_size(1048576)` returns `"1.0 MB"`.

#### UT-F07 — 2621440 bytes (2.5 MiB) renders as "2.5 MB"
- **Assert:** `_format_file_size(2621440)` returns `"2.5 MB"`.

---

## 4. Integration Test Scenarios

These scenarios test multi-step user journeys end-to-end. Each scenario is a single test function.

### IT-01 — Full happy path: select, review, upload, redirect
```
1. Open /upload
2. Assert: "Upload" button is disabled; staged file list is empty
3. Inject file: report.pdf (valid)
4. Assert: file row appears in the list with "report.pdf" and its formatted size
5. Assert: "Upload" button is now enabled
6. [Mock: POST /api/upload → 200]
7. [Mock: ui.run_javascript → 'test-jwt']
8. Click "Upload"
9. Assert: progress bar was visible during the request
10. Assert: redirected to /chatbot
11. Assert: no error label was made visible during the flow
```

### IT-02 — Multi-file selection, then remove one, then upload
```
1. Open /upload
2. Inject three files: a.txt, b.pdf, c.xlsx
3. Assert: all three appear in the staged file list
4. Assert: "Upload" button is enabled
5. Click remove on b.pdf
6. Assert: only a.txt and c.xlsx remain in the list
7. [Mock: POST /api/upload → 200]
8. Click "Upload"
9. Assert: request body contains exactly 2 files: a.txt and c.xlsx
10. Assert: redirected to /chatbot
```

### IT-03 — Invalid file rejected, then valid file accepted
```
1. Open /upload
2. Inject file: image.jpg (invalid)
3. Assert: validation error label visible, mentions "image.jpg"
4. Assert: "Upload" button still disabled; staged list empty
5. Inject file: report.pdf (valid)
6. Assert: validation error label is now invisible
7. Assert: staged list shows "report.pdf"
8. Assert: "Upload" button is enabled
```

### IT-04 — Upload failure, then successful retry
```
1. Open /upload
2. Inject a valid file
3. [Mock: POST /api/upload → 500]
4. Click "Upload"
5. Assert: error message "Server error. Please try again later." is visible
6. Assert: progress bar is hidden
7. Assert: "Upload" button is re-enabled
8. Assert: page still at /upload
9. [Mock: POST /api/upload → 200]
10. Click "Upload" again
11. Assert: error label is hidden at the start of the second attempt
12. Assert: redirected to /chatbot
```

### IT-05 — Remove all staged files, button disables, re-add and upload
```
1. Open /upload
2. Inject two files: file1.txt and file2.xls
3. Assert: "Upload" button enabled
4. Remove file1.txt
5. Assert: "Upload" button still enabled (file2.xls remains)
6. Remove file2.xls
7. Assert: "Upload" button disabled; staged list empty
8. Inject file3.pdf
9. Assert: "Upload" button enabled again
10. [Mock: POST /api/upload → 200]
11. Click "Upload"
12. Assert: request body contains only file3.pdf
13. Assert: redirected to /chatbot
```

### IT-06 — Network failure, then recovery
```
1. Open /upload
2. Inject a valid file
3. [Mock: POST /api/upload → raises ConnectionError]
4. Click "Upload"
5. Assert: error label shows "Could not reach the server. Check your connection."
6. Assert: progress bar hidden; "Upload" button re-enabled
7. [Mock: POST /api/upload → 200]
8. Click "Upload" again
9. Assert: redirected to /chatbot
```

### IT-07 — Session expired (401) flow
```
1. Open /upload
2. Inject a valid file
3. [Mock: ui.run_javascript → '' (no token in sessionStorage)]
4. [Mock: POST /api/upload → 401]
5. Click "Upload"
6. Assert: error label shows "Session expired. Please log in again."
7. Assert: "Upload" button re-enabled
8. Assert: page remains at /upload
```

---

## 5. Security Tests

### 5.1 File Type Enforcement

#### ST-F01 — Extension check runs independently of browser `accept` attribute
- **Rationale:** Browsers on some platforms ignore `accept`. The handler must re-validate.
- **Setup:** Bypass the `ui.upload` component's `accept` filtering. Inject a `.exe` file directly to `_handle_file_selected`.
- **Assert:** Validation error shown; file not added to `staged_files`. `requests.post` is never called.

#### ST-F02 — MIME type spoofing does not bypass extension check
- **Rationale:** `e.type` from the upload event can be set by the client and is not trustworthy. Validation must rely on `e.name` (extension), not `e.type`.
- **Setup:** Inject upload event with `filename='malware.exe'`, `e.type='text/plain'` (spoofed MIME type).
- **Assert:** Validation error shown (`.exe` is invalid); file not staged.

#### ST-F03 — Double extension file is rejected based on the last segment
- **Rationale:** A file named `virus.exe.txt` must be accepted (last extension `.txt`). A file named `report.txt.exe` must be rejected (last extension `.exe`).
- **Setup A:** Inject `filename='virus.exe.txt'`.
- **Assert A:** File accepted (last extension is `.txt`).
- **Setup B:** Inject `filename='report.txt.exe'`.
- **Assert B:** Validation error shown (last extension is `.exe`).

#### ST-F04 — Null byte in filename does not bypass extension check
- **Rationale:** Some systems treat `file.txt\x00.exe` differently. The handler must not be confused by null bytes.
- **Setup:** Inject upload event with `filename='file.txt\x00.exe'`.
- **Assert:** Either rejected (null byte treated as part of the name, last clean extension is `.exe`) or accepted (if null byte is stripped and `.txt` remains). The key assertion is that no unhandled exception is raised.

### 5.2 Payload Integrity

#### ST-P01 — File content is encoded as Base64 and never sent as raw bytes
- **Rationale:** Raw bytes in a JSON body would break serialization.
- **Setup:** Inject `filename='data.pdf'`, `content=b'\x00\xFF\xFE\xFD'` (non-UTF-8 bytes). Mock `requests.post`. Click "Upload".
- **Assert:** `requests.post` receives the content as a valid Base64 string (no `UnicodeEncodeError` or JSON serialization error).

#### ST-P02 — `requests.post` is called with `json=` (not `data=`)
- **Rationale:** Using `data=` would send form-encoded or raw bytes rather than a JSON body.
- **Setup:** Inject a valid file. Mock `requests.post`. Click "Upload".
- **Assert:** `requests.post` call uses the `json` keyword argument, not `data`.

#### ST-P03 — Token from `sessionStorage` is not logged or displayed
- **Rationale:** JWT tokens must not leak into error messages or UI labels.
- **Setup:** Mock `ui.run_javascript` to return `"secret-jwt-token-abc123"`. Mock `requests.post` returning 500. Click "Upload".
- **Assert:** The error label text does NOT contain `"secret-jwt-token-abc123"`. The token is only sent in the Authorization header.

#### ST-P04 — Empty token results in `Authorization: Bearer ` header (not missing header)
- **Rationale:** Sending an empty Bearer token is still valid from the frontend's perspective; the backend rejects it with 401.
- **Setup:** Mock `ui.run_javascript` to return `""`. Mock `requests.post` returning 401. Click "Upload".
- **Assert:** `requests.post` called with `"Authorization": "Bearer "` in headers. Error label shows "Session expired." message.

### 5.3 XSS Prevention

#### ST-X01 — `detail` from a 4xx response is rendered as text, not HTML
- **Rationale:** The backend could return a `detail` string containing HTML or JS.
- **Setup:** Mock `requests.post` returning `status_code=400, json={"detail": "<script>alert('xss')</script>"}`. Inject a valid file. Click "Upload".
- **Assert:** The error label's text is set via `ui.label.set_text()` (which escapes HTML in NiceGUI). No JS alert fires. The raw string is visible as text, not executed.

#### ST-X02 — Filename containing HTML characters is displayed as text
- **Rationale:** A user could upload a file named `<img src=x onerror=alert(1)>.txt`.
- **Setup:** Inject `filename='<img src=x onerror=alert(1)>.txt'`. (This is a `.txt` file and should be accepted.)
- **Assert:** The filename appears in the file row as literal text (the HTML is not rendered); no JS alert fires.

#### ST-X03 — Filename containing a script tag does not execute
- **Setup:** Inject `filename='<script>alert(1)</script>.pdf'` (valid `.pdf` extension).
- **Assert:** The filename is displayed as literal text in the file row; no JS executes.

### 5.4 Request Integrity

#### ST-R01 — `API_URL` cannot be overridden by file content
- **Rationale:** File bytes are Base64-encoded before use — they cannot modify the request URL.
- **Setup:** Inject `filename='data.txt'`, `content=b'http://evil.example.com/steal'`. Mock `requests.post`. Click "Upload".
- **Assert:** `requests.post` is called with the configured `API_URL` prefix, not any URL derived from file content.

#### ST-R02 — File content bytes are not evaluated or executed at any point
- **Rationale:** File bytes pass through Base64 encoding only. They must not be passed to `eval()`, `exec()`, or rendered in the DOM.
- **Setup:** Inject `filename='payload.txt'`, `content=b'__import__("os").system("whoami")'`.
- **Assert:** No shell command executes; the content is stored as a Base64 string only.

### 5.5 Error Message Safety

#### ST-M01 — Internal exception details are not surfaced to the user
- **Setup:** Mock `requests.post` raising `Exception("internal db error: secret_key=abc123 host=prod-db")`. Inject a valid file. Click "Upload".
- **Assert:** Error label shows only "An unexpected error occurred. Please try again." The raw exception string is not displayed.

#### ST-M02 — File size in error messages is formatted, not raw bytes
- **Rationale:** Showing raw byte counts for large files is not a security issue, but confirming the formatted output avoids accidental internal metric exposure.
- **Setup:** Inject `filename='large.pdf'`, `content=b'x' * 5242880` (5 MB).
- **Assert:** The file row shows something like "5.0 MB" — not the raw integer `5242880`.

---

## 6. Edge Cases

### 6.1 Empty and Zero-Size Files

#### EC-Z01 — Empty file (0 bytes) is accepted (valid extension) and staged
- **Setup:** Inject `filename='empty.txt'`, `content=b''`.
- **Assert:** No validation error; file added to `staged_files` with `size=0`.

#### EC-Z02 — Empty file is displayed with "0 Bytes" in the file row
- **Setup:** Inject `filename='empty.pdf'`, `content=b''`.
- **Assert:** The file row shows "0 Bytes" as the size.

#### EC-Z03 — Empty file's Base64 is an empty string (not an error)
- **Setup:** Inject `filename='empty.xls'`, `content=b''`.
- **Assert:** `staged_files[0]['content']` equals `""`. No exception.

### 6.2 Large Files

#### EC-LG01 — Large file (10 MB) does not crash the UI
- **Setup:** Inject `filename='big.pdf'`, `content=b'x' * 10_485_760` (10 MB).
- **Assert:** No exception during Base64 encoding; file added to `staged_files`.

#### EC-LG02 — Large file size is formatted as MB, not bytes or KB
- **Setup:** Inject `filename='big.pdf'`, `content=b'x' * 10_485_760`.
- **Assert:** File row displays a size string containing "MB".

#### EC-LG03 — Multiple large files do not crash the UI
- **Setup:** Inject five files, each 2 MB in size.
- **Assert:** All five appear in the staged list; no exception.

### 6.3 Special Filename Characters

#### EC-SF01 — Filename with spaces is stored and displayed correctly
- **Setup:** Inject `filename='my report 2024.pdf'`, `content=b'data'`.
- **Assert:** File row shows `"my report 2024.pdf"` verbatim; `staged_files[0]['filename']` matches exactly.

#### EC-SF02 — Filename with Unicode characters is handled correctly
- **Setup:** Inject `filename='ファイル.txt'` (Japanese filename), `content=b'text'`.
- **Assert:** No exception; filename stored and displayed correctly.

#### EC-SF03 — Filename with parentheses and brackets is handled correctly
- **Setup:** Inject `filename='report (final) [v2].xlsx'`.
- **Assert:** File accepted; filename stored without modification.

#### EC-SF04 — Very long filename (255 characters) does not crash
- **Setup:** Inject `filename='a' * 251 + '.txt'` (255 chars total), `content=b'x'`.
- **Assert:** No exception; file added to `staged_files`.

### 6.4 Repeated File Selections

#### EC-RP01 — Selecting the same filename twice adds two separate entries
- **Rationale:** The same filename could be selected multiple times (different content); both should be staged.
- **Setup:** Inject `filename='report.pdf'`, `content=b'v1'`. Then inject `filename='report.pdf'`, `content=b'v2'`.
- **Assert:** `staged_files` has two entries, both with `filename='report.pdf'`.

#### EC-RP02 — Mixed valid and invalid files in sequence — only valid files are staged
- **Setup:** Inject in order: `a.txt` (valid), `b.jpg` (invalid), `c.pdf` (valid), `d.exe` (invalid).
- **Assert:** `staged_files` has exactly two entries: `a.txt` and `c.pdf`. Validation error references the most recent invalid file (`d.exe`).

### 6.5 Network & Response Edge Cases

#### EC-NW01 — 4xx with non-JSON body shows fallback message (no `ValueError` crash)
- **Setup:** Inject a valid file. Mock `requests.post` returning `status_code=400` where `.json()` raises `ValueError("not json")`. Click "Upload".
- **Assert:** Upload error label shows "Upload failed. Please try again." No `ValueError` propagates.

#### EC-NW02 — 5xx with non-JSON body shows server error (no `ValueError` crash)
- **Setup:** Inject a valid file. Mock `requests.post` returning `status_code=500` where `.json()` raises `ValueError`. Click "Upload".
- **Assert:** Upload error label shows "Server error. Please try again later." No crash.

#### EC-NW03 — 2xx with non-JSON body still redirects (no `ValueError` crash)
- **Setup:** Inject a valid file. Mock `requests.post` returning `status_code=200` where `.json()` raises `ValueError`. Click "Upload".
- **Assert:** Redirect to `/chatbot` fires without exception.

#### EC-NW04 — `ui.run_javascript` returning `None` is treated as empty token
- **Setup:** Mock `ui.run_javascript` to return `None`. Inject a valid file. Mock `requests.post` returning 200. Click "Upload".
- **Assert:** No `TypeError` crash; request is sent with `"Authorization": "Bearer None"` or `"Bearer "`. Behaviour is defined: if the backend rejects it (401), the error message is shown.

### 6.6 State Isolation Between Page Visits

#### EC-SI01 — Staged files do not persist between page navigations
- **Setup:** Inject a valid file on the first visit to `/upload`. Navigate away (e.g., to `/login`). Navigate back to `/upload`.
- **Assert:** The staged file list is empty on the second visit; the "Upload" button is disabled.

#### EC-SI02 — Validation error does not persist between page visits
- **Setup:** Trigger a validation error on `/upload`. Navigate away. Navigate back.
- **Assert:** Validation error label is invisible on the fresh page load.

#### EC-SI03 — Upload error does not persist between page visits
- **Setup:** Trigger an upload error on `/upload`. Navigate away. Navigate back.
- **Assert:** Upload error label is invisible on the fresh page load.

### 6.7 Double-Submit Prevention

#### EC-DS01 — Rapid double-click on Upload sends exactly one request
- **Setup:** Inject a valid file. Mock `requests.post` with a blocking `side_effect`. Trigger two click events on "Upload" in rapid succession.
- **Assert:** `requests.post` is called exactly once (button disabled after first click blocks the second).

---

## 7. Test Data Reference

| Scenario | File(s) | Mock | Expected outcome |
|---|---|---|---|
| Single TXT upload | `report.txt` (5 bytes) | `POST → 200` | Redirect to `/chatbot` |
| Single PDF upload | `doc.pdf` (1 KB) | `POST → 200` | Redirect to `/chatbot` |
| Single XLS upload | `data.xls` (2 KB) | `POST → 200` | Redirect to `/chatbot` |
| Single XLSX upload | `sheet.xlsx` (3 KB) | `POST → 200` | Redirect to `/chatbot` |
| Multiple files | `a.txt`, `b.pdf`, `c.xlsx` | `POST → 200` | All 3 in request; redirect to `/chatbot` |
| Invalid type | `photo.jpg` | — (no POST) | Validation error shown; button still disabled |
| Mixed valid/invalid | `a.txt`, `b.jpg`, `c.pdf` | `POST → 200` | Only `a.txt` and `c.pdf` sent; error shown for `b.jpg` |
| Session expired | `report.pdf` | `POST → 401` | "Session expired. Please log in again." |
| Too large | `big.pdf` | `POST → 413` | "Files are too large." |
| Server error | `report.pdf` | `POST → 500` | "Server error. Please try again later." |
| Network down | `report.pdf` | `ConnectionError` | "Could not reach the server. Check your connection." |
| Timeout | `report.pdf` | `Timeout` | "Could not reach the server. Check your connection." |
| Unexpected error | `report.pdf` | `Exception("boom")` | "An unexpected error occurred. Please try again." |
| Empty file | `empty.txt` (0 bytes) | `POST → 200` | Staged and sent; redirect to `/chatbot` |
| Large file (10 MB) | `big.pdf` (10 MB) | `POST → 200` | Staged; size shown in MB; redirect to `/chatbot` |
| XSS filename | `<script>.pdf` | `POST → 200` | Filename rendered as text; no JS executes |
| MIME spoofing | `malware.exe` (type=`text/plain`) | — | Rejected; validation error shown |

---

## 8. Coverage Targets

| Area | Target |
|---|---|
| FR coverage | 100% — every FR in `05-upload-page-ui.md` has at least one test |
| AC coverage | 100% — every AC (AC-01 through AC-22) has a direct mapping below |
| File type validation | All 4 valid types + 4 representative invalid types + case variants + edge cases |
| Base64 encoding | Text, binary, empty, and large content all verified |
| Error status codes | All 7 error categories: 401, 413, other 4xx, 5xx, ConnectionError, Timeout, generic exception |
| Progress bar | Load, in-flight, success, and every error path |
| Security scenarios | MIME spoofing, XSS, payload injection, token leak, request integrity |
| Edge cases | Empty files, large files, Unicode filenames, double-submit, state isolation |

### FR → Test Mapping

| Requirement | Test IDs |
|---|---|
| FR-01 Route registration | UT-R01 |
| FR-02 Page shell / header | UT-R02, UT-R03, UT-R04, UT-R13 |
| FR-03 File selection component | UT-R05, UT-R06 |
| FR-04 Per-file handler (validate + encode + stage) | UT-V01–UT-V17, UT-B01–UT-B05, UT-L01–UT-L09 |
| FR-05 Staged file list display | UT-L01–UT-L09, UT-R12 |
| FR-06 Validation error display | UT-V14–UT-V17, UT-R10 |
| FR-07 Upload button state | UT-UB01–UT-UB08 |
| FR-08 Auth token retrieval | UT-A09, ST-P03, ST-P04 |
| FR-09 Upload API call | UT-A01–UT-A11 |
| FR-10 Success handling | UT-S01–UT-S04 |
| FR-11 Error handling | UT-E01–UT-E14 |

### AC → Test Mapping

| Acceptance Criterion | Test IDs |
|---|---|
| AC-01 Page renders at `/upload` | UT-R01 |
| AC-02 Upload button disabled on page load | UT-R08, UT-UB01 |
| AC-03 File picker restricted to TXT/PDF/XLS/XLSX | UT-V01–UT-V08 |
| AC-04 Valid `.txt` file adds to staged list, enables button | UT-V01, UT-L01, UT-UB02 |
| AC-05 Valid `.pdf` file adds to staged list | UT-V02, UT-L01 |
| AC-06 Valid `.xls` and `.xlsx` files add to staged list | UT-V03, UT-V04 |
| AC-07 Multiple files in one operation all staged | UT-L02, UT-L03, IT-01 |
| AC-08 Unsupported type shows validation error with filename | UT-V05–UT-V08, UT-V14 |
| AC-09 Valid file after invalid clears error | UT-V16 |
| AC-10 Each row shows filename, size, and remove button | UT-L04, UT-L05, UT-L06 |
| AC-11 Remove button removes only that file | UT-L07 |
| AC-12 Removing all files disables Upload button | UT-L08, UT-UB05 |
| AC-13 Clicking Upload disables button and shows progress bar | UT-UB07, UT-P02 |
| AC-14 Request body has valid Base64 content | UT-A05, UT-B01–UT-B04 |
| AC-15 Request includes Authorization: Bearer <token> | UT-A09 |
| AC-16 2xx hides progress bar and navigates to `/chatbot` | UT-S01, UT-S02, UT-P03 |
| AC-17 401 shows "Session expired" message | UT-E01 |
| AC-18 413 shows file-size error message | UT-E02 |
| AC-19 5xx shows server error message | UT-E06 |
| AC-20 Network error shows connection message | UT-E07, UT-E08 |
| AC-21 After any error: progress bar hidden and button re-enabled | UT-E10–UT-E12, UT-P04–UT-P06 |
| AC-22 Renders correctly at 768px | (manual / visual regression — not automated) |
