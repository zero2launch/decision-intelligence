import base64
import os

import requests
from dotenv import load_dotenv
from nicegui import ui
from nicegui.events import UploadEventArguments

load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000")


def _format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


@ui.page("/upload")
def upload_page() -> None:
    staged_files: list[dict] = []
    file_list_column: ui.column | None = None
    validation_error_label: ui.label | None = None
    upload_error_label: ui.label | None = None
    upload_btn: ui.button | None = None
    progress_bar: ui.linear_progress | None = None

    def _refresh_file_list() -> None:
        file_list_column.clear()

        def _make_remove(idx: int):
            def _remove():
                staged_files.pop(idx)
                _refresh_file_list()
                _update_upload_button()
            return _remove

        with file_list_column:
            for i, file in enumerate(staged_files):
                with ui.row().classes("items-center gap-3 w-full"):
                    ui.label(file["filename"]).classes("text-sm font-medium text-slate-800 flex-1")
                    ui.label(_format_file_size(file["size"])).classes("text-xs text-slate-500")
                    ui.button(icon="close", on_click=_make_remove(i)).props("flat dense").classes(
                        "text-slate-400 hover:text-red-500"
                    )

    def _update_upload_button() -> None:
        if len(staged_files) >= 1:
            upload_btn.enable()
        else:
            upload_btn.disable()

    async def _handle_file_selected(e: UploadEventArguments) -> None:
        validation_error_label.classes(add="invisible", remove="visible")
        ext = e.file.name.rsplit(".", 1)[-1].lower() if "." in e.file.name else ""
        if ext not in {"txt", "pdf", "xls", "xlsx", "csv"}:
            validation_error_label.set_text(
                f"Unsupported file type: {e.file.name}. Only TXT, PDF, XLS, XLSX, and CSV files are accepted."
            )
            validation_error_label.classes(add="visible", remove="invisible")
            return
        raw = await e.file.read()
        content_b64 = base64.b64encode(raw).decode("utf-8")
        staged_files.append({"filename": e.file.name, "content": content_b64, "size": len(raw)})
        _refresh_file_list()
        _update_upload_button()

    async def _handle_upload_click() -> None:
        upload_btn.disable()
        progress_bar.set_visibility(True)
        upload_error_label.classes(add="invisible", remove="visible")
        token = await ui.run_javascript("sessionStorage.getItem('auth_token') || ''")
        msg = None
        try:
            response = requests.post(
                f"{API_URL}/api/upload",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"files": staged_files},
            )
            if 200 <= response.status_code < 300:
                progress_bar.set_visibility(False)
                ui.navigate.to("/chatbot")
                return
            if response.status_code == 401:
                msg = "Session expired. Please log in again."
            elif response.status_code == 413:
                msg = "Files are too large. Reduce the total size and try again."
            elif response.status_code >= 500:
                msg = "Server error. Please try again later."
            else:
                try:
                    msg = response.json().get("detail") or "Upload failed. Please try again."
                except Exception:
                    msg = "Upload failed. Please try again."
        except requests.exceptions.ConnectionError:
            msg = "Could not reach the server. Check your connection."
        except requests.exceptions.Timeout:
            msg = "Could not reach the server. Check your connection."
        except Exception:
            msg = "An unexpected error occurred. Please try again."
        progress_bar.set_visibility(False)
        upload_btn.enable()
        upload_error_label.set_text(msg)
        upload_error_label.classes(add="visible", remove="invisible")

    def _build_header() -> None:
        with ui.header().classes(
            "bg-white border-b border-slate-200 p-4 shadow-none flex items-center justify-between"
        ):
            ui.label("Decision Intelligence").classes("text-xl font-bold text-slate-800")
            with ui.element("div").classes("flex items-center gap-4"):
                ui.link("Chat", target="/chatbot").classes(
                    "text-sm text-slate-600 hover:text-blue-600 font-medium no-underline"
                )
                ui.separator().props("vertical").classes("bg-slate-300 h-5")
                ui.link("Log out", target="/login").classes(
                    "text-sm text-slate-600 hover:text-blue-600 font-medium no-underline"
                )

    def _build_upload_zone(content_col: ui.column) -> None:
        nonlocal validation_error_label
        with content_col:
            with ui.element("div").classes(
                "bg-white border-2 border-dashed border-slate-300 rounded-xl p-8 "
                "flex flex-col items-center gap-4 w-full"
            ):
                ui.icon("upload_file").classes("text-5xl text-slate-300")
                ui.upload(
                    multiple=True,
                    auto_upload=True,
                    on_upload=_handle_file_selected,
                ).props('accept=".txt,.pdf,.xls,.xlsx,.csv"').classes("w-full")
                ui.label("Accepted: TXT, PDF, XLS, XLSX, CSV").classes("text-xs text-slate-400")
                validation_error_label = ui.label("").classes("text-red-500 text-sm invisible")

    def _build_file_list(content_col: ui.column) -> ui.column:
        nonlocal file_list_column
        with content_col:
            with ui.element("div").classes(
                "bg-white border border-slate-200 rounded-lg p-4 w-full"
            ):
                file_list_column = ui.column().classes("w-full gap-2")
        return file_list_column

    def _build_actions(content_col: ui.column) -> None:
        nonlocal upload_error_label, upload_btn, progress_bar
        with content_col:
            upload_error_label = ui.label("").classes("text-red-500 text-sm invisible")
            progress_bar = ui.linear_progress(value=None).classes("w-full")
            progress_bar.set_visibility(False)
            upload_btn = ui.button("Upload", on_click=_handle_upload_click).classes(
                "w-full bg-blue-600 text-white hover:bg-blue-700"
            )
            upload_btn.disable()

    _build_header()

    with ui.element("div").classes("w-full min-h-screen bg-slate-50"):
        with ui.column().classes(
            "w-full max-w-2xl mx-auto p-6 flex flex-col gap-6"
        ) as content_col:
            with ui.column().classes("gap-1"):
                ui.label("Upload Documents").classes("text-xl font-semibold text-slate-900")
                ui.label("Select TXT, PDF, or Excel files to upload").classes(
                    "text-sm text-slate-500"
                )

        _build_upload_zone(content_col)
        _build_file_list(content_col)
        _build_actions(content_col)
