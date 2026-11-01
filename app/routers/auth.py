from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User


router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)
    team_code: Literal["KIA", "SS", "LG", "KT", "SSG", "NC", "OB", "LT", "HH", "WO"]


@router.post("/register", status_code=201)
async def register(payload: RegisterRequest, session: Annotated[AsyncSession, Depends(get_db)]):
    if not settings.allow_public_registration:
        raise HTTPException(
            status_code=403,
            detail="공개 회원가입이 비활성화되어 있습니다.",
        )
    existing = await session.scalar(select(User).where(User.username == payload.username))
    if existing is not None:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        team_code=payload.team_code,
        role="COACH",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return {"id": user.id, "username": user.username, "team_code": user.team_code, "role": user.role}


@router.post("/login")
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    result = await session.execute(
        select(User).where(
            User.username == payload.username
        )
    )
    user = result.scalar_one_or_none()

    if (
        user is None
        or not user.is_active
        or not verify_password(
            payload.password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    token = create_access_token(
        user_id=user.id,
        secret_key=settings.jwt_secret_key,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600,
    }


@router.get("/me")
async def get_me(current_user: CurrentUser):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "team_code": current_user.team_code,
        "role": current_user.role,
    }
