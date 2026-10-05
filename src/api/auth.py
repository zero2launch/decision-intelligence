import logging

from fastapi import APIRouter

from src.schemas.auth import SignupRequest, SignupResponse, LoginRequest, LoginResponse
from src.services.auth import AuthService

auth_router = APIRouter(prefix="/api", tags=["Auth"])
logger = logging.getLogger(__name__)

_service = AuthService()


@auth_router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(payload: SignupRequest):
    return _service.signup(payload)


@auth_router.post("/login", response_model=LoginResponse, status_code=200)
async def login(payload: LoginRequest):
    return _service.login(payload)
