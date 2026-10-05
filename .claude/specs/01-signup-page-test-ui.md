# Test Spec: Signup Page UI

**ID:** `01-signup-page-test-ui`
**Status:** Ready for implementation
**Covers spec:** [01-signup-page-ui.md](01-signup-page-ui.md)
**Test file location:** `frontend/tests/test_signup_page.py`

---

## 1. Overview

This document defines the full test plan for the signup page UI (`frontend/pages/signup.py`). Tests cover rendering, form interaction, API integration, error handling, security, and edge cases.

The test suite uses **pytest** with **NiceGUI's built-in `User` testing class** (`nicegui.testing.User`) for browser-level interaction simulation, and **`unittest.mock.patch`** to intercept `requests.post` calls without hitting a real backend.

---

## 2. Test Framework & Setup

### 2.1 Dependencies

| Package | Purpose |
|---|---|
| `pytest` | Test runner |
| `pytest-asyncio` | Required by NiceGUI's async `User` fixture |
| `nicegui[testing]` | `nicegui.testing.User` for page interaction |
| `unittest.mock` | `patch` to mock `requests.post` and env vars |

Install via:
```bash
uv add --dev pytest pytest-asyncio
```

NiceGUI's `User` class is included in `nicegui[testing]` extras.

### 2.2 Fixture Pattern

```python
# frontend/tests/conftest.py
import pytest
from nicegui.testing import User

@pytest.fixture
def user(user: User):
    return user
```

All test functions receive the `user` fixture (provided by NiceGUI's pytest plugin). Interaction methods: `user.open('/signup')`, `user.find('Username').type('alice')`, `user.find('Submit').click()`, `user.should_see('...')`.

### 2.3 Mocking Pattern

All tests that trigger the API call must patch `requests.post` at the module level where it is imported:

```python
from unittest.mock import patch, MagicMock

with patch('frontend.pages.signup.requests.post') as mock_post:
    mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
    # ... test body
```

### 2.4 Environment Variable Isolation

Tests must not rely on a real `.env` file. Mock `os.getenv` or set the env var before module import:

```python
import os
os.environ['API_URL'] = 'http://test-backend:8000'
```

---

## 3. Unit Test Cases

### 3.1 Page Rendering

#### UT-R01 — Page loads at `/signup` route
- **Setup:** Open `/signup`.
- **Assert:** Page renders without exception; HTTP 200 equivalent.

#### UT-R02 — Page title is visible
- **Setup:** Open `/signup`.
- **Assert:** Element containing "Decision Intelligence" (or the configured app title) is visible.

#### UT-R03 — Subtitle is visible
- **Setup:** Open `/signup`.
- **Assert:** Element containing "Create your account" is visible.

#### UT-R04 — Username input is rendered
- **Setup:** Open `/signup`.
- **Assert:** An input with label "Username" exists on the page.

#### UT-R05 — Password input is rendered and masked
- **Setup:** Open `/signup`.
- **Assert:** An input with label "Password" exists and is of type `password` (masked by default).

#### UT-R06 — Submit button is rendered
- **Setup:** Open `/signup`.
- **Assert:** A button with text "Sign Up" (or "Submit") exists.

#### UT-R07 — Login navigation link is rendered
- **Setup:** Open `/signup`.
- **Assert:** Element containing "Already have an account" and "Log in" is visible.

#### UT-R08 — Error label is rendered but not visible
- **Setup:** Open `/signup`.
- **Assert:** Error label element exists in DOM but has `invisible` class (not visually shown).

#### UT-R09 — Page does not render sidebar or header
- **Setup:** Open `/signup`.
- **Assert:** No element with NiceGUI's header or left-drawer structure exists on this page.

---

### 3.2 Submit Button Enable/Disable State

#### UT-B01 — Button disabled on page load (both fields empty)
- **Setup:** Open `/signup`. Make no input changes.
- **Assert:** Submit button has `disabled` attribute / is not clickable.

#### UT-B02 — Button disabled when only Username is filled
- **Setup:** Open `/signup`. Type "alice" in Username. Leave Password empty.
- **Assert:** Submit button remains disabled.

#### UT-B03 — Button disabled when only Password is filled
- **Setup:** Open `/signup`. Leave Username empty. Type "secret123" in Password.
- **Assert:** Submit button remains disabled.

#### UT-B04 — Button enabled when both fields have values
- **Setup:** Open `/signup`. Type "alice" in Username. Type "secret123" in Password.
- **Assert:** Submit button is enabled (no `disabled` attribute).

#### UT-B05 — Button re-disabled when Username is cleared after being filled
- **Setup:** Open `/signup`. Fill both fields. Clear Username.
- **Assert:** Submit button becomes disabled again.

#### UT-B06 — Button re-disabled when Password is cleared after being filled
- **Setup:** Open `/signup`. Fill both fields. Clear Password.
- **Assert:** Submit button becomes disabled again.

---

### 3.3 API Call Behavior

#### UT-A01 — POST is sent to correct URL on submit
- **Setup:** Mock `requests.post` returning `status_code=201`. Fill both fields. Click Submit.
- **Assert:** `requests.post` was called with URL `http://test-backend:8000/api/signup`.

#### UT-A02 — Request payload contains username and password
- **Setup:** Mock `requests.post`. Type "alice" / "secret123". Click Submit.
- **Assert:** `requests.post` called with `json={"username": "alice", "password": "secret123"}`.

#### UT-A03 — Request includes `Content-Type: application/json` header
- **Setup:** Mock `requests.post`. Fill fields. Click Submit.
- **Assert:** `headers` kwarg passed to `requests.post` includes `"Content-Type": "application/json"`.

#### UT-A04 — Submit button is disabled during the API call (double-submit prevention)
- **Setup:** Mock `requests.post` with a delayed response (use `side_effect` with a blocking callable). Click Submit.
- **Assert:** Submit button is disabled while the mock is blocking.

#### UT-A05 — API_URL is sourced from environment variable, not hardcoded
- **Setup:** Set `API_URL=http://custom-host:9000` in env before importing the module. Mock `requests.post`. Fill fields. Click Submit.
- **Assert:** `requests.post` URL starts with `http://custom-host:9000`.

---

### 3.4 Success Handling

#### UT-S01 — Redirect to `/upload` on 200 response
- **Setup:** Mock `requests.post` returning `status_code=200`. Fill fields. Click Submit.
- **Assert:** Current page/URL is `/upload`.

#### UT-S02 — Redirect to `/upload` on 201 response
- **Setup:** Mock `requests.post` returning `status_code=201`. Fill fields. Click Submit.
- **Assert:** Current page/URL is `/upload`.

#### UT-S03 — No error label shown on success
- **Setup:** Mock `requests.post` returning `status_code=201`. Fill fields. Click Submit.
- **Assert:** Error label remains invisible / contains no text before redirect fires.

---

### 3.5 Error Handling

#### UT-E01 — 400 response shows `detail` from response JSON
- **Setup:** Mock `requests.post` returning `status_code=400, json={"detail": "Invalid input"}`. Fill fields. Click Submit.
- **Assert:** Error label is visible and contains "Invalid input".

#### UT-E02 — 409 response shows `detail` from response JSON
- **Setup:** Mock `requests.post` returning `status_code=409, json={"detail": "Username already exists"}`. Fill fields. Click Submit.
- **Assert:** Error label is visible and contains "Username already exists".

#### UT-E03 — 422 response shows `detail` or generic message
- **Setup:** Mock `requests.post` returning `status_code=422, json={"detail": "Validation error"}`. Fill fields. Click Submit.
- **Assert:** Error label is visible and contains "Validation error".

#### UT-E04 — 422 response with no `detail` field shows generic message
- **Setup:** Mock `requests.post` returning `status_code=422, json={}`. Fill fields. Click Submit.
- **Assert:** Error label is visible and contains a non-empty fallback message (not an exception traceback).

#### UT-E05 — 500 response shows generic server error message
- **Setup:** Mock `requests.post` returning `status_code=500`. Fill fields. Click Submit.
- **Assert:** Error label is visible and contains "Server error. Please try again later."

#### UT-E06 — Network error shows connection message
- **Setup:** Mock `requests.post` raising `requests.exceptions.ConnectionError`. Fill fields. Click Submit.
- **Assert:** Error label is visible and contains "Could not reach the server".

#### UT-E07 — Submit button re-enabled after 4xx error
- **Setup:** Mock `requests.post` returning `status_code=409`. Fill fields. Click Submit.
- **Assert:** Submit button is enabled after the handler completes.

#### UT-E08 — Submit button re-enabled after 5xx error
- **Setup:** Mock `requests.post` returning `status_code=500`. Fill fields. Click Submit.
- **Assert:** Submit button is enabled after the handler completes.

#### UT-E09 — Submit button re-enabled after network error
- **Setup:** Mock `requests.post` raising `requests.exceptions.ConnectionError`. Fill fields. Click Submit.
- **Assert:** Submit button is enabled after the handler completes.

#### UT-E10 — Page remains on `/signup` after any error
- **Setup:** Mock `requests.post` returning `status_code=409`. Fill fields. Click Submit.
- **Assert:** Current route remains `/signup`.

#### UT-E11 — Error label clears / becomes invisible when user retries
- **Setup:** Trigger a 409 error (error label appears). Update the Username field with a new value. Click Submit again with a 201 mock.
- **Assert:** Error label is hidden (or cleared) before the second request fires, or at the moment of redirect.

---

### 3.6 Navigation

#### UT-N01 — Login link navigates to `/login`
- **Setup:** Open `/signup`. Click "Log in" (or the login navigation element).
- **Assert:** Current route is `/login`.

---

## 4. Security Tests

### 4.1 Input Sanitization / XSS

#### ST-X01 — Script tag in Username field does not execute
- **Setup:** Mock `requests.post` returning 409 with `detail` echoing the username. Type `<script>alert('xss')</script>` in Username. Click Submit.
- **Assert:** No JavaScript alert fires. The error label renders the string as plain text, not interpreted HTML.
- **Why:** NiceGUI labels must not use `ui.html()` for user-controlled content. Use `ui.label()` only.

#### ST-X02 — HTML in error response `detail` field does not render as markup
- **Setup:** Mock `requests.post` returning `status_code=409, json={"detail": "<b>bold error</b><img src=x onerror=alert(1)>"}`. Fill fields. Click Submit.
- **Assert:** Error label displays the raw string literally; no HTML elements are rendered; no JS executes.

#### ST-X03 — `javascript:` URI in login link does not execute
- **Setup:** Inspect the login link's `href` or `on_click` target.
- **Assert:** The navigation target is the literal string `'/login'`, not a user-supplied value. The link is hardcoded, not derived from any input.

### 4.2 Credential Handling

#### ST-C01 — Password value is not logged or exposed in error label
- **Setup:** Mock `requests.post` raising `Exception('connection failed')`. Type "secret123" in Password. Click Submit.
- **Assert:** Error label text does not contain "secret123". The exception message exposed to the UI must not include the password string.

#### ST-C02 — Password field renders as masked input by default
- **Setup:** Open `/signup`. Type "mysecret" in Password.
- **Assert:** The input element's `type` attribute is `password` (characters are obscured before toggling visibility).

#### ST-C03 — Password value is not present in the URL
- **Setup:** Mock `requests.post` returning 201. Fill fields. Click Submit.
- **Assert:** The navigation target `/upload` contains no query string with the username or password.

### 4.3 Request Integrity

#### ST-R01 — API_URL cannot be overridden by user input
- **Setup:** Open `/signup`. Type `http://evil.example.com` in the Username field. Click Submit.
- **Assert:** `requests.post` is still called with the configured `API_URL` prefix, not any user-provided URL.

#### ST-R02 — Request does not include extra sensitive headers (no auth token leak)
- **Setup:** Mock `requests.post`. Fill fields. Click Submit.
- **Assert:** The `headers` kwarg passed to `requests.post` does not contain `Authorization`, `Cookie`, or any session token from a prior page.

### 4.4 Error Message Safety

#### ST-M01 — Internal exception details are not surfaced to the user
- **Setup:** Mock `requests.post` raising a generic `Exception('internal db error: password=hunter2 host=prod-db')`. Click Submit.
- **Assert:** Error label shows only the user-facing connection error message, not the raw exception string.

---

## 5. Edge Cases

### 5.1 Whitespace Inputs

#### EC-W01 — Whitespace-only Username keeps button disabled
- **Setup:** Open `/signup`. Type `"   "` (spaces only) in Username. Type "secret123" in Password.
- **Assert:** Submit button remains disabled (whitespace does not count as valid input).

#### EC-W02 — Whitespace-only Password keeps button disabled
- **Setup:** Open `/signup`. Type "alice" in Username. Type `"   "` (spaces only) in Password.
- **Assert:** Submit button remains disabled.

#### EC-W03 — Whitespace-only values in both fields keeps button disabled
- **Setup:** Open `/signup`. Type `"   "` in both fields.
- **Assert:** Submit button remains disabled.

### 5.2 Long Inputs

#### EC-L01 — Very long username (500 characters) does not crash the UI
- **Setup:** Mock `requests.post` returning 400 with generic detail. Type a 500-character string in Username. Type "pass" in Password. Click Submit.
- **Assert:** No unhandled exception; error label displays normally.

#### EC-L02 — Very long password (500 characters) does not crash the UI
- **Setup:** Same as EC-L01 but 500 chars in Password.
- **Assert:** No unhandled exception; error label displays normally.

### 5.3 Special & Unicode Characters

#### EC-U01 — Username with special characters (`@`, `#`, `!`, spaces)
- **Setup:** Mock `requests.post` returning 201. Type `"alice @#! 123"` in Username. Type "pass" in Password. Click Submit.
- **Assert:** The exact value `"alice @#! 123"` is sent in the JSON payload as `username`; redirect fires.

#### EC-U02 — Password with special characters and symbols
- **Setup:** Mock `requests.post` returning 201. Type `"p@$$w0rd!<>&"` in Password. Type "alice" in Username. Click Submit.
- **Assert:** The exact value is sent unmodified in the JSON payload; no encoding errors.

#### EC-U03 — Unicode username (non-ASCII characters)
- **Setup:** Mock `requests.post` returning 201. Type `"用户名"` in Username. Type "pass" in Password. Click Submit.
- **Assert:** JSON payload encodes the Unicode string correctly (UTF-8); no `UnicodeEncodeError`.

#### EC-U04 — Emoji in password field
- **Setup:** Mock `requests.post` returning 201. Type `"pass🔑word"` in Password. Type "alice" in Username. Click Submit.
- **Assert:** No crash; value transmitted as-is.

### 5.4 Network & Response Edge Cases

#### EC-N01 — Request timeout shows connection error message
- **Setup:** Mock `requests.post` raising `requests.exceptions.Timeout`. Fill fields. Click Submit.
- **Assert:** Error label is visible and contains a user-friendly timeout/connection message (not a raw `Timeout` traceback).

#### EC-N02 — Backend returns 2xx but body is empty (no JSON)
- **Setup:** Mock `requests.post` returning `status_code=200` with an empty body (`text=''`, `json` method raises `ValueError`). Fill fields. Click Submit.
- **Assert:** Redirect to `/upload` fires without raising a JSON parse error (success path must not call `.json()`).

#### EC-N03 — Backend returns 4xx with non-JSON body
- **Setup:** Mock `requests.post` returning `status_code=400` with `text='Bad Request'` and `.json()` raising `ValueError`. Fill fields. Click Submit.
- **Assert:** Error label shows a fallback generic message; no unhandled `ValueError` propagates to the UI.

#### EC-N04 — Backend returns 4xx with `detail` as a list (FastAPI validation errors)
- **Setup:** Mock `requests.post` returning `status_code=422, json={"detail": [{"loc": ["body", "username"], "msg": "field required"}]}`. Click Submit.
- **Assert:** Error label is visible and shows either a stringified version of the list or a generic message — it must not crash on `str(list)`.

### 5.5 Interaction Edge Cases

#### EC-I01 — Clicking Submit multiple times in rapid succession sends only one request
- **Setup:** Mock `requests.post` with a small delay. Fill fields. Trigger Submit click twice programmatically.
- **Assert:** `requests.post` is called exactly once (button disabled prevents second call).

#### EC-I02 — Navigating to `/signup` after a prior session leaves no stale error state
- **Setup:** Open `/signup`, trigger a 409 error (error label appears). Navigate away. Navigate back to `/signup`.
- **Assert:** Error label is invisible on fresh load; no stale error text from the previous visit.

#### EC-I03 — API_URL environment variable not set uses fallback default
- **Setup:** Remove `API_URL` from the environment (unset it). Open `/signup`. Mock `requests.post`. Fill fields. Click Submit.
- **Assert:** `requests.post` URL starts with `http://localhost:8000` (the default).

---

## 6. Test Data Reference

| Scenario | Username | Password | Mock Status | Expected Outcome |
|---|---|---|---|---|
| Happy path | `alice` | `secret123` | `201` | Redirect to `/upload` |
| Duplicate user | `existing_user` | `anypass` | `409 {"detail": "Username already exists"}` | Inline error shown |
| Backend crash | `alice` | `secret123` | `500` | "Server error..." shown |
| Network down | `alice` | `secret123` | `ConnectionError` | "Could not reach..." shown |
| Empty username | `` | `secret123` | (no call) | Button stays disabled |
| Whitespace username | `   ` | `secret123` | (no call) | Button stays disabled |
| XSS in username | `<script>alert(1)</script>` | `pass` | `409 (echoed)` | Rendered as plain text |
| Unicode | `用户名` | `pass🔑` | `201` | Redirect to `/upload` |

---

## 7. Coverage Targets

| Area | Target |
|---|---|
| FR coverage (functional requirements) | 100% — every FR in `01-signup-page-ui.md` has at least one test |
| AC coverage (acceptance criteria) | 100% — every AC has a direct mapping to a test case |
| Error status codes | All 5 categories tested (400, 409, 422, 500, network) |
| Security scenarios | XSS, credential leak, request integrity, error message safety |
| Edge cases | Whitespace, long input, unicode, race conditions, stale state |

### FR → Test Mapping

| Requirement | Test IDs |
|---|---|
| FR-01 Route registration | UT-R01 |
| FR-02 Centered form | UT-R02, UT-R03, UT-R04, UT-R05, UT-R06, UT-R09 |
| FR-03 Input fields | UT-R04, UT-R05 |
| FR-04 Button enable/disable | UT-B01–UT-B06, EC-W01–EC-W03 |
| FR-05 API call | UT-A01–UT-A05 |
| FR-06 Success redirect | UT-S01, UT-S02, UT-S03 |
| FR-07 Error handling | UT-E01–UT-E11, EC-N01–EC-N04 |
| FR-08 Login link | UT-R07, UT-N01 |

### AC → Test Mapping

| Acceptance Criterion | Test IDs |
|---|---|
| AC-01 Page renders at `/signup` | UT-R01 |
| AC-02 Button disabled when both empty | UT-B01 |
| AC-03 Button disabled when one field filled | UT-B02, UT-B03 |
| AC-04 Button enabled when both filled | UT-B04 |
| AC-05 POST sent with correct body | UT-A01, UT-A02, UT-A03 |
| AC-06 Success redirects to `/upload` | UT-S01, UT-S02 |
| AC-07 409 shows backend error inline | UT-E02 |
| AC-08 422 shows descriptive error inline | UT-E03, UT-E04 |
| AC-09 Network error shows connection message | UT-E06, EC-N01 |
| AC-10 Button re-enabled after error | UT-E07, UT-E08, UT-E09 |
| AC-11 Login link navigates to `/login` | UT-N01 |
| AC-12 Renders correctly at 768px | (manual / visual regression test) |
