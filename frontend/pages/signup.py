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
            ui.label("Create your account").classes("text-sm text-slate-500")
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

        submit_btn = ui.button("Sign Up").classes(
            "w-full bg-blue-600 text-white hover:bg-blue-700"
        )
        submit_btn.disable()

        async def _handle_submit(_=None) -> None:
            submit_btn.disable()
            error_label.classes("invisible", remove="visible")
            error_label.classes(add="invisible")

            try:
                response = requests.post(
                    f"{API_URL}/api/signup",
                    json={
                        "username": username_input.value,
                        "password": password_input.value,
                    },
                    headers={"Content-Type": "application/json"},
                )
                if 200 <= response.status_code < 300:
                    token = response.json().get("token", "")
                    if token:
                        await ui.run_javascript(
                            f"sessionStorage.setItem('auth_token', '{token}')"
                        )
                    ui.navigate.to("/upload")
                    return

                if response.status_code >= 500:
                    msg = "Server error. Please try again later."
                else:
                    try:
                        detail = response.json().get("detail", "")
                        if isinstance(detail, list):
                            msg = detail[0].get("msg", "An error occurred.") if detail else "An error occurred."
                        else:
                            msg = str(detail) if detail else "An error occurred."
                    except Exception:
                        msg = "An error occurred."

            except requests.exceptions.ConnectionError:
                msg = "Could not reach the server. Check your connection."
            except requests.exceptions.Timeout:
                msg = "Could not reach the server. Check your connection."
            except Exception:
                msg = "Could not reach the server. Check your connection."

            error_label.set_text(msg)
            error_label.classes(remove="invisible")
            error_label.classes(add="visible")
            submit_btn.enable()

        submit_btn.on("click", _handle_submit)

        ui.label("Already have an account?").classes("text-sm text-slate-500 self-center")
        ui.link("Log in", target="/login").classes("text-sm text-blue-600 self-center")


@ui.page("/signup")
def signup_page() -> None:
    with ui.element("div").classes(
        "w-screen h-screen flex items-center justify-center bg-slate-50"
    ):
        card = _build_card()
        _build_form(card)
