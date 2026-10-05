import os

import requests
from dotenv import load_dotenv
from nicegui import ui

load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000")


@ui.page("/chatbot")
def chatbot_page() -> None:
    messages: list[dict] = []
    chat_column: ui.column | None = None
    message_input: ui.input | None = None
    send_btn: ui.button | None = None
    error_label: ui.label | None = None

    def _render_messages() -> None:
        chat_column.clear()
        if not messages:
            with chat_column:
                with ui.element("div").classes(
                    "flex flex-col items-center justify-center py-20 gap-6"
                ):
                    with ui.element("div").classes(
                        "w-20 h-20 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 "
                        "flex items-center justify-center shadow-lg"
                    ):
                        ui.icon("smart_toy").classes("text-white text-5xl")
                    with ui.element("div").classes("flex flex-col items-center gap-2 text-center"):
                        ui.label("How can I help you today?").classes(
                            "text-slate-700 text-xl font-semibold"
                        )
                        ui.label(
                            "Ask me anything about your uploaded documents."
                        ).classes("text-slate-400 text-sm")
        else:
            with chat_column:
                for msg in messages:
                    if msg["role"] == "user":
                        with ui.element("div").classes(
                            "flex items-end gap-3 justify-end w-full"
                        ):
                            with ui.element("div").classes(
                                "flex flex-col items-end gap-1"
                            ):
                                ui.label("You").classes(
                                    "text-xs text-slate-400 font-medium px-1"
                                )
                                ui.label(msg["content"]).classes(
                                    "bg-gradient-to-br from-blue-500 to-blue-700 text-white "
                                    "rounded-2xl rounded-tr-sm px-4 py-3 max-w-prose text-sm "
                                    "leading-relaxed shadow-md"
                                )
                            with ui.element("div").classes(
                                "w-8 h-8 rounded-full bg-blue-100 border-2 border-blue-300 "
                                "flex items-center justify-center flex-shrink-0"
                            ):
                                ui.icon("person").classes("text-blue-600 text-base")
                    else:
                        with ui.element("div").classes(
                            "flex items-end gap-3 justify-start w-full"
                        ):
                            with ui.element("div").classes(
                                "w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 "
                                "to-indigo-600 flex items-center justify-center "
                                "flex-shrink-0 shadow-sm"
                            ):
                                ui.icon("smart_toy").classes("text-white text-base")
                            with ui.element("div").classes(
                                "flex flex-col items-start gap-1"
                            ):
                                ui.label("AI Assistant").classes(
                                    "text-xs text-slate-400 font-medium px-1"
                                )
                                ui.label(msg["content"]).classes(
                                    "bg-white border border-slate-200 text-slate-700 "
                                    "rounded-2xl rounded-tl-sm px-4 py-3 max-w-prose text-sm "
                                    "leading-relaxed shadow-sm"
                                )
        ui.run_javascript(
            "document.getElementById('chat-scroll').scrollTop = "
            "document.getElementById('chat-scroll').scrollHeight"
        )

    def _update_send_button() -> None:
        if message_input.value and message_input.value.strip():
            send_btn.enable()
        else:
            send_btn.disable()

    async def _handle_send() -> None:
        user_text = message_input.value.strip() if message_input.value else ""
        if not user_text:
            return

        messages.append({"role": "user", "content": user_text})
        message_input.value = ""
        _update_send_button()
        _render_messages()
        error_label.classes(add="invisible", remove="visible")
        send_btn.disable()

        token = await ui.run_javascript("sessionStorage.getItem('auth_token') || ''")

        msg = None
        try:
            response = requests.post(
                f"{API_URL}/api/chat",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"question": user_text},
            )
            if 200 <= response.status_code < 300:
                reply_text = response.json().get("answer", "")
                messages.append({"role": "assistant", "content": reply_text})
                _render_messages()
                _update_send_button()
                return
            if response.status_code == 401:
                msg = "Session expired. Please log in again."
            elif response.status_code == 429:
                msg = "Too many requests. Please wait a moment and try again."
            elif response.status_code >= 500:
                msg = "Server error. Please try again later."
            else:
                try:
                    msg = response.json().get("detail") or "Request failed. Please try again."
                except Exception:
                    msg = "Request failed. Please try again."
        except requests.exceptions.ConnectionError:
            msg = "Could not reach the server. Check your connection."
        except requests.exceptions.Timeout:
            msg = "Could not reach the server. Check your connection."
        except Exception:
            msg = "An unexpected error occurred. Please try again."

        error_label.set_text(msg)
        error_label.classes(add="visible", remove="invisible")
        _update_send_button()

    def _build_header() -> None:
        with ui.header().classes(
            "bg-gradient-to-r from-blue-600 to-indigo-700 px-6 py-4 shadow-md "
            "flex items-center justify-between"
        ):
            with ui.element("div").classes("flex items-center gap-3"):
                with ui.element("div").classes(
                    "w-9 h-9 rounded-xl bg-white/20 flex items-center justify-center"
                ):
                    ui.icon("smart_toy").classes("text-white text-xl")
                with ui.element("div").classes("flex flex-col leading-tight"):
                    ui.label("Decision Intelligence").classes(
                        "text-xl font-bold text-white"
                    )
                    ui.label("Powered by AI").classes("text-xs text-blue-100 font-normal")
            with ui.element("div").classes("flex items-center gap-4"):
                ui.link("Upload Docs", target="/upload").classes(
                    "text-sm text-white/80 hover:text-white font-medium no-underline"
                )
                ui.separator().props("vertical").classes("bg-white/30 h-5")
                ui.link("Log out", target="/login").classes(
                    "text-sm text-white/80 hover:text-white font-medium no-underline"
                )

    def _build_chat_area(content_col: ui.column) -> ui.column:
        nonlocal chat_column
        with content_col:
            with ui.element("div").classes(
                "flex-1 overflow-y-auto p-6"
            ).props('id="chat-scroll"'):
                chat_column = ui.column().classes("w-full gap-5")
        return chat_column

    def _build_input_area(content_col: ui.column) -> None:
        nonlocal message_input, send_btn, error_label
        with content_col:
            with ui.element("div").classes(
                "sticky bottom-0 bg-white/95 backdrop-blur-sm "
                "border-t border-slate-200 px-6 pt-3 pb-5"
            ):
                error_label = ui.label("").classes(
                    "text-red-500 text-sm mb-2 invisible block"
                )
                with ui.element("div").classes(
                    "flex gap-3 items-center bg-slate-50 border border-slate-300 "
                    "rounded-2xl px-4 py-2 shadow-sm"
                ):
                    message_input = (
                        ui.input(
                            placeholder="Ask a question about your documents…",
                            on_change=lambda _: _update_send_button(),
                        )
                        .props("borderless")
                        .classes("flex-1 text-sm")
                    )
                    message_input.on(
                        "keydown.enter",
                        lambda _: _handle_send() if (
                            message_input.value
                            and message_input.value.strip()
                            and not send_btn._props.get("disabled", False)
                        ) else None,
                    )
                    send_btn = (
                        ui.button(icon="send", on_click=_handle_send)
                        .props("round")
                        .classes("bg-blue-600 text-white hover:bg-blue-700 shadow-sm")
                    )
                    send_btn.disable()

    _build_header()

    with ui.element("div").classes(
        "w-screen min-h-screen bg-gradient-to-br from-slate-50 via-blue-50/30 to-slate-50 "
        "flex flex-col"
    ):
        with ui.column().classes(
            "flex-1 flex flex-col max-w-3xl mx-auto w-full"
        ) as content_col:
            pass
        _build_chat_area(content_col)
        _build_input_area(content_col)

    _render_messages()
