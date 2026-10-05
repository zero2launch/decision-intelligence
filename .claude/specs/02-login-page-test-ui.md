# Test Spec: Login Page UI

**ID:** `02-login-page-test-ui`
**Status:** Ready for implementation
**Covers spec:** [02-login-page-ui.md](02-login-page-ui.md)
**Test file location:** `frontend/tests/test_login_page.py`

---

## 1. Overview

This document defines the full test plan for the login page UI (`frontend/pages/login.py`). Tests cover rendering, form interaction, API integration, Enter key submission, error handling, security, and edge cases.

The test suite uses **pytest** with **NiceGUI's built-in `User` testing class** (`nicegui.testing.User`) for browser-level interaction simulation, and **`unittest.mock.patch`** to intercept `requests.post` calls without hitting a real backend.

> **Key difference from the signup test suite:** The login page always shows a fixed `"Invalid username or password."` message for **all** 4xx responses — it never surfaces the backend `detail` field. Tests must verify this fixed-message behaviour, not dynamic detail extraction.

---

## 2. Test Framework & Setup

### 2.1 Dependencies

| Package | Purpose |
|---|---|
| `pytest` | Test runner |
| `pytest-asyncio` | Required by NiceGUI's async `User` fixture |
| `nicegui[testing]` | `nicegui.testing.User` for page interaction |
| `unittest.mock` | `patch` to mock `requests.post` and env vars |

All are already present from the signup test suite. No new packages required.

### 2.2 Fixture Pattern

```python
# frontend/tests/conftest.py  (already exists — no changes needed)
import pytest
from nicegui.testing import User

@pytest.fixture
def user(user: User):
    return user
```

All test functions receive the `user` fixture provided by NiceGUI's pytest plugin. Core interaction methods used: `user.open('/login')`, `user.find('Username').type('alice')`, `user.find('Log in').click()`, `user.should_see('...')`.

### 2.3 Mocking Pattern

All tests that trigger the API call must patch `requests.post` at the module where it is imported:

```python
from unittest.mock import patch, MagicMock

with patch('frontend.pages.login.requests.post') as mock_post:
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
    # ... test body
```

### 2.4 Environment Variable Isolation

```python
# At the top of test_login_page.py, before importing the page module
import os
os.environ.setdefault('API_URL', 'http://test-backend:8000')

import frontend.pages.login  # noqa: F401
```

Tests that need a different `API_URL` must patch the module-level constant directly:
```python
with patch('frontend.pages.login.API_URL', 'http://custom-host:9000'):
    ...
```

---

## 3. Unit Test Cases

### 3.1 Page Rendering

#### UT-R01 — Page loads at `/login` without error
- **Setup:** Open `/login`.
- **Assert:** Page renders without exception; "Decision Intelligence" title is visible.

#### UT-R02 — App title is visible
- **Setup:** Open `/login`.
- **Assert:** Element containing "Decision Intelligence" is present on the page.

#### UT-R03 — Subtitle is visible
- **Setup:** Open `/login`.
- **Assert:** Element containing "Sign in to your account" is visible.

#### UT-R04 — Username input is rendered
- **Setup:** Open `/login`.
- **Assert:** An input with label "Username" exists.

#### UT-R05 — Password input is rendered
- **Setup:** Open `/login`.
- **Assert:** An input with label "Password" exists.

#### UT-R06 — Submit button is rendered with correct label
- **Setup:** Open `/login`.
- **Assert:** A button with text "Log in" exists.

#### UT-R07 — Signup navigation link is rendered
- **Setup:** Open `/login`.
- **Assert:** Elements containing "Don't have an account?" and "Sign up" are visible.

#### UT-R08 — Error label is rendered but invisible on load
- **Setup:** Open `/login`.
- **Assert:** Error label element exists in the DOM but carries the `invisible` class (not visually shown). No error text is displayed without user action.

#### UT-R09 — Page does not render sidebar or header
- **Setup:** Open `/login`.
- **Assert:** No standard app shell header or left-drawer element exists — the page is a standalone full-screen layout.

---

### 3.2 Submit Button Enable / Disable State

#### UT-B01 — Button disabled on page load (both fields empty)
- **Setup:** Open `/login`. Make no input changes.
- **Assert:** "Log in" button has `disabled` attribute / is not interactable.

#### UT-B02 — Button disabled when only Username is filled
- **Setup:** Open `/login`. Type "alice" in Username. Leave Password empty.
- **Assert:** "Log in" button remains disabled.

#### UT-B03 — Button disabled when only Password is filled
- **Setup:** Open `/login`. Leave Username empty. Type "secret123" in Password.
- **Assert:** "Log in" button remains disabled.

#### UT-B04 — Button enabled when both fields have values
- **Setup:** Open `/login`. Type "alice" in Username. Type "secret123" in Password.
- **Assert:** "Log in" button is enabled.

#### UT-B05 — Button re-disabled when Username is cleared after being filled
- **Setup:** Fill both fields. Clear Username.
- **Assert:** "Log in" button becomes disabled again.

#### UT-B06 — Button re-disabled when Password is cleared after being filled
- **Setup:** Fill both fields. Clear Password.
- **Assert:** "Log in" button becomes disabled again.

---

### 3.3 API Call Behaviour

#### UT-A01 — POST is sent to the correct URL on click
- **Setup:** Mock `requests.post` returning `status_code=200`. Fill both fields. Click "Log in".
- **Assert:** `requests.post` was called with URL `http://test-backend:8000/api/login`.

#### UT-A02 — Request payload contains username and password
- **Setup:** Mock `requests.post`. Type "alice" / "secret123". Click "Log in".
- **Assert:** `requests.post` called with `json={"username": "alice", "password": "secret123"}`.

#### UT-A03 — Request includes `Content-Type: application/json` header
- **Setup:** Mock `requests.post`. Fill fields. Click "Log in".
- **Assert:** `headers` kwarg passed to `requests.post` includes `"Content-Type": "application/json"`.

#### UT-A04 — Submit button is disabled during the API call (double-submit prevention)
- **Setup:** Mock `requests.post` with a blocking `side_effect`. Fill fields. Click "Log in".
- **Assert:** "Log in" button is disabled while the mock is blocking (before it returns).

#### UT-A05 — `API_URL` is sourced from the environment variable
- **Setup:** Patch `frontend.pages.login.API_URL` to `http://custom-host:9000`. Mock `requests.post`. Fill fields. Click "Log in".
- **Assert:** `requests.post` URL starts with `http://custom-host:9000`.

---

### 3.4 Success Handling

#### UT-S01 — Redirects to `/upload` on 200 response
- **Setup:** Mock `requests.post` returning `status_code=200`. Fill fields. Click "Log in".
- **Assert:** Current page URL path is `/upload`.

#### UT-S02 — Redirects to `/upload` on any 2xx response (e.g. 201)
- **Setup:** Mock `requests.post` returning `status_code=201`. Fill fields. Click "Log in".
- **Assert:** Current page URL path is `/upload`.

#### UT-S03 — No error label shown on successful login
- **Setup:** Mock `requests.post` returning `status_code=200`. Fill fields. Click "Log in".
- **Assert:** Error label remains invisible / empty before the redirect fires.

#### UT-S04 — Success handler does not call `.json()` on the response
- **Setup:** Mock `requests.post` returning a response where `status_code=200` and `.json()` raises `ValueError("no body")`. Fill fields. Click "Log in".
- **Assert:** No `ValueError` is raised; redirect to `/upload` still fires.

---

### 3.5 Error Handling

> All 4xx responses must show the fixed message `"Invalid username or password."` — the backend `detail` field must never be surfaced on the login page.

#### UT-E01 — 401 response shows "Invalid username or password."
- **Setup:** Mock `requests.post` returning `status_code=401`. Fill fields. Click "Log in".
- **Assert:** Error label is visible and contains exactly "Invalid username or password."

#### UT-E02 — 400 response shows "Invalid username or password." (not backend detail)
- **Setup:** Mock `requests.post` returning `status_code=400, json={"detail": "Bad credentials"}`. Fill fields. Click "Log in".
- **Assert:** Error label shows "Invalid username or password.", not "Bad credentials".

#### UT-E03 — 422 response shows "Invalid username or password." (not validation detail)
- **Setup:** Mock `requests.post` returning `status_code=422, json={"detail": [{"msg": "field required"}]}`. Fill fields. Click "Log in".
- **Assert:** Error label shows "Invalid username or password.", not "field required".

#### UT-E04 — 403 (or any other 4xx) response shows "Invalid username or password."
- **Setup:** Mock `requests.post` returning `status_code=403`. Fill fields. Click "Log in".
- **Assert:** Error label shows "Invalid username or password."

#### UT-E05 — 500 response shows "Server error. Please try again later."
- **Setup:** Mock `requests.post` returning `status_code=500`. Fill fields. Click "Log in".
- **Assert:** Error label is visible and contains "Server error. Please try again later."

#### UT-E06 — `ConnectionError` shows "Could not reach the server. Check your connection."
- **Setup:** Mock `requests.post` raising `requests.exceptions.ConnectionError`. Fill fields. Click "Log in".
- **Assert:** Error label is visible and contains "Could not reach the server. Check your connection."

#### UT-E07 — `Timeout` shows "Could not reach the server. Check your connection."
- **Setup:** Mock `requests.post` raising `requests.exceptions.Timeout`. Fill fields. Click "Log in".
- **Assert:** Error label is visible and contains "Could not reach the server. Check your connection."

#### UT-E08 — Generic exception shows "Could not reach the server. Check your connection."
- **Setup:** Mock `requests.post` raising a bare `Exception("unexpected")`. Fill fields. Click "Log in".
- **Assert:** Error label is visible and contains "Could not reach the server. Check your connection."

#### UT-E09 — Submit button re-enabled after 4xx error
- **Setup:** Mock `requests.post` returning `status_code=401`. Fill fields. Click "Log in".
- **Assert:** "Log in" button is enabled after the handler completes.

#### UT-E10 — Submit button re-enabled after 5xx error
- **Setup:** Mock `requests.post` returning `status_code=500`. Fill fields. Click "Log in".
- **Assert:** "Log in" button is enabled after the handler completes.

#### UT-E11 — Submit button re-enabled after network error
- **Setup:** Mock `requests.post` raising `requests.exceptions.ConnectionError`. Fill fields. Click "Log in".
- **Assert:** "Log in" button is enabled after the handler completes.

#### UT-E12 — Page remains on `/login` after any error
- **Setup:** Mock `requests.post` returning `status_code=401`. Fill fields. Click "Log in".
- **Assert:** Current route path is `/login`.

#### UT-E13 — Error label is cleared/hidden when user retries a submit
- **Setup:** Trigger a 401 error (error label appears). Update Username field. Click "Log in" again (mock now returns 200).
- **Assert:** Error label is hidden (invisible class applied) before the second API request fires, or at the moment of redirect.

---

### 3.6 Enter Key Submission (FR-08)

#### UT-K01 — Enter key on password field submits when both fields are filled
- **Setup:** Mock `requests.post` returning `status_code=200`. Fill both fields. Focus the password input. Simulate `keydown.enter` event.
- **Assert:** `requests.post` is called once; user is redirected to `/upload`.

#### UT-K02 — Enter key on password field does nothing when Username is empty
- **Setup:** Leave Username empty. Type "secret123" in Password. Simulate `keydown.enter` on password input.
- **Assert:** `requests.post` is **not** called; no error label appears; page stays on `/login`.

#### UT-K03 — Enter key on password field does nothing when Username is whitespace-only
- **Setup:** Type `"   "` in Username. Type "secret123" in Password. Simulate `keydown.enter` on password input.
- **Assert:** `requests.post` is **not** called; page stays on `/login`.

#### UT-K04 — Enter key on password field does nothing when Password is empty
- **Setup:** Type "alice" in Username. Leave Password empty. Simulate `keydown.enter` on password input.
- **Assert:** `requests.post` is **not** called; page stays on `/login`.

#### UT-K05 — Enter key on username field does NOT submit the form
- **Setup:** Fill both fields. Simulate `keydown.enter` on the username input.
- **Assert:** `requests.post` is **not** called (Enter key handler is only on the password field).

#### UT-K06 — Enter key submission shows the same error as button click on failure
- **Setup:** Mock `requests.post` returning `status_code=401`. Fill both fields. Simulate `keydown.enter` on password input.
- **Assert:** Error label is visible and contains "Invalid username or password." — same as the click path.

---

### 3.7 Navigation

#### UT-N01 — "Sign up" link navigates to `/signup`
- **Setup:** Open `/login`. Click "Sign up" (the navigation link).
- **Assert:** Current route is `/signup`.

---

## 4. Integration Test Scenarios

These scenarios test multi-step flows that cross component boundaries. Each scenario is a single test function that narrates a realistic user journey.

### IT-01 — Full happy path: login and redirect
```
1. Open /login
2. Observe: "Log in" button is disabled, no error shown
3. Type "alice" in Username
4. Observe: button still disabled (password empty)
5. Type "secret123" in Password
6. Observe: button becomes enabled
7. [Mock: POST /api/login → 200]
8. Click "Log in"
9. Assert: redirected to /upload
10. Assert: no error label was made visible during the flow
```

### IT-02 — Failed login then successful retry
```
1. Open /login
2. Fill both fields with wrong credentials
3. [Mock: POST /api/login → 401]
4. Click "Log in"
5. Assert: error label visible, shows "Invalid username or password."
6. Assert: button is re-enabled, page remains /login
7. Update Password field with correct value
8. [Mock: POST /api/login → 200]
9. Click "Log in"
10. Assert: error label is hidden before/during the second submit
11. Assert: redirected to /upload
```

### IT-03 — Network failure then recovery
```
1. Open /login
2. Fill both fields
3. [Mock: POST /api/login → raises ConnectionError]
4. Click "Log in"
5. Assert: error label shows "Could not reach the server. Check your connection."
6. Assert: button re-enabled
7. [Mock: POST /api/login → 200]
8. Click "Log in" again
9. Assert: redirected to /upload
```

### IT-04 — Enter key then button click both work identically
```
1. Open /login. Fill both fields.
2. [Mock: POST /api/login → 401]
3. Press Enter on password field
4. Assert: error label appears with "Invalid username or password."
5. [Mock: POST /api/login → 200]
6. Click "Log in" button
7. Assert: redirected to /upload
(Verifies both submission paths produce equivalent behaviour)
```

### IT-05 — Navigation round-trip: login → signup → login
```
1. Open /login
2. Click "Sign up" link
3. Assert: current route is /signup
4. Click "Log in" link on signup page
5. Assert: current route is /login
6. Assert: login page renders cleanly with no stale state (error label invisible, fields empty)
```

---

## 5. Security Tests

### 5.1 User Enumeration Prevention

#### ST-U01 — All 4xx responses produce the identical error message
- **Setup:** Run the submit handler with `status_code=401`, then with `status_code=400`, then with `status_code=403`, then with `status_code=404`.
- **Assert:** Each produces exactly `"Invalid username or password."` — no variation between status codes that could reveal whether the username or password was wrong.

#### ST-U02 — Backend `detail` field is never surfaced on any 4xx response
- **Setup:** Mock `requests.post` returning `status_code=401, json={"detail": "No user with that email"}`. Fill fields. Click "Log in".
- **Assert:** Error label does **not** contain "No user with that email". It shows only "Invalid username or password."

### 5.2 XSS Prevention

#### ST-X01 — Script tag in error response `detail` is not executed
- **Setup:** Mock `requests.post` returning `status_code=500, json={"detail": "<script>alert('xss')</script>"}`. Fill fields. Click "Log in".
- **Assert:** The 500 path shows the server error message; the `detail` is not displayed or evaluated. No JS alert fires.

#### ST-X02 — HTML in a 4xx response `detail` is neither displayed nor executed
- **Setup:** Mock `requests.post` returning `status_code=401, json={"detail": "<img src=x onerror=alert(1)>"}`. Fill fields. Click "Log in".
- **Assert:** Error label shows "Invalid username or password." only. The `detail` value is never passed to `ui.label()` or any rendering path.

#### ST-X03 — Script in Username field is transmitted as plain text, not executed
- **Setup:** Mock `requests.post` returning `status_code=200`. Type `<script>alert('xss')</script>` in Username. Type "pass" in Password. Click "Log in".
- **Assert:** `requests.post` receives the literal string in the JSON payload; no JS alert fires; redirect fires normally.

### 5.3 Credential Handling

#### ST-C01 — Password value does not appear in the error label
- **Setup:** Mock `requests.post` raising `Exception("connection failed")`. Type "supersecret" in Password. Click "Log in".
- **Assert:** Error label text does not contain "supersecret". The exception message is swallowed by the generic handler.

#### ST-C02 — Password field renders as type=`password` (masked) by default
- **Setup:** Open `/login`. Type "mypassword" in Password.
- **Assert:** The input element's `type` attribute is `password` before any toggle action.

#### ST-C03 — Password value does not appear in the navigation URL after redirect
- **Setup:** Mock `requests.post` returning `status_code=200`. Fill fields. Click "Log in".
- **Assert:** The resulting URL `/upload` contains no query string parameters carrying the username or password.

### 5.4 Request Integrity

#### ST-R01 — `API_URL` cannot be overridden by user input
- **Setup:** Type `http://evil.example.com` in the Username field. Mock `requests.post`. Click "Log in".
- **Assert:** `requests.post` is called with the configured `API_URL` prefix, not the user-supplied string.

#### ST-R02 — Request does not include authorization or session headers
- **Setup:** Mock `requests.post`. Fill fields. Click "Log in".
- **Assert:** `headers` kwarg does not contain `Authorization`, `Cookie`, or any session token — the login page is unauthenticated.

### 5.5 Error Message Safety

#### ST-M01 — Internal exception strings are not surfaced to the user
- **Setup:** Mock `requests.post` raising `Exception("internal db error: password=hunter2 host=prod-db")`. Fill fields. Click "Log in".
- **Assert:** Error label shows only "Could not reach the server. Check your connection." — the raw exception string is never displayed.

---

## 6. Edge Cases

### 6.1 Whitespace Inputs

#### EC-W01 — Whitespace-only Username keeps button disabled
- **Setup:** Type `"   "` in Username. Type "secret123" in Password.
- **Assert:** "Log in" button remains disabled.

#### EC-W02 — Whitespace-only Password keeps button disabled
- **Setup:** Type "alice" in Username. Type `"   "` in Password.
- **Assert:** "Log in" button remains disabled.

#### EC-W03 — Whitespace-only values in both fields keeps button disabled
- **Setup:** Type `"   "` in both fields.
- **Assert:** "Log in" button remains disabled.

#### EC-W04 — Enter key on password field is ignored when both fields are whitespace-only
- **Setup:** Type `"   "` in both fields. Simulate `keydown.enter` on password input.
- **Assert:** `requests.post` is not called.

### 6.2 Long Inputs

#### EC-L01 — Very long username (500 characters) does not crash the UI
- **Setup:** Mock `requests.post` returning `status_code=401`. Type a 500-character string in Username. Type "pass" in Password. Click "Log in".
- **Assert:** No unhandled exception; error label displays "Invalid username or password." normally.

#### EC-L02 — Very long password (500 characters) does not crash the UI
- **Setup:** Mock `requests.post` returning `status_code=401`. Type "alice" in Username. Type a 500-character string in Password. Click "Log in".
- **Assert:** No unhandled exception; error label displays "Invalid username or password." normally.

### 6.3 Special & Unicode Characters

#### EC-U01 — Username with special characters is transmitted verbatim
- **Setup:** Mock `requests.post` returning `status_code=200`. Type `"alice @#! 123"` in Username. Type "pass" in Password. Click "Log in".
- **Assert:** JSON payload sent to `requests.post` contains `"username": "alice @#! 123"` exactly.

#### EC-U02 — Password with symbols and special characters is transmitted verbatim
- **Setup:** Mock `requests.post` returning `status_code=200`. Type `"p@$$w0rd!<>&"` in Password. Type "alice" in Username. Click "Log in".
- **Assert:** JSON payload contains the exact password string; no encoding errors thrown.

#### EC-U03 — Unicode username (non-ASCII) is transmitted correctly
- **Setup:** Mock `requests.post` returning `status_code=200`. Type `"用户名"` in Username. Type "pass" in Password. Click "Log in".
- **Assert:** JSON payload encodes the Unicode string correctly; no `UnicodeEncodeError` is raised.

#### EC-U04 — Emoji in password field does not crash the UI
- **Setup:** Mock `requests.post` returning `status_code=200`. Type `"pass🔑word"` in Password. Type "alice" in Username. Click "Log in".
- **Assert:** No exception; value transmitted as-is.

### 6.4 Network & Response Edge Cases

#### EC-N01 — 4xx response with non-JSON body still shows fixed message
- **Setup:** Mock `requests.post` returning `status_code=401` where `.json()` raises `ValueError("not json")`. Fill fields. Click "Log in".
- **Assert:** Error label shows "Invalid username or password." — the fixed-message path must not call `.json()` at all for 4xx.

#### EC-N02 — 5xx response with non-JSON body shows server error message
- **Setup:** Mock `requests.post` returning `status_code=500` where `.json()` raises `ValueError`. Fill fields. Click "Log in".
- **Assert:** Error label shows "Server error. Please try again later." — no `ValueError` propagates.

#### EC-N03 — 2xx with empty body (no JSON) redirects successfully
- **Setup:** Mock `requests.post` returning `status_code=200` where `.json()` raises `ValueError("no body")`. Fill fields. Click "Log in".
- **Assert:** Redirect to `/upload` fires without error.

### 6.5 Interaction Edge Cases

#### EC-I01 — Rapid double-click on submit sends only one request
- **Setup:** Mock `requests.post` with a blocking delay. Fill fields. Trigger two click events in rapid succession.
- **Assert:** `requests.post` is called exactly once (button disabled after first click prevents the second).

#### EC-I02 — Stale error state is cleared on fresh page load
- **Setup:** Open `/login`, trigger a 401 error (error label appears). Navigate away. Navigate back to `/login`.
- **Assert:** Error label is invisible on the fresh load; no stale error text persists from the previous visit.

#### EC-I03 — `API_URL` not set in environment falls back to `http://localhost:8000`
- **Setup:** Patch `frontend.pages.login.API_URL` to `"http://localhost:8000"` (simulating unset env var with default). Mock `requests.post`. Fill fields. Click "Log in".
- **Assert:** `requests.post` URL starts with `http://localhost:8000`.

---

## 7. Test Data Reference

| Scenario | Username | Password | Mock | Expected outcome |
|---|---|---|---|---|
| Happy path | `alice` | `secret123` | `200` | Redirect to `/upload` |
| Wrong password | `alice` | `wrongpass` | `401` | "Invalid username or password." shown |
| Unknown user | `nobody` | `anypass` | `401` | "Invalid username or password." shown (same as wrong password) |
| Malformed request | `alice` | `secret` | `400 {"detail": "bad input"}` | "Invalid username or password." (detail NOT shown) |
| Backend crash | `alice` | `secret123` | `500` | "Server error. Please try again later." shown |
| Network down | `alice` | `secret123` | `ConnectionError` | "Could not reach the server. Check your connection." shown |
| Timeout | `alice` | `secret123` | `Timeout` | "Could not reach the server. Check your connection." shown |
| Empty username | `` | `secret123` | (no call) | Button stays disabled |
| Whitespace username | `   ` | `secret123` | (no call) | Button stays disabled |
| XSS in detail | `alice` | `pass` | `401 {"detail": "<script>alert(1)</script>"}` | Fixed message shown; detail never rendered |
| Unicode username | `用户名` | `pass🔑` | `200` | Redirect to `/upload`; payload encoded correctly |

---

## 8. Coverage Targets

| Area | Target |
|---|---|
| FR coverage | 100% — every FR in `02-login-page-ui.md` has at least one test |
| AC coverage | 100% — every AC has a direct mapping to a test case ID |
| Error status codes | All 6 error categories tested: 401, other 4xx, 5xx, ConnectionError, Timeout, generic exception |
| Enter key paths | Both valid and invalid state paths tested (UT-K01 through UT-K06) |
| Security scenarios | User enumeration, XSS, credential leak, request integrity, exception exposure |
| Edge cases | Whitespace, long input, Unicode, emoji, non-JSON responses, double-submit, stale state |

### FR → Test Mapping

| Requirement | Test IDs |
|---|---|
| FR-01 Route registration | UT-R01 |
| FR-02 Centered form layout | UT-R02, UT-R03, UT-R04, UT-R05, UT-R06, UT-R09 |
| FR-03 Input fields | UT-R04, UT-R05, ST-C02 |
| FR-04 Submit button state | UT-B01–UT-B06, EC-W01–EC-W03 |
| FR-05 API call on submit | UT-A01–UT-A05 |
| FR-06 Success redirect | UT-S01–UT-S04 |
| FR-07 Error handling | UT-E01–UT-E13, EC-N01–EC-N02 |
| FR-08 Enter key submission | UT-K01–UT-K06, EC-W04 |
| FR-09 Navigation link to signup | UT-R07, UT-N01 |

### AC → Test Mapping

| Acceptance Criterion | Test IDs |
|---|---|
| AC-01 Page renders at `/login` | UT-R01 |
| AC-02 Button disabled when both fields empty | UT-B01 |
| AC-03 Button disabled when one field filled | UT-B02, UT-B03 |
| AC-04 Button enabled when both fields non-empty | UT-B04 |
| AC-05 POST sent with correct body | UT-A01, UT-A02, UT-A03 |
| AC-06 2xx redirects to `/upload` | UT-S01, UT-S02 |
| AC-07 401 shows "Invalid username or password." inline | UT-E01, ST-U01 |
| AC-08 Other 4xx shows "Invalid username or password." | UT-E02, UT-E03, UT-E04 |
| AC-09 5xx shows server error message | UT-E05 |
| AC-10 Network error shows connection message | UT-E06, UT-E07 |
| AC-11 Button re-enabled after error | UT-E09, UT-E10, UT-E11 |
| AC-12 Password field masks characters | ST-C02 |
| AC-13 Enter submits form when both fields non-empty | UT-K01 |
| AC-14 Enter does nothing when a field is empty | UT-K02, UT-K03, UT-K04 |
| AC-15 "Sign up" link navigates to `/signup` | UT-N01 |
| AC-16 Renders correctly at 768px | (manual / visual regression — not automated) |
