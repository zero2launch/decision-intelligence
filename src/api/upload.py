import logging

from fastapi import APIRouter, Header

from src.schemas.upload import UploadRequest, UploadResponse
from src.services.upload import UploadService
from src.utils.auth import AuthUtils
from src.utils.exception import AppException

upload_router = APIRouter(prefix="/api", tags=["Upload"])
logger = logging.getLogger(__name__)

_service = UploadService()


def _get_current_user(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise AppException("Invalid or expired token", status_code=401)
    token = authorization.removeprefix("Bearer ")
    claims = AuthUtils.decode_access_token(token)
    username = claims.get("sub")
    if not username:
        raise AppException("Invalid or expired token", status_code=401)
    return username


@upload_router.post("/upload", response_model=UploadResponse, status_code=200)
async def upload_files(payload: UploadRequest, authorization: str = Header(default="")):
    username = _get_current_user(authorization)
    return _service.process_upload(payload, username)
