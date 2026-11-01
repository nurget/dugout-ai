import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.user import User
from app.routers.auth import RegisterRequest, register


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session

    await engine.dispose()


@pytest.mark.asyncio
async def test_public_registration_is_disabled_by_default(session, monkeypatch):
    monkeypatch.setattr(settings, "allow_public_registration", False)
    payload = RegisterRequest(
        username="coach01",
        password="strong-password",
        team_code="KIA",
    )

    with pytest.raises(HTTPException) as exc_info:
        await register(payload, session)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_public_registration_can_only_create_coach(session, monkeypatch):
    monkeypatch.setattr(settings, "allow_public_registration", True)
    payload = RegisterRequest(
        username="coach01",
        password="strong-password",
        team_code="KIA",
    )

    response = await register(payload, session)

    assert response["role"] == "COACH"
    user = await session.get(User, response["id"])
    assert user is not None
    assert user.role == "COACH"


def test_registration_rejects_client_selected_role():
    with pytest.raises(ValidationError):
        RegisterRequest(
            username="coach01",
            password="strong-password",
            team_code="KIA",
            role="MANAGER",
        )
