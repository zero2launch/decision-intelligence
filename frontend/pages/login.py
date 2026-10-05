import os

import requests
from dotenv import load_dotenv
from nicegui import ui

load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000")


def _build_card() -> ui.column:
    with ui.column().classes(
        "w-full max-w-md flex flex-col gap-6 p-8 bg-white shadow-lg border border-slate-200 rounded-xl"
    ) as card:
        with ui.column().classes("gap-1"):
            ui.label("Decision Intelligence").classes("text-2xl font-bold text-slate-800")
            ui.label("Sign in to your account").classes("text-sm text-slate-500")
    return card


def _build_form(card: ui.column) -> None:
    with card:
        def _update_button_state(_=None) -> None:
            if username_input.value.strip() and password_input.value.strip():
                submit_btn.enable()
            else:
                submit_btn.disable()

        username_input = ui.input("Username", on_change=_update_button_state).classes("w-full")
        password_input = ui.input(
            "Password", password=True, password_toggle_button=True, on_change=_update_button_state
        ).classes("w-full")

        error_label = ui.label("").classes("text-red-500 text-sm invisible")

        submit_btn = ui.button("Log in").classes(
            "w-full bg-blue-600 text-white hover:bg-blue-700"
        )
        submit_btn.disable()

        def _handle_submit() -> None:
            if not username_input.value.strip() or not password_input.value.strip():
                return

            submit_btn.disable()
            error_label.classes(add="invisible", remove="visible")

            try:
                response = requests.post(
                    f"{API_URL}/api/login",
                    json={
                        "username": username_input.value,
                        "password": password_input.value,
                    },
                    headers={"Content-Type": "application/json"},
                )
                if 200 <= response.status_code < 300:
                    import json
                    token = response.json().get("token", "")
                    ui.run_javascript(f"sessionStorage.setItem('auth_token', {json.dumps(token)})")
                    ui.navigate.to("/upload")
                    return

                if response.status_code >= 500:
                    msg = "Server error. Please try again later."
                else:
                    msg = "Invalid username or password."

            except requests.exceptions.ConnectionError:
                msg = "Could not reach the server. Check your connection."
            except requests.exceptions.Timeout:
                msg = "Could not reach the server. Check your connection."
            except Exception:
                msg = "Could not reach the server. Check your connection."

            error_label.set_text(msg)
            error_label.classes(add="visible", remove="invisible")
            submit_btn.enable()

        submit_btn.on("click", lambda _: _handle_submit())
        password_input.on("keydown.enter", lambda _: _handle_submit())

        with ui.row().classes("self-center gap-1"):
            ui.label("Don't have an account?").classes("text-sm text-slate-500 self-center")
            ui.link("Sign up", target="/signup").classes("text-sm text-blue-600 self-center")


@ui.page("/login")
def login_page() -> None:
    with ui.element("div").classes(
        "w-screen h-screen flex items-center justify-center bg-slate-50"
    ):
        card = _build_card()
        _build_form(card)
