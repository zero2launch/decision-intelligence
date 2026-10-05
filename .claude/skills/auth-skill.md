# UI-Skill: Authentication (Login & Signup)

## 1. Page Purpose & UX Goal
**Purpose:** Provide a secure, seamless entry point into the Decision Intelligence application. 
**UX Goal:** Present a clean, distraction-free interface that handles both user registration and login. The transition between "Login" and "Signup" states should be instant and intuitive, relying on clear client-side validation to prevent unnecessary backend calls.

## 2. Structural Layout (The Skeleton)
The page discards the standard app shell (sidebar/header) in favor of a focused, full-screen layout.

- **Background Wrapper:** A full viewport flex container centering its children (`w-screen h-screen flex items-center justify-center bg-slate-50`).
- **Auth Card:** A central, constrained column (`w-full max-w-md flex flex-col gap-6 p-8 bg-white shadow-lg border border-slate-200 rounded-xl`).
- **Header Section:** Logo/Title and a brief subtitle (e.g., "Welcome back" or "Create your account").
- **Form Section:** A vertical stack of inputs and the primary action button.
- **Footer Section:** A toggle link to switch the form mode.

## 3. Component Breakdown

### Inputs
- **Email Input:** `ui.input('Email').classes('w-full')`. Must include basic client-side email format validation.
- **Password Input:** `ui.input('Password', password=True, password_toggle_button=True).classes('w-full')`.
- **Confirm Password (Signup Only):** `ui.input('Confirm Password', password=True).classes('w-full')`. Only visible when the state is set to 'signup'.

### Buttons & Toggles
- **Submit Button:** `ui.button('Sign In' / 'Sign Up').classes('w-full mt-4 bg-blue-600 text-white hover:bg-blue-700')`.
- **Mode Toggle:** `ui.link('Need an account? Sign up', target='#').classes('text-sm text-blue-600 hover:text-blue-800 self-center mt-2')`. Clicking this mutates the UI state variable to swap the form layout.

### Feedback Elements
- **Error Banner:** A `ui.label().classes('text-red-500 text-sm bg-red-50 p-2 rounded hidden')`. Used to display backend errors (e.g., 401 Unauthorized, 400 Bad Request).

## 4. Dynamic States & Auth Interactions
- **Loading State:** Upon clicking the submit button, disable the button and change its text/icon to a spinner (`ui.spinner(size='sm')`) to prevent double-submissions while the FastAPI backend hashes and verifies the bcrypt payload.
- **Validation State:** For signup, if `password != confirm_password`, immediately show an inline error beneath the inputs and keep the submit button disabled.
- **Success State:** Upon successful login or signup, trigger a `ui.notify('Success', type='positive')` and immediately use `ui.navigate.to('/dashboard')` to route the user into the main application.

## 5. Data Integration Points
Claude should expect the following integration patterns for the FastAPI backend:

- **State Management:** A local boolean or string (e.g., `is_login_mode = True`) to track which form is actively rendering.
- **Login API:**
  - `POST /api/auth/login`
  - Needs to handle the `python-jose` generated JWT.
  - Must parse `{ "access_token": "...", "token_type": "bearer" }` and store it (e.g., in `app.storage.user` or local storage depending on NiceGUI configuration).
- **Signup API:**
  - `POST /api/auth/signup`
  - Expects `{ "email": "...", "password": "..." }` matching the Pydantic schema.