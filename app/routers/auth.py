from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.core.config import settings
from app.core.security import (
    create_access_token,
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