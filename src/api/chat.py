import logging
from fastapi import APIRouter, Header
from src.schemas.chat import ChatRequest, ChatResponse
from src.services.chat import ChatService
from src.utils.auth import AuthUtils
from src.utils.exception import AppException

chat_router = APIRouter(prefix="/api", tags=["Chat"])
logger = logging.getLogger(__name__)

_service = ChatService()


def _get_current_user(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise AppException("Invalid or expired token", status_code=401)
    token = authorization.removeprefix("Bearer ")
    claims = AuthUtils.decode_access_token(token)
    username = claims.get("sub")
    if not username:
        raise AppException("Invalid or expired token", status_code=401)
    return username


@chat_router.post("/chat", response_model=ChatResponse, status_code=200)
async def chat(payload: ChatRequest, authorization: str = Header(default="")):
    username = _get_current_user(authorization)
    answer = _service.ask(payload.question, username)
    return ChatResponse(answer=answer)
