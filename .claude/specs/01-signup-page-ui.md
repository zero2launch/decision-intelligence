# Feature Spec: Signup Page UI

**ID:** `01-signup-page-ui`
**Status:** Ready for implementation
**Route:** `/signup`
**Source story:** User signup page with NiceGUI frontend + FastAPI backend

---

## 1. Overview

A focused, full-screen signup page that lets a new user create an account by providing a username and password. The page communicates with the backend signup API and redirects to the file upload page on success. The page deliberately avoids the standard app shell (sidebar/header) to keep the flow distraction-free.

---

## 2. Functional Requirements

### FR-01 — Route Registration
The signup page must be registered at the `/signup` route inside the NiceGUI frontend app (`frontend/main.py`) using the `@ui.page('/signup')` decorator.

### FR-02 — Centered Signup Form
The page must render a vertically and horizontally centered card on a full-viewport background. No sidebar, no header, no navigation. The card contains:
- A page title/logo label ("Decision Intelligence" or equivalent)
- A subtitle ("Create your account")
- A Username input field
- A Password input field (masked, with visibility toggle)
- A Submit button
- An error feedback area

### FR-03 — Input Fields
| Field | Type | NiceGUI Component | Required |
|---|---|---|---|
| Username | Text | `ui.input('Username')` | Yes |
| Password | Password (masked) | `ui.input('Password', password=True, password_toggle_button=True)` | Yes |

Both fields must be `w-full` width within the card.

### FR-04 — Submit Button State
The Submit button must be **disabled** when either input field is empty. It becomes enabled only when both fields contain at least one non-whitespace character. This must be enforced client-side using NiceGUI's `bind_enabled_from` or an `on_change` handler — no round-trip to the backend for validation.

### FR-05 — API Call on Submit
Clicking Submit must:
1. Disable the button (prevent double-submit).
2. Send a synchronous `POST` request to `{API_URL}/api/signup` using the `requests` library, where `API_URL` is read from the `.env` file via `os.getenv('API_URL')`.
3. Send the payload as JSON: `{ "username": "<value>", "password": "<value>" }`.
4. Include the header `Content-Type: application/json`.

### FR-06 — Success Handling
If the API response status code is in the 2xx range (200–299):
1. Extract the `token` string from the JSON response body: `response.json().get("token", "")`.
2. Persist the token to the browser's `sessionStorage` using `ui.run_javascript`:
   ```python
   await ui.run_javascript(f"sessionStorage.setItem('auth_token', '{token}')")
   ```
3. Navigate the user to `/upload` using `ui.navigate.to('/upload')`.
- Do **not** display a success notification before navigating (redirect is the signal).
- If the response body is missing the `token` field (e.g. unexpected server shape), skip the `sessionStorage` write and still redirect — do not block navigation on a missing token.

### FR-07 — Error Handling
If the API response status code is outside the 2xx range, or if a network/connection error occurs:
- Re-enable the Submit button.
- Display an inline error message inside the error feedback area (visible label, not a toast).
- The user remains on the `/signup` page.
- The error message must reflect the nature of the failure:
  - 4xx response: show the `detail` field from the JSON response body, or a fallback generic message if the field is absent.
  - 5xx response: show "Server error. Please try again later."
  - Network/connection error: show "Could not reach the server. Check your connection."

### FR-08 — Navigation Link to Login
Below the Submit button, provide a small navigation link: "Already have an account? Log in" that routes the user to `/login`. This must be a `ui.link` or a clickable `ui.label` using `ui.navigate.to('/login')`.

---

## 3. Non-Functional Requirements

### NFR-01 — Styling
All styling must use Tailwind utility classes via NiceGUI's `.classes()` method. No inline `style=` attributes and no custom CSS files unless the required effect is impossible with Tailwind alone.

### NFR-02 — Responsiveness
The card must render correctly on desktop (1280px+) and tablet (768px). It must not overflow horizontally on smaller viewports. Use `w-full max-w-md` on the card container.

### NFR-03 — No Standard Shell
The page must not render the standard app shell (sidebar, header) defined in `ui-design.md`. This page is a standalone, full-screen flow.

### NFR-04 — Modularity
The page implementation must be broken into small, named Python functions — do not write a single monolithic `@ui.page` function body. At minimum, separate:
- `_build_card()` — renders the outer card container and header
- `_build_form(card)` — renders inputs, button, and error label inside the card

### NFR-05 — Environment Variable Isolation
`API_URL` must be loaded exactly once at module import time using `python-dotenv`'s `load_dotenv()` and `os.getenv('API_URL', 'http://localhost:8000')`. It must **not** be hardcoded anywhere in the page module.

### NFR-06 — Thread Safety
NiceGUI runs page handlers synchronously per client. The `requests` call is blocking; this is acceptable for this project and consistent with the existing frontend pattern (see CLAUDE.md).

The Submit button's `on_click` handler **must be declared `async`** because `ui.run_javascript()` (used to write the JWT to session storage in FR-06) is a coroutine and must be awaited. This is the only concession to async in this module — the rest of the handler (requests call, UI updates) remains synchronous within that async function. Do not introduce background tasks or `asyncio.run()`.

### NFR-07 — Error Visibility
The error label must always be allocated space in the DOM (use `.classes('invisible')` to hide it when empty, not `display:none`), so the card does not shift in size when an error appears.

---

## 4. Acceptance Criteria

| ID | Criterion | How to verify |
|---|---|---|
| AC-01 | Navigating to `http://localhost:8080/signup` renders the signup form without error | Manual browser check |
| AC-02 | The Submit button is disabled when both fields are empty | Observe button state on page load |
| AC-03 | The Submit button is disabled when only one field has a value | Enter text in one field only |
| AC-04 | The Submit button is enabled when both fields have non-empty values | Enter text in both fields |
| AC-05 | Clicking Submit with valid credentials sends `POST {API_URL}/api/signup` with correct JSON body | Inspect with network tab or backend log |
| AC-06 | A successful response redirects to `/upload` | Complete a signup with a fresh username |
| AC-07 | A 409 Conflict response (duplicate user) shows the backend error message inline | Attempt signup with an existing username |
| AC-08 | A 422 Unprocessable Entity response shows a descriptive error inline | Send malformed data (simulate via backend) |
| AC-09 | A network error (backend not running) shows "Could not reach the server" | Stop backend, attempt signup |
| AC-10 | The Submit button is re-enabled after any error so the user can retry | Trigger any error, observe button state |
| AC-11 | The "Already have an account? Log in" link navigates to `/login` | Click the link |
| AC-12 | The page renders correctly at 768px viewport width | Resize browser |
| AC-13 | After a successful signup, `sessionStorage.getItem('auth_token')` in the browser returns the JWT string returned by the API | Open DevTools → Application → Session Storage after signing up |
| AC-14 | If the API response is 2xx but has no `token` field, the user is still redirected to `/upload` without error | Simulate by returning a 200 with empty body |

---

## 5. Out of Scope

The following are explicitly excluded from this feature and must not be implemented:

- Password strength indicators or policy enforcement (minimum length, special characters, etc.)
- Social login providers (Google, GitHub, Microsoft, etc.)
- Email verification or account activation flows
- CAPTCHA, MFA, or any bot-protection mechanism
- User profile creation or account settings post-signup
- Confirm Password / repeat-password field (single password field only)
- Remember Me checkbox or session persistence options
- Terms of Service / Privacy Policy checkbox
- Inline username availability checking (no real-time API call while typing)

---

## 6. Design Rules

These rules are derived from `.claude/rules/ui-design.md` and `.claude/skills/auth-skill.md` and are binding for this page.

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
│          │  [Submit Button]             w-full bg-blue-600 text-white            │ │
│          │  [Login Link]                text-sm text-blue-600 self-center        │ │
│          └───────────────────────────────────────────────────────────────────────┘ │
│                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────┘
```

|

### 6.3 Spacing & Structure

- Card internal gap between sections: `gap-6` via `flex flex-col`
- Form elements stack vertically with `gap-4`
- Card padding: `p-8`
- Card must be `flex flex-col` so all children stack vertically

### 6.4 Component Naming Conventions

- Page module file: `frontend/pages/signup.py`
- `@ui.page('/signup')` function name: `signup_page()`
- Helper functions: `_build_card()`, `_build_form()`
- Local state variable for the error label reference: `error_label`

---

## 7. API Contract

### Endpoint
`POST {API_URL}/api/signup`

### Request
```json
{
  "username": "string",
  "password": "string"
}
```

### Success Response
- **Status:** `200 OK` or `201 Created`
- **Body:** `{ "token": "<jwt-string>" }` — the frontend reads `token` and writes it to `sessionStorage` under the key `auth_token` before redirecting.

### Error Responses

| Status | Meaning | Frontend action |
|---|---|---|
| `400 Bad Request` | Validation error or bad input | Show `detail` from response JSON |
| `409 Conflict` | Username already exists | Show `detail` from response JSON |
| `422 Unprocessable Entity` | Pydantic schema mismatch | Show `detail` from response JSON or generic message |
| `500 Internal Server Error` | Backend failure | Show "Server error. Please try again later." |
| Network error | Backend unreachable | Show "Could not reach the server. Check your connection." |

### Environment Variable
| Variable | Default | Source |
|---|---|---|
| `API_URL` | `http://localhost:8000` | `.env` in project root |

---

## 8. File & Module Layout

```
frontend/
├── main.py                   # imports pages.signup to register the route
└── pages/
    └── signup.py             # @ui.page('/signup') — self-contained module
```

`frontend/main.py` must contain an import of `frontend.pages.signup` (or equivalent relative import) so the `@ui.page` decorator fires and the route is registered before `ui.run()` is called.

---

## 9. Dependencies

| Package | Purpose | Already in pyproject.toml? |
|---|---|---|
| `nicegui` | UI framework | To be added |
| `requests` | Synchronous HTTP calls to backend | To be added |
| `python-dotenv` | Load `.env` at startup | To be added |

All packages must be added via `uv add <pkg>` and tracked in `pyproject.toml`.

---

## 10. Open Questions / Assumptions

| # | Question | Current Assumption |
|---|---|---|
| Q1 | Does the backend `/api/signup` endpoint return a JWT token on success? | **Yes** — per spec `03-signup-api.md`, the endpoint returns `{ "token": "<jwt-string>" }` on `201 Created`. The frontend extracts this token and writes it to `sessionStorage` under the key `auth_token` before redirecting (see FR-06). |
| Q2 | Is `/upload` page already implemented? | Assumed to exist (or will exist). The spec redirects to it unconditionally. |
| Q3 | Should the signup page be accessible when the user is already logged in? | Out of scope — no auth guard on `/signup` for this feature. |
| Q4 | What is the exact JSON field name the backend expects — `username` or `email`? | `username`, per the user story. Verify against the backend `SignupRequest` Pydantic schema before implementing. |
