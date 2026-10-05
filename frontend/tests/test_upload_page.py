import asyncio
import base64
import os
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("API_URL", "http://test-backend:8000")

from nicegui import ui
from nicegui.testing import User

import frontend.pages.upload  # noqa: F401 — registers @ui.page('/upload')
from frontend.pages.upload import _format_file_size


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_upload_event(filename: str, content: bytes, mime: str = "text/plain") -> MagicMock:
    e = MagicMock()
    e.name = filename
    e.content = BytesIO(content)
    e.type = mime
    return e


def _get_upload_handler(user: User):
    """Extract the on_upload callback from the rendered upload element."""
    elements = list(user.find(ui.upload).elements)
    assert elements, "No ui.upload element found"
    el = elements[0]
    listeners = el._event_listeners.get("upload", [])
    assert listeners, "No 'upload' event listener on upload element"
    return listeners[0].callback


def _inject_file(user: User, filename: str, content: bytes, mime: str = "text/plain") -> None:
    _get_upload_handler(user)(_make_upload_event(filename, content, mime))


def _get_close_buttons(user: User) -> list:
    """Return all close-icon button elements currently in the DOM."""
    return [
        el for el in user.find(ui.button).elements
        if el._props.get("icon") == "close"
    ]


def _click_element(el) -> None:
    """Fire the click event listener on a NiceGUI element."""
    for listener in el._event_listeners.get("click", []):
        listener.callback()


async def _click_upload_with_mocks(user: User, mock_post, token: str = "test-jwt-token") -> None:
    """Click Upload with ui.run_javascript mocked, then drain the event loop."""
    with patch("nicegui.ui.run_javascript", new_callable=AsyncMock) as mock_js:
        mock_js.return_value = token
        user.find("Upload").click()
        await asyncio.sleep(0.15)


# ---------------------------------------------------------------------------
# 3.1 Page Rendering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_r01_page_loads(user: User):
    await user.open("/upload")


@pytest.mark.asyncio
async def test_r02_header_displays_app_name(user: User):
    await user.open("/upload")
    await user.should_see("Decision Intelligence")


@pytest.mark.asyncio
async def test_r03_page_title_visible(user: User):
    await user.open("/upload")
    await user.should_see("Upload Documents")


@pytest.mark.asyncio
async def test_r04_page_subtitle_visible(user: User):
    await user.open("/upload")
    await user.should_see("Select TXT, PDF, or Excel files to upload")


@pytest.mark.asyncio
async def test_r05_upload_component_rendered(user: User):
    await user.open("/upload")
    elements = list(user.find(ui.upload).elements)
    assert len(elements) == 1


@pytest.mark.asyncio
async def test_r06_accepted_types_hint_visible(user: User):
    await user.open("/upload")
    await user.should_see("TXT, PDF, XLS, XLSX")


@pytest.mark.asyncio
async def test_r07_upload_button_rendered(user: User):
    await user.open("/upload")
    await user.should_see("Upload")


@pytest.mark.asyncio
async def test_r08_upload_button_disabled_on_load(user: User):
    await user.open("/upload")
    assert not user.find("Upload").enabled


@pytest.mark.asyncio
async def test_r09_progress_bar_not_visible_on_load(user: User):
    await user.open("/upload")
    els = list(user.find(ui.linear_progress).elements)
    assert els, "No linear_progress found"
    assert not els[0]._visible


@pytest.mark.asyncio
async def test_r10_validation_error_label_invisible_on_load(user: User):
    await user.open("/upload")
    await user.should_not_see("Unsupported file type")


@pytest.mark.asyncio
async def test_r11_upload_error_label_invisible_on_load(user: User):
    await user.open("/upload")
    await user.should_not_see("Session expired")
    await user.should_not_see("Server error")
    await user.should_not_see("Upload failed")


@pytest.mark.asyncio
async def test_r12_staged_file_list_empty_on_load(user: User):
    await user.open("/upload")
    await user.should_not_see(".txt")
    await user.should_not_see(".pdf")


@pytest.mark.asyncio
async def test_r13_standard_header_not_full_screen_auth_layout(user: User):
    await user.open("/upload")
    header_els = list(user.find(ui.header).elements)
    assert header_els, "Expected a header element"


# ---------------------------------------------------------------------------
# 3.2 File Extension Validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_v01_txt_accepted(user: User):
    await user.open("/upload")
    _inject_file(user, "report.txt", b"hello")
    await user.should_not_see("Unsupported file type")
    await user.should_see("report.txt")


@pytest.mark.asyncio
async def test_v02_pdf_accepted(user: User):
    await user.open("/upload")
    _inject_file(user, "document.pdf", b"%PDF-1.4")
    await user.should_not_see("Unsupported file type")
    await user.should_see("document.pdf")


@pytest.mark.asyncio
async def test_v03_xls_accepted(user: User):
    await user.open("/upload")
    _inject_file(user, "data.xls", b"\xD0\xCF\x11\xE0")
    await user.should_not_see("Unsupported file type")
    await user.should_see("data.xls")


@pytest.mark.asyncio
async def test_v04_xlsx_accepted(user: User):
    await user.open("/upload")
    _inject_file(user, "spreadsheet.xlsx", b"PK\x03\x04")
    await user.should_not_see("Unsupported file type")
    await user.should_see("spreadsheet.xlsx")


@pytest.mark.asyncio
async def test_v05_jpg_rejected(user: User):
    await user.open("/upload")
    _inject_file(user, "photo.jpg", b"\xFF\xD8\xFF")
    await user.should_see("photo.jpg")
    await user.should_see("Unsupported file type")
    assert not user.find("Upload").enabled


@pytest.mark.asyncio
async def test_v06_docx_rejected(user: User):
    await user.open("/upload")
    _inject_file(user, "letter.docx", b"PK\x03\x04")
    await user.should_see("letter.docx")
    await user.should_see("Unsupported file type")


@pytest.mark.asyncio
async def test_v07_exe_rejected(user: User):
    await user.open("/upload")
    _inject_file(user, "program.exe", b"MZ\x90\x00")
    await user.should_see("Unsupported file type")
    assert not user.find("Upload").enabled


@pytest.mark.asyncio
async def test_v08_csv_rejected(user: User):
    await user.open("/upload")
    _inject_file(user, "data.csv", b"a,b,c")
    await user.should_see("Unsupported file type")
    assert not user.find("Upload").enabled


@pytest.mark.asyncio
async def test_v09_pdf_upper_case_accepted(user: User):
    await user.open("/upload")
    _inject_file(user, "DOCUMENT.PDF", b"%PDF")
    await user.should_not_see("Unsupported file type")
    await user.should_see("DOCUMENT.PDF")


@pytest.mark.asyncio
async def test_v10_txt_upper_case_accepted(user: User):
    await user.open("/upload")
    _inject_file(user, "NOTES.TXT", b"text")
    await user.should_not_see("Unsupported file type")


@pytest.mark.asyncio
async def test_v11_xls_xlsx_upper_case_accepted(user: User):
    await user.open("/upload")
    _inject_file(user, "DATA.XLS", b"\xD0\xCF")
    await user.should_not_see("Unsupported file type")
    _inject_file(user, "DATA.XLSX", b"PK\x03\x04")
    await user.should_not_see("Unsupported file type")


@pytest.mark.asyncio
async def test_v12_multiple_dots_uses_last_extension(user: User):
    await user.open("/upload")
    _inject_file(user, "report.2024.final.pdf", b"%PDF")
    await user.should_not_see("Unsupported file type")
    await user.should_see("report.2024.final.pdf")


@pytest.mark.asyncio
async def test_v13_no_extension_rejected(user: User):
    await user.open("/upload")
    _inject_file(user, "README", b"readme content")
    await user.should_see("Unsupported file type")
    assert not user.find("Upload").enabled


@pytest.mark.asyncio
async def test_v14_validation_error_contains_filename(user: User):
    await user.open("/upload")
    _inject_file(user, "badfile.mp4", b"\x00")
    await user.should_see("badfile.mp4")


@pytest.mark.asyncio
async def test_v15_validation_error_mentions_supported_types(user: User):
    await user.open("/upload")
    _inject_file(user, "image.png", b"\x89PNG")
    await user.should_see("TXT")
    await user.should_see("PDF")
    await user.should_see("XLS")
    await user.should_see("XLSX")


@pytest.mark.asyncio
async def test_v16_validation_error_clears_on_valid_file(user: User):
    await user.open("/upload")
    _inject_file(user, "bad.jpg", b"\xFF\xD8")
    await user.should_see("Unsupported file type")
    _inject_file(user, "good.txt", b"hello")
    await user.should_not_see("Unsupported file type")


@pytest.mark.asyncio
async def test_v17_validation_error_updates_on_second_invalid(user: User):
    await user.open("/upload")
    _inject_file(user, "bad.jpg", b"\xFF\xD8")
    await user.should_see("bad.jpg")
    _inject_file(user, "worse.mp4", b"\x00")
    await user.should_see("worse.mp4")


# ---------------------------------------------------------------------------
# 3.3 Base64 Encoding (verified via POST request body on upload click)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_b01_text_file_encoded_correctly(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "hello.txt", b"Hello, World!")
        await _click_upload_with_mocks(user, mock_post)
        body = mock_post.call_args[1]["json"]
        expected = base64.b64encode(b"Hello, World!").decode("utf-8")
        assert body["files"][0]["content"] == expected


@pytest.mark.asyncio
async def test_b02_binary_file_round_trips(user: User):
    raw = b"\x00\x01\x02\xFF\xFE\xFD"
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "doc.pdf", raw)
        await _click_upload_with_mocks(user, mock_post)
        body = mock_post.call_args[1]["json"]
        decoded = base64.b64decode(body["files"][0]["content"])
        assert decoded == raw


@pytest.mark.asyncio
async def test_b03_base64_string_is_valid(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "data.xlsx", b"any binary content")
        await _click_upload_with_mocks(user, mock_post)
        body = mock_post.call_args[1]["json"]
        base64.b64decode(body["files"][0]["content"])  # must not raise


@pytest.mark.asyncio
async def test_b04_empty_file_produces_empty_base64(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "empty.txt", b"")
        await _click_upload_with_mocks(user, mock_post)
        body = mock_post.call_args[1]["json"]
        assert body["files"][0]["content"] == ""


@pytest.mark.asyncio
async def test_b05_size_field_records_original_byte_count(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "data.txt", b"12345")
        await _click_upload_with_mocks(user, mock_post)
        body = mock_post.call_args[1]["json"]
        assert body["files"][0]["size"] == 5


# ---------------------------------------------------------------------------
# 3.4 Staged File List Management
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l01_one_valid_file_adds_row(user: User):
    await user.open("/upload")
    _inject_file(user, "report.txt", b"hi")
    await user.should_see("report.txt")


@pytest.mark.asyncio
async def test_l02_two_valid_files_both_in_list(user: User):
    await user.open("/upload")
    _inject_file(user, "a.txt", b"a")
    _inject_file(user, "b.pdf", b"b")
    await user.should_see("a.txt")
    await user.should_see("b.pdf")


@pytest.mark.asyncio
async def test_l03_three_valid_files_all_in_list(user: User):
    await user.open("/upload")
    for name in ("x.txt", "y.pdf", "z.xlsx"):
        _inject_file(user, name, b"data")
    await user.should_see("x.txt")
    await user.should_see("y.pdf")
    await user.should_see("z.xlsx")


@pytest.mark.asyncio
async def test_l04_file_row_displays_filename(user: User):
    await user.open("/upload")
    _inject_file(user, "report.pdf", b"content")
    await user.should_see("report.pdf")


@pytest.mark.asyncio
async def test_l05_file_row_displays_human_readable_size(user: User):
    await user.open("/upload")
    _inject_file(user, "file.txt", b"x" * 2048)
    await user.should_see("2.0 KB")


@pytest.mark.asyncio
async def test_l06_file_row_has_remove_button(user: User):
    await user.open("/upload")
    _inject_file(user, "test.txt", b"data")
    assert len(_get_close_buttons(user)) >= 1


@pytest.mark.asyncio
async def test_l07_remove_button_removes_only_that_file(user: User):
    await user.open("/upload")
    _inject_file(user, "file_a.txt", b"aaa")
    _inject_file(user, "file_b.pdf", b"bbb")
    btns = _get_close_buttons(user)
    assert len(btns) == 2
    _click_element(btns[0])
    await user.should_not_see("file_a.txt")
    await user.should_see("file_b.pdf")


@pytest.mark.asyncio
async def test_l08_removing_last_file_empties_list(user: User):
    await user.open("/upload")
    _inject_file(user, "only.txt", b"x")
    _click_element(_get_close_buttons(user)[0])
    await user.should_not_see("only.txt")
    assert not user.find("Upload").enabled


@pytest.mark.asyncio
async def test_l09_invalid_file_not_added_to_list(user: User):
    await user.open("/upload")
    _inject_file(user, "photo.jpg", b"\xFF\xD8\xFF")
    # "photo.jpg" appears in error message, not a file row — button still disabled
    assert not user.find("Upload").enabled


# ---------------------------------------------------------------------------
# 3.5 Upload Button State
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ub01_button_disabled_on_load(user: User):
    await user.open("/upload")
    assert not user.find("Upload").enabled


@pytest.mark.asyncio
async def test_ub02_button_enabled_after_one_valid_file(user: User):
    await user.open("/upload")
    _inject_file(user, "doc.txt", b"x")
    assert user.find("Upload").enabled


@pytest.mark.asyncio
async def test_ub03_button_enabled_after_multiple_valid_files(user: User):
    await user.open("/upload")
    for name in ("a.txt", "b.pdf", "c.xls"):
        _inject_file(user, name, b"data")
    assert user.find("Upload").enabled


@pytest.mark.asyncio
async def test_ub04_button_remains_disabled_after_invalid_file(user: User):
    await user.open("/upload")
    _inject_file(user, "bad.jpg", b"\xFF\xD8")
    assert not user.find("Upload").enabled


@pytest.mark.asyncio
async def test_ub05_button_disabled_when_last_file_removed(user: User):
    await user.open("/upload")
    _inject_file(user, "only.txt", b"x")
    assert user.find("Upload").enabled
    _click_element(_get_close_buttons(user)[0])
    assert not user.find("Upload").enabled


@pytest.mark.asyncio
async def test_ub06_button_remains_enabled_when_one_of_two_removed(user: User):
    await user.open("/upload")
    _inject_file(user, "a.txt", b"a")
    _inject_file(user, "b.pdf", b"b")
    _click_element(_get_close_buttons(user)[0])
    assert user.find("Upload").enabled


@pytest.mark.asyncio
async def test_ub08_button_reenabled_after_upload_failure(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=500)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        assert user.find("Upload").enabled


# ---------------------------------------------------------------------------
# 3.6 Upload API Call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a01_post_sent_to_correct_url(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "report.txt", b"hi")
        await _click_upload_with_mocks(user, mock_post)
        assert mock_post.call_args[0][0] == "http://test-backend:8000/api/upload"


@pytest.mark.asyncio
async def test_a02_request_body_contains_files_array(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "report.txt", b"hello")
        await _click_upload_with_mocks(user, mock_post)
        assert "files" in mock_post.call_args[1]["json"]


@pytest.mark.asyncio
async def test_a03_each_entry_has_required_fields(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "report.txt", b"hello")
        await _click_upload_with_mocks(user, mock_post)
        entry = mock_post.call_args[1]["json"]["files"][0]
        assert "filename" in entry
        assert "content" in entry
        assert "size" in entry


@pytest.mark.asyncio
async def test_a04_filename_field_matches_original(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "my_report.pdf", b"data")
        await _click_upload_with_mocks(user, mock_post)
        assert mock_post.call_args[1]["json"]["files"][0]["filename"] == "my_report.pdf"


@pytest.mark.asyncio
async def test_a05_content_is_valid_base64_of_file_bytes(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "data.txt", b"test content")
        await _click_upload_with_mocks(user, mock_post)
        content_b64 = mock_post.call_args[1]["json"]["files"][0]["content"]
        assert base64.b64decode(content_b64) == b"test content"


@pytest.mark.asyncio
async def test_a06_size_field_matches_byte_length(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "data.txt", b"abcde")
        await _click_upload_with_mocks(user, mock_post)
        assert mock_post.call_args[1]["json"]["files"][0]["size"] == 5


@pytest.mark.asyncio
async def test_a07_multiple_files_sent_in_single_request(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "a.txt", b"aaa")
        _inject_file(user, "b.pdf", b"bbbbb")
        await _click_upload_with_mocks(user, mock_post)
        files = mock_post.call_args[1]["json"]["files"]
        assert len(files) == 2
        names = {f["filename"] for f in files}
        assert names == {"a.txt", "b.pdf"}


@pytest.mark.asyncio
async def test_a08_request_includes_content_type_header(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        headers = mock_post.call_args[1]["headers"]
        assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_a09_request_includes_authorization_header(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        with patch("nicegui.ui.run_javascript", new_callable=AsyncMock) as mock_js:
            mock_js.return_value = "test-jwt-token"
            user.find("Upload").click()
            await asyncio.sleep(0.15)
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test-jwt-token"


@pytest.mark.asyncio
async def test_a10_api_url_from_env(user: User):
    with patch("frontend.pages.upload.API_URL", "http://custom-host:9000"):
        with patch("frontend.pages.upload.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
            await user.open("/upload")
            _inject_file(user, "doc.txt", b"x")
            await _click_upload_with_mocks(user, mock_post)
            assert mock_post.call_args[0][0].startswith("http://custom-host:9000")


@pytest.mark.asyncio
async def test_a11_upload_not_triggered_by_file_selection(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# 3.7 Progress Bar Behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p01_progress_bar_hidden_on_load(user: User):
    await user.open("/upload")
    els = list(user.find(ui.linear_progress).elements)
    assert els and not els[0]._visible


@pytest.mark.asyncio
async def test_p03_progress_bar_hidden_after_successful_upload(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        els = list(user.find(ui.linear_progress).elements)
        assert els and not els[0]._visible


@pytest.mark.asyncio
async def test_p04_progress_bar_hidden_after_4xx_failure(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=401)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        els = list(user.find(ui.linear_progress).elements)
        assert els and not els[0]._visible


@pytest.mark.asyncio
async def test_p05_progress_bar_hidden_after_5xx_failure(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=500)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        els = list(user.find(ui.linear_progress).elements)
        assert els and not els[0]._visible


@pytest.mark.asyncio
async def test_p06_progress_bar_hidden_after_network_error(user: User):
    import requests as req
    with patch("frontend.pages.upload.requests.post", side_effect=req.exceptions.ConnectionError):
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, None)
        els = list(user.find(ui.linear_progress).elements)
        assert els and not els[0]._visible


# ---------------------------------------------------------------------------
# 3.8 Success Handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s01_redirect_to_chatbot_on_200(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        assert user.current_page_url.path == "/chatbot"


@pytest.mark.asyncio
async def test_s02_redirect_to_chatbot_on_201(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        assert user.current_page_url.path == "/chatbot"


@pytest.mark.asyncio
async def test_s03_no_error_label_on_success(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        await user.should_not_see("Session expired")
        await user.should_not_see("Server error")
        await user.should_not_see("Upload failed")


@pytest.mark.asyncio
async def test_s04_redirect_fires_even_if_json_raises(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        resp = MagicMock(status_code=200)
        resp.json.side_effect = ValueError("no body")
        mock_post.return_value = resp
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        assert user.current_page_url.path == "/chatbot"


# ---------------------------------------------------------------------------
# 3.9 Error Handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e01_401_shows_session_expired(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=401)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        await user.should_see("Session expired. Please log in again.")


@pytest.mark.asyncio
async def test_e02_413_shows_file_size_error(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=413)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        await user.should_see("Files are too large.")


@pytest.mark.asyncio
async def test_e03_400_shows_detail_from_body(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=400, json=lambda: {"detail": "Invalid file format"}
        )
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        await user.should_see("Invalid file format")


@pytest.mark.asyncio
async def test_e04_400_no_detail_shows_fallback(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=400, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        await user.should_see("Upload failed. Please try again.")


@pytest.mark.asyncio
async def test_e05_422_shows_detail_from_body(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=422, json=lambda: {"detail": "Schema mismatch"}
        )
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        await user.should_see("Schema mismatch")


@pytest.mark.asyncio
async def test_e06_500_shows_server_error(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=500)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        await user.should_see("Server error. Please try again later.")


@pytest.mark.asyncio
async def test_e07_connection_error_shows_message(user: User):
    import requests as req
    with patch("frontend.pages.upload.requests.post", side_effect=req.exceptions.ConnectionError):
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, None)
        await user.should_see("Could not reach the server. Check your connection.")


@pytest.mark.asyncio
async def test_e08_timeout_shows_connection_message(user: User):
    import requests as req
    with patch("frontend.pages.upload.requests.post", side_effect=req.exceptions.Timeout):
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, None)
        await user.should_see("Could not reach the server. Check your connection.")


@pytest.mark.asyncio
async def test_e09_generic_exception_shows_unexpected_error(user: User):
    with patch("frontend.pages.upload.requests.post", side_effect=Exception("unexpected")):
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, None)
        await user.should_see("An unexpected error occurred. Please try again.")


@pytest.mark.asyncio
async def test_e10_button_reenabled_after_4xx(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=401)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        assert user.find("Upload").enabled


@pytest.mark.asyncio
async def test_e11_button_reenabled_after_5xx(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=500)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        assert user.find("Upload").enabled


@pytest.mark.asyncio
async def test_e12_button_reenabled_after_network_error(user: User):
    import requests as req
    with patch("frontend.pages.upload.requests.post", side_effect=req.exceptions.ConnectionError):
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, None)
        assert user.find("Upload").enabled


@pytest.mark.asyncio
async def test_e13_page_remains_on_upload_after_error(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=500)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        assert user.current_page_url.path == "/upload"


@pytest.mark.asyncio
async def test_e14_previous_error_hidden_at_start_of_new_attempt(user: User):
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock(status_code=500)
        return MagicMock(status_code=200, json=lambda: {})

    with patch("frontend.pages.upload.requests.post", side_effect=side_effect):
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, None)
        await user.should_see("Server error. Please try again later.")
        await _click_upload_with_mocks(user, None)
        assert user.current_page_url.path == "/chatbot"


# ---------------------------------------------------------------------------
# 3.10 Helper Function: _format_file_size
# ---------------------------------------------------------------------------

def test_f01_zero_bytes():
    assert _format_file_size(0) == "0 Bytes"


def test_f02_one_byte_contains_byte():
    result = _format_file_size(1)
    assert "1" in result and "Byte" in result


def test_f03_500_bytes():
    assert _format_file_size(500) == "500 Bytes"


def test_f04_1024_bytes_is_1kb():
    assert _format_file_size(1024) == "1.0 KB"


def test_f05_1536_bytes_is_1_5kb():
    assert _format_file_size(1536) == "1.5 KB"


def test_f06_1mib_is_1mb():
    assert _format_file_size(1_048_576) == "1.0 MB"


def test_f07_2_5mib_is_2_5mb():
    assert _format_file_size(2_621_440) == "2.5 MB"


# ---------------------------------------------------------------------------
# 4. Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_it01_full_happy_path(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        assert not user.find("Upload").enabled
        _inject_file(user, "report.pdf", b"pdf-data")
        await user.should_see("report.pdf")
        assert user.find("Upload").enabled
        await _click_upload_with_mocks(user, mock_post)
        assert user.current_page_url.path == "/chatbot"


@pytest.mark.asyncio
async def test_it02_multi_file_remove_then_upload(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "a.txt", b"a")
        _inject_file(user, "b.pdf", b"b")
        _inject_file(user, "c.xlsx", b"c")
        await user.should_see("b.pdf")
        # Remove b.pdf (second close button)
        _click_element(_get_close_buttons(user)[1])
        await user.should_not_see("b.pdf")
        await _click_upload_with_mocks(user, mock_post)
        files = mock_post.call_args[1]["json"]["files"]
        assert len(files) == 2
        names = {f["filename"] for f in files}
        assert names == {"a.txt", "c.xlsx"}
        assert user.current_page_url.path == "/chatbot"


@pytest.mark.asyncio
async def test_it03_invalid_then_valid(user: User):
    await user.open("/upload")
    _inject_file(user, "image.jpg", b"\xFF\xD8")
    await user.should_see("Unsupported file type")
    await user.should_see("image.jpg")
    assert not user.find("Upload").enabled
    _inject_file(user, "report.pdf", b"%PDF")
    await user.should_not_see("Unsupported file type")
    await user.should_see("report.pdf")
    assert user.find("Upload").enabled


@pytest.mark.asyncio
async def test_it04_failure_then_successful_retry(user: User):
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock(status_code=500)
        return MagicMock(status_code=200, json=lambda: {})

    with patch("frontend.pages.upload.requests.post", side_effect=side_effect):
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, None)
        await user.should_see("Server error. Please try again later.")
        assert user.find("Upload").enabled
        assert user.current_page_url.path == "/upload"
        await _click_upload_with_mocks(user, None)
        assert user.current_page_url.path == "/chatbot"


@pytest.mark.asyncio
async def test_it05_remove_all_then_readd_and_upload(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "file1.txt", b"a")
        _inject_file(user, "file2.xls", b"b")
        assert user.find("Upload").enabled
        # Remove both (re-query each time since the list rebuilds after removal)
        for _ in range(2):
            _click_element(_get_close_buttons(user)[0])
        assert not user.find("Upload").enabled
        _inject_file(user, "file3.pdf", b"c")
        assert user.find("Upload").enabled
        await _click_upload_with_mocks(user, mock_post)
        files = mock_post.call_args[1]["json"]["files"]
        assert len(files) == 1
        assert files[0]["filename"] == "file3.pdf"


@pytest.mark.asyncio
async def test_it06_network_failure_then_recovery(user: User):
    import requests as req
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise req.exceptions.ConnectionError
        return MagicMock(status_code=200, json=lambda: {})

    with patch("frontend.pages.upload.requests.post", side_effect=side_effect):
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, None)
        await user.should_see("Could not reach the server.")
        assert user.find("Upload").enabled
        await _click_upload_with_mocks(user, None)
        assert user.current_page_url.path == "/chatbot"


@pytest.mark.asyncio
async def test_it07_session_expired_401_flow(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=401)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        with patch("nicegui.ui.run_javascript", new_callable=AsyncMock) as mock_js:
            mock_js.return_value = ""
            user.find("Upload").click()
            await asyncio.sleep(0.15)
        await user.should_see("Session expired. Please log in again.")
        assert user.find("Upload").enabled
        assert user.current_page_url.path == "/upload"


# ---------------------------------------------------------------------------
# 5. Security Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_st_f01_extension_check_bypasses_browser_accept(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        await user.open("/upload")
        _inject_file(user, "program.exe", b"MZ\x90\x00")
        await user.should_see("Unsupported file type")
        assert not user.find("Upload").enabled
        mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_st_f02_mime_spoofing_does_not_bypass_extension(user: User):
    await user.open("/upload")
    _inject_file(user, "malware.exe", b"MZ", mime="text/plain")
    await user.should_see("Unsupported file type")
    assert not user.find("Upload").enabled


@pytest.mark.asyncio
async def test_st_f03a_double_extension_exe_txt_accepted(user: User):
    await user.open("/upload")
    _inject_file(user, "virus.exe.txt", b"data")
    await user.should_not_see("Unsupported file type")
    await user.should_see("virus.exe.txt")


@pytest.mark.asyncio
async def test_st_f03b_double_extension_txt_exe_rejected(user: User):
    await user.open("/upload")
    _inject_file(user, "report.txt.exe", b"data")
    await user.should_see("Unsupported file type")


@pytest.mark.asyncio
async def test_st_f04_null_byte_in_filename_no_exception(user: User):
    await user.open("/upload")
    _inject_file(user, "file.txt\x00.exe", b"data")
    # Must not raise — result (accepted/rejected) depends on implementation


@pytest.mark.asyncio
async def test_st_p01_content_sent_as_base64_not_raw_bytes(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "data.pdf", b"\x00\xFF\xFE\xFD")
        await _click_upload_with_mocks(user, mock_post)
        content = mock_post.call_args[1]["json"]["files"][0]["content"]
        assert isinstance(content, str)
        base64.b64decode(content)  # valid base64, no serialization error


@pytest.mark.asyncio
async def test_st_p02_post_uses_json_kwarg_not_data(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        assert "json" in mock_post.call_args[1]
        assert "data" not in mock_post.call_args[1]


@pytest.mark.asyncio
async def test_st_p03_token_not_leaked_in_error_message(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=500)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        with patch("nicegui.ui.run_javascript", new_callable=AsyncMock) as mock_js:
            mock_js.return_value = "secret-jwt-token-abc123"
            user.find("Upload").click()
            await asyncio.sleep(0.15)
        await user.should_not_see("secret-jwt-token-abc123")


@pytest.mark.asyncio
async def test_st_p04_empty_token_sends_bearer_empty(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=401)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        with patch("nicegui.ui.run_javascript", new_callable=AsyncMock) as mock_js:
            mock_js.return_value = ""
            user.find("Upload").click()
            await asyncio.sleep(0.15)
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer "
        await user.should_see("Session expired")


@pytest.mark.asyncio
async def test_st_x01_detail_xss_rendered_as_text(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=400,
            json=lambda: {"detail": "<script>alert('xss')</script>"},
        )
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        await user.should_see("<script>alert('xss')</script>")


@pytest.mark.asyncio
async def test_st_x02_html_filename_rendered_as_text(user: User):
    await user.open("/upload")
    _inject_file(user, "<img src=x onerror=alert(1)>.txt", b"data")
    await user.should_see("<img src=x onerror=alert(1)>.txt")


@pytest.mark.asyncio
async def test_st_x03_script_tag_filename_rendered_as_text(user: User):
    await user.open("/upload")
    _inject_file(user, "<script>alert(1)</script>.pdf", b"data")
    await user.should_see("<script>alert(1)</script>.pdf")


@pytest.mark.asyncio
async def test_st_r01_api_url_not_overridden_by_file_content(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "data.txt", b"http://evil.example.com/steal")
        await _click_upload_with_mocks(user, mock_post)
        assert mock_post.call_args[0][0].startswith("http://test-backend:8000")


@pytest.mark.asyncio
async def test_st_m01_internal_exception_not_surfaced(user: User):
    with patch(
        "frontend.pages.upload.requests.post",
        side_effect=Exception("internal db error: secret_key=abc123"),
    ):
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, None)
        await user.should_see("An unexpected error occurred. Please try again.")
        await user.should_not_see("abc123")


@pytest.mark.asyncio
async def test_st_m02_file_size_shown_formatted_not_raw_bytes(user: User):
    await user.open("/upload")
    _inject_file(user, "large.pdf", b"x" * 5_242_880)
    await user.should_see("5.0 MB")
    await user.should_not_see("5242880")


# ---------------------------------------------------------------------------
# 6. Edge Cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ec_z01_empty_file_accepted_and_staged(user: User):
    await user.open("/upload")
    _inject_file(user, "empty.txt", b"")
    await user.should_not_see("Unsupported file type")
    await user.should_see("empty.txt")


@pytest.mark.asyncio
async def test_ec_z02_empty_file_shows_zero_bytes(user: User):
    await user.open("/upload")
    _inject_file(user, "empty.pdf", b"")
    await user.should_see("0 Bytes")


@pytest.mark.asyncio
async def test_ec_z03_empty_file_base64_is_empty_string(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "empty.xls", b"")
        await _click_upload_with_mocks(user, mock_post)
        assert mock_post.call_args[1]["json"]["files"][0]["content"] == ""


@pytest.mark.asyncio
async def test_ec_lg01_large_file_no_crash(user: User):
    await user.open("/upload")
    _inject_file(user, "big.pdf", b"x" * 10_485_760)
    await user.should_see("big.pdf")


@pytest.mark.asyncio
async def test_ec_lg02_large_file_size_shown_in_mb(user: User):
    await user.open("/upload")
    _inject_file(user, "big.pdf", b"x" * 10_485_760)
    await user.should_see("MB")


@pytest.mark.asyncio
async def test_ec_lg03_multiple_large_files_no_crash(user: User):
    await user.open("/upload")
    for i in range(5):
        _inject_file(user, f"file{i}.pdf", b"x" * 2_097_152)
    for i in range(5):
        await user.should_see(f"file{i}.pdf")


@pytest.mark.asyncio
async def test_ec_sf01_filename_with_spaces(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "my report 2024.pdf", b"data")
        await user.should_see("my report 2024.pdf")
        await _click_upload_with_mocks(user, mock_post)
        assert mock_post.call_args[1]["json"]["files"][0]["filename"] == "my report 2024.pdf"


@pytest.mark.asyncio
async def test_ec_sf02_unicode_filename(user: User):
    await user.open("/upload")
    _inject_file(user, "ファイル.txt", b"text")
    await user.should_see("ファイル.txt")


@pytest.mark.asyncio
async def test_ec_sf03_filename_with_brackets(user: User):
    await user.open("/upload")
    _inject_file(user, "report (final) [v2].xlsx", b"data")
    await user.should_see("report (final) [v2].xlsx")


@pytest.mark.asyncio
async def test_ec_sf04_very_long_filename(user: User):
    await user.open("/upload")
    name = "a" * 251 + ".txt"
    _inject_file(user, name, b"x")
    await user.should_see(name)


@pytest.mark.asyncio
async def test_ec_rp01_same_filename_twice_adds_two_entries(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "report.pdf", b"v1")
        _inject_file(user, "report.pdf", b"v2")
        await _click_upload_with_mocks(user, mock_post)
        files = mock_post.call_args[1]["json"]["files"]
        assert len(files) == 2
        assert all(f["filename"] == "report.pdf" for f in files)


@pytest.mark.asyncio
async def test_ec_rp02_mixed_valid_invalid_sequence(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/upload")
        _inject_file(user, "a.txt", b"a")
        _inject_file(user, "b.jpg", b"\xFF\xD8")
        _inject_file(user, "c.pdf", b"%PDF")
        _inject_file(user, "d.exe", b"MZ")
        await user.should_see("d.exe")  # last invalid in error msg
        await _click_upload_with_mocks(user, mock_post)
        files = mock_post.call_args[1]["json"]["files"]
        assert len(files) == 2
        names = {f["filename"] for f in files}
        assert names == {"a.txt", "c.pdf"}


@pytest.mark.asyncio
async def test_ec_nw01_4xx_non_json_body_shows_fallback(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        resp = MagicMock(status_code=400)
        resp.json.side_effect = ValueError("not json")
        mock_post.return_value = resp
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        await user.should_see("Upload failed. Please try again.")


@pytest.mark.asyncio
async def test_ec_nw02_5xx_non_json_body_shows_server_error(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        resp = MagicMock(status_code=500)
        resp.json.side_effect = ValueError("not json")
        mock_post.return_value = resp
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        await user.should_see("Server error. Please try again later.")


@pytest.mark.asyncio
async def test_ec_nw03_2xx_non_json_body_still_redirects(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        resp = MagicMock(status_code=200)
        resp.json.side_effect = ValueError("not json")
        mock_post.return_value = resp
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        assert user.current_page_url.path == "/chatbot"


@pytest.mark.asyncio
async def test_ec_si01_staged_files_do_not_persist_between_visits(user: User):
    await user.open("/upload")
    _inject_file(user, "old.txt", b"x")
    await user.should_see("old.txt")
    await user.open("/login")
    await user.open("/upload")
    await user.should_not_see("old.txt")
    assert not user.find("Upload").enabled


@pytest.mark.asyncio
async def test_ec_si02_validation_error_does_not_persist_between_visits(user: User):
    await user.open("/upload")
    _inject_file(user, "bad.jpg", b"\xFF\xD8")
    await user.should_see("Unsupported file type")
    await user.open("/login")
    await user.open("/upload")
    await user.should_not_see("Unsupported file type")


@pytest.mark.asyncio
async def test_ec_si03_upload_error_does_not_persist_between_visits(user: User):
    with patch("frontend.pages.upload.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=500)
        await user.open("/upload")
        _inject_file(user, "doc.txt", b"x")
        await _click_upload_with_mocks(user, mock_post)
        await user.should_see("Server error")
    await user.open("/login")
    await user.open("/upload")
    await user.should_not_see("Server error")
