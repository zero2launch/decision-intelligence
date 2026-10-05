import pymongo.errors
import pytest
from unittest.mock import MagicMock, patch

from src.schemas.auth import SignupRequest
from src.services.auth import AuthService
from src.utils.exception import AppException


@pytest.fixture()
def service():
    svc = AuthService.__new__(AuthService)
    svc._repo = MagicMock()
    return svc


def test_signup_success(service):
    service._repo.find_by_username.return_value = None
    service._repo.insert_user.return_value = "fake_object_id"

    with patch("src.services.auth.AuthUtils.create_access_token", return_value="mocked.jwt.token"):
        response = service.signup(SignupRequest(username="alice", password="securepass1"))

    assert response.token == "mocked.jwt.token"
    service._repo.find_by_username.assert_called_once_with("alice")
    service._repo.insert_user.assert_called_once()


def test_signup_username_taken(service):
    service._repo.find_by_username.return_value = {"username": "alice", "password": "hashed"}

    with pytest.raises(AppException) as exc_info:
        service.signup(SignupRequest(username="alice", password="securepass1"))

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == "Username already taken"


def test_signup_db_error_on_insert(service):
    service._repo.find_by_username.return_value = None
    service._repo.insert_user.side_effect = pymongo.errors.PyMongoError("connection failed")

    with pytest.raises(AppException) as exc_info:
        service.signup(SignupRequest(username="alice", password="securepass1"))

    assert exc_info.value.status_code == 500
    assert exc_info.value.message == "Internal server error"
