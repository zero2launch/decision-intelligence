# Feature Spec: Login Page UI

**ID:** `02-login-page-ui`
**Status:** Ready for implementation
**Route:** `/login`
**Source story:** User login page with NiceGUI frontend + FastAPI backend

---

## 1. Overview

A focused, full-screen login page that allows a registered user to authenticate by entering their username and password. The page communicates with the backend login API and redirects to the file upload page on success. Like the signup page, it deliberately avoids the standard app shell (sidebar/header) to keep the authentication flow distraction-free and consistent.

---

## 2. Functional Requirements

### FR-01 — Route Registration
The login page must be registered at the `/login` route inside the NiceGUI frontend app (`frontend/main.py`) using the `@ui.page('/login')` decorator. The module `pages.login` must be imported in `frontend/main.py` so the decorator fires before `ui.run()` is called.

### FR-02 — Centered Login Form
The page must render a vertically and horizontally centered card on a full-viewport background. No sidebar, no header, no navigation. The card contains:
- A page title/logo label ("Decision Intelligence" or equivalent)
- A subtitle ("Sign in to your account")
- A Username input field
- A Password input field (masked, with visibility toggle)
- An error feedback area
- A Submit button ("Log in")
- A navigation link to the signup page

### FR-03 — Input Fields
| Field    | Type              | NiceGUI Component                                              | Required |
|----------|-------------------|----------------------------------------------------------------|----------|
| Username | Text              | `ui.input('Username')`                                         | Yes      |
| Password | Password (masked) | `ui.input('Password', password=True, password_toggle_button=True)` | Yes  |

Both fields must be `w-full` width within the card.

### FR-04 — Submit Button State
The Submit button must be **disabled** when either input field is empty or contains only whitespace. It becomes enabled only when both fields contain at least one non-whitespace character. This must be enforced client-side via an `on('input', ...)` handler — no round-trip to the backend for validation.

### FR-05 — API Call on Submit
Clicking Submit must:
1. Disable the button (prevent double-submit).
2. Clear any previously displayed error message.
3. Send a synchronous `POST` request to `{API_URL}/api/login` using the `requests` library, where `API_URL` is read from the `.env` file via `os.getenv('API_URL')`.
4. Send the payload as JSON: `{ "username": "<value>", "password": "<value>" }`.
5. Include the header `Content-Type: application/json`.

### FR-06 — Success Handling
If the API response status code is in the 2xx range (200–299):
- Navigate the user to `/upload` using `ui.navigate.to('/upload')`.
- Do **not** display a success notification before navigating (redirect is the signal).

### FR-07 — Error Handling
If the API response status code is outside the 2xx range, or if a network/connection error occurs:
- Re-enable the Submit button.
- Display an inline error message inside the error feedback area (visible label, not a toast).
- The user remains on the `/login` page.
- Error messages must follow this mapping:

| Condition                      | Message to display                                        |
|--------------------------------|-----------------------------------------------------------|
| 401 Unauthorized               | "Invalid username or password."                           |
| Any other 4xx response         | "Invalid username or password."                           |
| 5xx response                   | "Server error. Please try again later."                   |
| `requests.ConnectionError`     | "Could not reach the server. Check your connection."      |
| `requests.Timeout`             | "Could not reach the server. Check your connection."      |
| Any other unexpected exception | "Could not reach the server. Check your connection."      |

> **Rationale for fixed 4xx message:** Login pages must not reveal whether the username or password was incorrect. Always showing "Invalid username or password." avoids user enumeration.

### FR-08 — Enter Key Submission
Pressing the **Enter** key while the password field is focused must submit the form, but only if both input fields contain valid (non-empty, non-whitespace) values. If either field is empty, the Enter key press must be ignored (no API call, no error displayed).

Implementation: attach an `on('keydown.enter', ...)` handler to the password input that calls `_handle_submit()` conditionally.

### FR-09 — Navigation Link to Signup
Below the Submit button, provide a small navigation cue: a label "Don't have an account?" followed by a `ui.link("Sign up", target="/signup")` that routes the user to `/signup`.

---

## 3. Non-Functional Requirements

### NFR-01 — Styling
All styling must use Tailwind utility classes via NiceGUI's `.classes()` method. No inline `style=` attributes and no custom CSS files unless the required effect is impossible with Tailwind alone.

### NFR-02 — Responsiveness
The card must render correctly on desktop (1280px+) and tablet (768px). It must not overflow horizontally on smaller viewports. Use `w-full max-w-md` on the card container.

### NFR-03 — No Standard Shell
The page must not render the standard app shell (sidebar, header) defined in `ui-design.md`. This page is a standalone, full-screen authentication flow.

### NFR-04 — Modularity
The page implementation must be broken into small, named Python functions — do not write a single monolithic `@ui.page` function body. At minimum, separate:
- `_build_card()` — renders the outer card container and header labels
- `_build_form(card)` — renders inputs, error label, button, and navigation link inside the card

### NFR-05 — Environment Variable Isolation
`API_URL` must be loaded exactly once at module import time using `python-dotenv`'s `load_dotenv()` and `os.getenv('API_URL', 'http://localhost:8000')`. It must **not** be hardcoded anywhere in the page module.

### NFR-06 — Thread Safety
NiceGUI runs page handlers synchronously per client. The `requests` call is blocking; this is acceptable and consistent with the existing signup page pattern (see `frontend/pages/signup.py`). Do not introduce `asyncio` or background tasks.

### NFR-07 — Error Label Visibility
The error label must always be allocated space in the DOM (use `.classes('invisible')` to hide it when empty, not `display:none`), so the card does not shift in size when an error appears or disappears.

### NFR-08 — Visual Consistency with Signup Page
The login page must be visually identical in structure and styling to `frontend/pages/signup.py`. Only the subtitle text, button label, API endpoint, error messages, and navigation link differ. This keeps the authentication flow cohesive.

---

## 4. Acceptance Criteria

| ID    | Criterion                                                                                                         | How to verify                                             |
|-------|-------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------|
| AC-01 | Navigating to `http://localhost:8080/login` renders the login form without error                                  | Manual browser check                                      |
| AC-02 | The Submit button is disabled when both fields are empty                                                          | Observe button state on page load                         |
| AC-03 | The Submit button is disabled when only one field has a value                                                     | Enter text in one field only                              |
| AC-04 | The Submit button is enabled when both fields have non-empty, non-whitespace values                               | Enter text in both fields                                 |
| AC-05 | Clicking Submit sends `POST {API_URL}/api/login` with JSON body `{"username": "...", "password": "..."}`         | Inspect network tab or backend logs                       |
| AC-06 | A successful 2xx response redirects to `/upload`                                                                  | Log in with valid credentials                             |
| AC-07 | A 401 response displays "Invalid username or password." inline and keeps the user on `/login`                    | Log in with wrong password                                |
| AC-08 | Any other 4xx response displays "Invalid username or password." inline                                            | Simulate a 400/422 from the backend                       |
| AC-09 | A 5xx response displays "Server error. Please try again later." inline                                            | Simulate a 500 from the backend                           |
| AC-10 | A network error (backend not running) displays "Could not reach the server. Check your connection." inline        | Stop the backend, attempt login                           |
| AC-11 | The Submit button is re-enabled after any error so the user can retry                                             | Trigger any error, observe button state                   |
| AC-12 | The password field masks entered characters                                                                       | Type in the password field, observe dots/asterisks        |
| AC-13 | Pressing Enter while focused on the password field submits the form when both fields are non-empty                | Fill both fields, focus password, press Enter             |
| AC-14 | Pressing Enter while focused on the password field does nothing when either field is empty                        | Leave one field empty, focus password, press Enter        |
| AC-15 | The "Sign up" link navigates to `/signup`                                                                         | Click the link                                            |
| AC-16 | The page renders correctly at 768px viewport width without horizontal overflow                                    | Resize browser to 768px width                             |

---

## 5. Out of Scope

The following are explicitly excluded from this feature and must not be implemented:

- Password strength validation or policy enforcement
- Social login providers (Google, GitHub, Microsoft, etc.)
- Email verification or account activation flows
- CAPTCHA, MFA, or any bot-protection mechanism
- User profile creation or account settings
- "Remember Me" checkbox or persistent session storage
- "Forgot Password" / password reset flow
- Auto-redirect if the user is already authenticated (no auth guard on `/login`)
- Token storage or session management (the login page's only job is to authenticate and redirect)
- Real-time username availability checking while typing

---

## 6. Design Rules

These rules are derived from `.claude/rules/ui-design.md` and must be followed exactly.

### 6.1 Layout Skeleton

```
┌─────────────────── w-screen h-screen bg-slate-50 (flex center) ───────────────────┐
│                                                                                    │
│          ┌──────────── max-w-md w-full bg-white rounded-xl shadow-lg ───────────┐ │
│          │  [Logo / App Title]          text-2xl font-bold text-slate-800        │ │
│          │  [Subtitle]                  text-sm text-slate-500                   │ │
│          │  ─────────────────────────────────────────────────────────────        │ │
│          │  [Username Input]            w-full                                   │ │
│          │  [Password Input + toggle]   w-full                                   │ │
│          │  [Error Label]               text-red-500 text-sm (invisible/visible) │ │
│          │  [Log in Button]             w-full bg-blue-600 text-white            │ │
│          │  [Sign up Link]              text-sm text-blue-600 self-center        │ │
│          └───────────────────────────────────────────────────────────────────────┘ │
│                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Color & Typography Tokens

| Element        | Tailwind classes                                              |
|----------------|---------------------------------------------------------------|
| Page bg        | `bg-slate-50`                                                 |
| Card           | `bg-white shadow-lg border border-slate-200 rounded-xl`       |
| App title      | `text-2xl font-bold text-slate-800`                           |
| Subtitle       | `text-sm text-slate-500`                                      |
| Error label    | `text-red-500 text-sm` + `invisible` / `visible`              |
| Submit button  | `w-full bg-blue-600 text-white hover:bg-blue-700`             |
| Nav link       | `text-sm text-blue-600 self-center`                           |
| Nav label      | `text-sm text-slate-500 self-center`                          |

### 6.3 Spacing & Structure

- Card internal gap between sections: `gap-6` via `flex flex-col`
- Form elements stack vertically with `gap-4`
- Card padding: `p-8`
- Card must be `flex flex-col` so all children stack vertically

### 6.4 Component Naming Conventions

- Page module file: `frontend/pages/login.py`
- `@ui.page('/login')` function name: `login_page()`
- Helper functions: `_build_card()`, `_build_form(card)`
- Local state variable for the error label reference: `error_label`
- Local state variable for the submit button reference: `submit_btn`

---

## 7. API Contract

### Endpoint
`POST {API_URL}/api/login`

### Request
```json
{
  "username": "string",
  "password": "string"
}
```

### Success Response
- **Status:** `200 OK`
- **Body:** May contain a JWT token or session info — the frontend ignores the body and only uses the status code to trigger the redirect.

### Error Responses

| Status                  | Meaning                   | Frontend action                                           |
|-------------------------|---------------------------|-----------------------------------------------------------|
| `401 Unauthorized`      | Invalid credentials       | Show "Invalid username or password."                      |
| `400 Bad Request`       | Malformed request         | Show "Invalid username or password."                      |
| `422 Unprocessable`     | Schema mismatch           | Show "Invalid username or password."                      |
| `500 Internal Error`    | Backend failure           | Show "Server error. Please try again later."              |
| Network / `ConnectionError` | Backend unreachable   | Show "Could not reach the server. Check your connection." |

### Environment Variable

| Variable  | Default                    | Source            |
|-----------|----------------------------|-------------------|
| `API_URL` | `http://localhost:8000`    | `.env` in project root |

---

## 8. File & Module Layout

```
frontend/
├── main.py                   # must import pages.login to register the route
└── pages/
    ├── signup.py             # existing — reference implementation for style consistency
    └── login.py              # new — @ui.page('/login'), self-contained module
```

`frontend/main.py` must contain `import pages.login  # noqa: F401` alongside the existing `import pages.signup` so the route is registered before `ui.run()` is called.

---

## 9. Dependencies

All dependencies are already in `pyproject.toml` from the signup page feature. No new packages are required.

| Package        | Purpose                              | Status in pyproject.toml |
|----------------|--------------------------------------|--------------------------|
| `nicegui`      | UI framework                         | Already added            |
| `requests`     | Synchronous HTTP calls to backend    | Already added            |
| `python-dotenv`| Load `.env` at startup               | Already added            |

---

## 10. Open Questions / Assumptions

| #  | Question                                                                          | Current Assumption                                                                                                  |
|----|-----------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| Q1 | Does the backend `/api/login` return a JWT token on success?                      | Possibly — but the frontend ignores the response body for this feature. Token storage is out of scope.              |
| Q2 | What HTTP status code does the backend return for invalid credentials?             | Assumed `401 Unauthorized`. Verify against `src/api/auth.py` before implementing `_handle_submit`.                 |
| Q3 | Is `/upload` page already implemented?                                             | Assumed to exist (or will exist). The spec redirects unconditionally.                                               |
| Q4 | Should the login page redirect away if the user is already authenticated?          | No auth guard — out of scope for this feature.                                                                       |
| Q5 | What are the exact JSON field names the backend login endpoint expects?            | `username` and `password`, consistent with the signup endpoint. Verify against the backend `LoginRequest` schema.   |
