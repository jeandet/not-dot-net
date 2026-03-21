from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from not_dot_net.backend.db import get_user_db
from not_dot_net.backend.users import get_user_manager, get_jwt_strategy
from not_dot_net.backend.schemas import UserCreate

router = APIRouter(tags=["auth"])


class AuthRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str


@router.post("/auth/local", response_model=TokenResponse)
async def local_login(
    credentials: AuthRequest,
    user_db=Depends(get_user_db),
):
    user = await user_db.get_by_email(credentials.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    hashed = getattr(user, "hashed_password", None)
    if not hashed:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    if not pwd_context.verify(credentials.password, hashed):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    strategy = get_jwt_strategy()
    token = await strategy.write_token(user)
    return TokenResponse(access_token=token)


@router.post("/auth/register", response_model=TokenResponse)
async def local_register(
    credentials: AuthRequest,
    user_manager=Depends(get_user_manager),
):
    user_create = UserCreate(email=credentials.email, password=credentials.password)
    try:
        user = await user_manager.create(user_create)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    strategy = get_jwt_strategy()
    token = await strategy.write_token(user)
    return TokenResponse(access_token=token)
