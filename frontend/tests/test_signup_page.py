import os
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("API_URL", "http://test-backend:8000")

from nicegui.testing import User
import frontend.pages.signup  # noqa: F401


# ---------------------------------------------------------------------------
# 3.1 Rendering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_page_loads(user: User):
    await user.open("/signup")
    await user.should_see("Decision Intelligence")


@pytest.mark.asyncio
async def test_title_visible(user: User):
    await user.open("/signup")
    await user.should_see("Decision Intelligence")


@pytest.mark.asyncio
async def test_subtitle_visible(user: User):
    await user.open("/signup")
    await user.should_see("Create your account")


@pytest.mark.asyncio
async def test_username_input_rendered(user: User):
    await user.open("/signup")
    await user.should_see("Username")


@pytest.mark.asyncio
async def test_password_input_rendered(user: User):
    await user.open("/signup")
    await user.should_see("Password")


@pytest.mark.asyncio
async def test_submit_button_rendered(user: User):
    await user.open("/signup")
    await user.should_see("Sign Up")


@pytest.mark.asyncio
async def test_login_link_rendered(user: User):
    await user.open("/signup")
    await user.should_see("Already have an account?")
    await user.should_see("Log in")


@pytest.mark.asyncio
async def test_no_sidebar_or_header(user: User):
    await user.open("/signup")
    user.find("header").assert_not_found()


# ---------------------------------------------------------------------------
# 3.2 Button enable/disable state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_button_disabled_on_load(user: User):
    await user.open("/signup")
    assert user.find("Sign Up").props.get("disabled") is not None or \
           not user.find("Sign Up").enabled


@pytest.mark.asyncio
async def test_button_disabled_username_only(user: User):
    await user.open("/signup")
    user.find("Username").type("alice")
    assert not user.find("Sign Up").enabled


@pytest.mark.asyncio
async def test_button_disabled_password_only(user: User):
    await user.open("/signup")
    user.find("Password").type("secret123")
    assert not user.find("Sign Up").enabled


@pytest.mark.asyncio
async def test_button_enabled_both_fields(user: User):
    await user.open("/signup")
    user.find("Username").type("alice")
    user.find("Password").type("secret123")
    assert user.find("Sign Up").enabled


@pytest.mark.asyncio
async def test_button_disabled_after_clearing_username(user: User):
    await user.open("/signup")
    user.find("Username").type("alice")
    user.find("Password").type("secret123")
    user.find("Username").type("")
    assert not user.find("Sign Up").enabled


@pytest.mark.asyncio
async def test_button_disabled_after_clearing_password(user: User):
    await user.open("/signup")
    user.find("Username").type("alice")
    user.find("Password").type("secret123")
    user.find("Password").type("")
    assert not user.find("Sign Up").enabled


# ---------------------------------------------------------------------------
# 3.3 API call behavior
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_sent_to_correct_url(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://test-backend:8000/api/signup"


@pytest.mark.asyncio
async def test_post_payload_correct(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"] == {"username": "alice", "password": "secret123"}


@pytest.mark.asyncio
async def test_post_includes_content_type_header(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        headers = mock_post.call_args[1].get("headers", {})
        assert headers.get("Content-Type") == "application/json"


@pytest.mark.asyncio
async def test_api_url_from_env(user: User):
    with patch("frontend.pages.signup.API_URL", "http://custom-host:9000"):
        with patch("frontend.pages.signup.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
            await user.open("/signup")
            user.find("Username").type("alice")
            user.find("Password").type("secret123")
            user.find("Sign Up").click()
            url = mock_post.call_args[0][0]
            assert url.startswith("http://custom-host:9000")


# ---------------------------------------------------------------------------
# 3.4 Success handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_redirect_on_200(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        assert user.current_page_url.path == "/upload"


@pytest.mark.asyncio
async def test_redirect_on_201(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        assert user.current_page_url.path == "/upload"


# ---------------------------------------------------------------------------
# 3.5 Error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_error_400_shows_detail(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=400, json=lambda: {"detail": "Invalid input"})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        await user.should_see("Invalid input")


@pytest.mark.asyncio
async def test_error_409_shows_detail(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=409, json=lambda: {"detail": "Username already exists"})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        await user.should_see("Username already exists")


@pytest.mark.asyncio
async def test_error_422_shows_detail(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=422, json=lambda: {"detail": "Validation error"})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        await user.should_see("Validation error")


@pytest.mark.asyncio
async def test_error_422_no_detail_shows_fallback(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=422, json=lambda: {})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        await user.should_see("An error occurred.")


@pytest.mark.asyncio
async def test_error_500_shows_server_error(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=500)
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        await user.should_see("Server error. Please try again later.")


@pytest.mark.asyncio
async def test_network_error_shows_connection_message(user: User):
    import requests as req
    with patch("frontend.pages.signup.requests.post", side_effect=req.exceptions.ConnectionError):
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        await user.should_see("Could not reach the server")


@pytest.mark.asyncio
async def test_button_reenabled_after_4xx(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=409, json=lambda: {"detail": "exists"})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        assert user.find("Sign Up").enabled


@pytest.mark.asyncio
async def test_button_reenabled_after_5xx(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=500)
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        assert user.find("Sign Up").enabled


@pytest.mark.asyncio
async def test_button_reenabled_after_network_error(user: User):
    import requests as req
    with patch("frontend.pages.signup.requests.post", side_effect=req.exceptions.ConnectionError):
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        assert user.find("Sign Up").enabled


@pytest.mark.asyncio
async def test_page_remains_on_signup_after_error(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=409, json=lambda: {"detail": "exists"})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        assert user.current_page_url.path == "/signup"


# ---------------------------------------------------------------------------
# 3.6 Navigation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_link_navigates(user: User):
    await user.open("/signup")
    user.find("Log in").click()
    assert user.current_page_url.path == "/login"


# ---------------------------------------------------------------------------
# 4. Security tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_xss_in_username_not_executed(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=409,
            json=lambda: {"detail": "<script>alert('xss')</script>"},
        )
        await user.open("/signup")
        user.find("Username").type("<script>alert('xss')</script>")
        user.find("Password").type("pass")
        user.find("Sign Up").click()
        await user.should_see("<script>alert('xss')</script>")


@pytest.mark.asyncio
async def test_html_in_error_detail_not_rendered(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=409,
            json=lambda: {"detail": "<b>bold error</b><img src=x onerror=alert(1)>"},
        )
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("pass")
        user.find("Sign Up").click()
        await user.should_see("<b>bold error</b>")


@pytest.mark.asyncio
async def test_password_not_in_error_label(user: User):
    import requests as req
    with patch("frontend.pages.signup.requests.post", side_effect=Exception("connection failed")):
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("secret123")
        user.find("Sign Up").click()
        error_text = user.find("Could not reach the server").text
        assert "secret123" not in error_text


@pytest.mark.asyncio
async def test_api_url_not_overridden_by_input(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
        await user.open("/signup")
        user.find("Username").type("http://evil.example.com")
        user.find("Password").type("pass")
        user.find("Sign Up").click()
        url = mock_post.call_args[0][0]
        assert url.startswith("http://test-backend:8000")


@pytest.mark.asyncio
async def test_no_auth_header_sent(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("pass")
        user.find("Sign Up").click()
        headers = mock_post.call_args[1].get("headers", {})
        assert "Authorization" not in headers
        assert "Cookie" not in headers


@pytest.mark.asyncio
async def test_internal_exception_not_surfaced(user: User):
    with patch(
        "frontend.pages.signup.requests.post",
        side_effect=Exception("internal db error: password=hunter2 host=prod-db"),
    ):
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("pass")
        user.find("Sign Up").click()
        await user.should_see("Could not reach the server")
        user.find("hunter2").assert_not_found()


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whitespace_username_button_disabled(user: User):
    await user.open("/signup")
    user.find("Username").type("   ")
    user.find("Password").type("secret123")
    assert not user.find("Sign Up").enabled


@pytest.mark.asyncio
async def test_whitespace_password_button_disabled(user: User):
    await user.open("/signup")
    user.find("Username").type("alice")
    user.find("Password").type("   ")
    assert not user.find("Sign Up").enabled


@pytest.mark.asyncio
async def test_long_username_no_crash(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=400, json=lambda: {"detail": "too long"})
        await user.open("/signup")
        user.find("Username").type("a" * 500)
        user.find("Password").type("pass")
        user.find("Sign Up").click()
        await user.should_see("too long")


@pytest.mark.asyncio
async def test_long_password_no_crash(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=400, json=lambda: {"detail": "too long"})
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("p" * 500)
        user.find("Sign Up").click()
        await user.should_see("too long")


@pytest.mark.asyncio
async def test_special_chars_in_username_sent_correctly(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
        await user.open("/signup")
        user.find("Username").type("alice @#! 123")
        user.find("Password").type("pass")
        user.find("Sign Up").click()
        assert mock_post.call_args[1]["json"]["username"] == "alice @#! 123"


@pytest.mark.asyncio
async def test_unicode_username_sent_correctly(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
        await user.open("/signup")
        user.find("Username").type("用户名")
        user.find("Password").type("pass")
        user.find("Sign Up").click()
        assert mock_post.call_args[1]["json"]["username"] == "用户名"


@pytest.mark.asyncio
async def test_timeout_shows_connection_error(user: User):
    import requests as req
    with patch("frontend.pages.signup.requests.post", side_effect=req.exceptions.Timeout):
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("pass")
        user.find("Sign Up").click()
        await user.should_see("Could not reach the server")


@pytest.mark.asyncio
async def test_success_does_not_call_json(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        resp = MagicMock(status_code=200)
        resp.json.side_effect = ValueError("no body")
        mock_post.return_value = resp
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("pass")
        user.find("Sign Up").click()
        assert user.current_page_url.path == "/upload"


@pytest.mark.asyncio
async def test_4xx_non_json_body_shows_fallback(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        resp = MagicMock(status_code=400)
        resp.json.side_effect = ValueError("not json")
        mock_post.return_value = resp
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("pass")
        user.find("Sign Up").click()
        await user.should_see("An error occurred.")


@pytest.mark.asyncio
async def test_422_detail_as_list(user: User):
    with patch("frontend.pages.signup.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=422,
            json=lambda: {"detail": [{"loc": ["body", "username"], "msg": "field required"}]},
        )
        await user.open("/signup")
        user.find("Username").type("alice")
        user.find("Password").type("pass")
        user.find("Sign Up").click()
        await user.should_see("field required")


@pytest.mark.asyncio
async def test_api_url_default_when_not_set(user: User):
    original = frontend.pages.signup.API_URL
    try:
        frontend.pages.signup.API_URL = "http://localhost:8000"
        with patch("frontend.pages.signup.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
            await user.open("/signup")
            user.find("Username").type("alice")
            user.find("Password").type("pass")
            user.find("Sign Up").click()
            assert mock_post.call_args[0][0].startswith("http://localhost:8000")
    finally:
        frontend.pages.signup.API_URL = original
