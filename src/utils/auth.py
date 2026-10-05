import os
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from src.utils.exception import AppException


class AuthUtils:

    @staticmethod
    def hash_password(plain: str) -> str:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def validate_hash_password(plain: str, hashed: str) -> bool:
        return bcrypt.checkpw(plain.encode(), hashed.encode())

    @staticmethod
    def create_access_token(data: dict) -> str:
        secret = os.environ["JWT_SECRET"]
        algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
        expires_in = int(os.environ.get("JWT_EXPIRES_IN", "3600"))
        payload = {**data, "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in)}
        return jwt.encode(payload, secret, algorithm=algorithm)

    @staticmethod
    def decode_access_token(token: str) -> dict:
        secret = os.environ["JWT_SECRET"]
        algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
        from jose import JWTError, ExpiredSignatureError
        try:
            return jwt.decode(token, secret, algorithms=[algorithm])
        except ExpiredSignatureError:
            raise AppException("Invalid or expired token", status_code=401)
        except JWTError:
            raise AppException("Invalid or expired token", status_code=401)
