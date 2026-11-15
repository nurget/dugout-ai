from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.routers import private_knowledge


@pytest.mark.asyncio
async def test_private_rulebook_upload_requires_auth_and_uses_authenticated_owner(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "private-rulebook.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    first_user_id = str(uuid4())
    second_user_id = str(uuid4())
    secret = "private-rulebook-test-secret-key-32-bytes"
    monkeypatch.setattr(settings, "jwt_secret_key", secret)

    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)
    async with session_factory() as session:
        session.add_all([
            User(
                id=first_user_id,
                username="rulebook-owner-1",
                password_hash="test-hash",
                team_code="KIA",
                role="COACH",
                is_active=True,
            ),
            User(
                id=second_user_id,
                username="rulebook-owner-2",
                password_hash="test-hash",
                team_code="LG",
                role="COACH",
                is_active=True,
            ),
        ])
        await session.commit()

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    calls = []
    stored_owners = set()

    def fake_store(*, owner_user_id, pdf_bytes, replace):
        was_replaced = owner_user_id in stored_owners and replace
        stored_owners.add(owner_user_id)
        calls.append({
            "owner_user_id": owner_user_id,
            "pdf_bytes": pdf_bytes,
            "replace": replace,
        })
        return {
            "pdf_pages": 220,
            "nonempty_pages": 208,
            "blank_pages": 12,
            "chunks": 213,
            "sha256": "a" * 64,
            "replaced": was_replaced,
            "unchanged": False,
        }

    monkeypatch.setattr(private_knowledge, "store_private_rulebook", fake_store)
    monkeypatch.setattr(private_knowledge, "MAX_PRIVATE_RULEBOOK_BYTES", 32)
    first_token = create_access_token(first_user_id, secret)
    second_token = create_access_token(second_user_id, secret)
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            unauthorized = await client.post(
                "/api/agent/knowledge/private-rulebook",
                content=b"%PDF-test",
                headers={"Content-Type": "application/pdf"},
            )
            assert unauthorized.status_code == 401

            owner_upload = await client.post(
                "/api/agent/knowledge/private-rulebook",
                content=b"%PDF-test",
                headers={
                    "Authorization": f"Bearer {first_token}",
                    "Content-Type": "application/pdf",
                },
            )
            assert owner_upload.status_code == 201
            assert owner_upload.json()["blank_pages"] == 12
            assert calls[-1]["owner_user_id"] == first_user_id
            assert calls[-1]["pdf_bytes"] == b"%PDF-test"

            second_owner_upload = await client.post(
                "/api/agent/knowledge/private-rulebook",
                content=b"%PDF-new-version",
                headers={
                    "Authorization": f"Bearer {second_token}",
                    "Content-Type": "application/pdf",
                },
            )
            assert second_owner_upload.status_code == 201
            assert calls[-1]["owner_user_id"] == second_user_id

            owner_replacement = await client.post(
                "/api/agent/knowledge/private-rulebook?replace=true",
                content=b"%PDF-replacement",
                headers={
                    "Authorization": f"Bearer {first_token}",
                    "Content-Type": "application/pdf",
                },
            )
            assert owner_replacement.status_code == 200
            assert calls[-1]["owner_user_id"] == first_user_id
            assert calls[-1]["replace"] is True

            wrong_type = await client.post(
                "/api/agent/knowledge/private-rulebook",
                content=b"not pdf",
                headers={
                    "Authorization": f"Bearer {first_token}",
                    "Content-Type": "text/plain",
                },
            )
            assert wrong_type.status_code == 415

            oversized = await client.post(
                "/api/agent/knowledge/private-rulebook",
                content=b"%PDF-" + b"x" * 40,
                headers={
                    "Authorization": f"Bearer {first_token}",
                    "Content-Type": "application/pdf",
                },
            )
            assert oversized.status_code == 413
            assert len(calls) == 3
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
