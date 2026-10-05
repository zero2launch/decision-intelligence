import logging

import pymongo.errors

from src.repository.auth import AuthRepository
from src.schemas.auth import SignupRequest, SignupResponse, LoginRequest, LoginResponse
from src.utils.auth import AuthUtils
from src.utils.exception import AppException

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self):
        self._repo = AuthRepository()

    def signup(self, payload: SignupRequest) -> SignupResponse:
        try:
            existing = self._repo.find_by_username(payload.username)
        except pymongo.errors.PyMongoError as e:
            logger.error(f"DB error on find_by_username: {e}")
            raise AppException("Internal server error", status_code=500)

        if existing:
            raise AppException("Username already taken", status_code=409)

        hashed = AuthUtils.hash_password(payload.password)

        try:
            self._repo.insert_user({"username": payload.username, "password": hashed})
        except pymongo.errors.PyMongoError as e:
            logger.error(f"DB error on insert_user: {e}")
            raise AppException("Internal server error", status_code=500)

        token = AuthUtils.create_access_token({"sub": payload.username})
        return SignupResponse(token=token)

    def login(self, payload: LoginRequest) -> LoginResponse:
        try:
            user = self._repo.find_by_username(payload.username)
        except pymongo.errors.PyMongoError as e:
            logger.error(f"DB error on find_by_username: {e}")
            raise AppException("Internal server error", status_code=500)

        if not user or not AuthUtils.validate_hash_password(payload.password, user["password"]):
            raise AppException("Invalid username or password", status_code=401)

        token = AuthUtils.create_access_token({"sub": payload.username})
        return LoginResponse(token=token)
