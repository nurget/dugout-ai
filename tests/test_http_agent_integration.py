import json
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db, get_session_factory
from app.main import app
from app.routers import agent as agent_router


class FakeOpenAI:
    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def parse_sse(payload: str) -> list[tuple[str, dict]]:
    events = []
    for block in payload.strip().split("\n\n"):
        lines = block.splitlines()
        name = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        events.append((name, json.loads(data)))
    return events


@pytest.mark.asyncio
async def test_authenticated_sse_persists_messages_and_run(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "integration.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_db():
        async with session_factory() as session:
            yield session

    def override_session_factory():
        return session_factory

    run_id = str(uuid4())

    async def fake_stream_agent(**kwargs):
        yield "started", {"run_id": run_id, "message": "시작"}
        yield "tool_start", {"tool": "get_game_state", "round": 1}
        yield "tool_result", {
            "tool": "get_game_state",
            "ok": True,
            "error": None,
            "duration_ms": 1.5,
        }
        yield "answer_delta", {"delta": "검증된 최종 답변"}
        yield "completed", {
            "run_id": run_id,
            "duration_ms": 5.0,
            "llm_calls": 2,
            "input_tokens": 10,
            "output_tokens": 5,
            "tool_count": 1,
            "rounds": 2,
        }

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = override_session_factory
    monkeypatch.setattr(settings, "allow_public_registration", True)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(agent_router, "AsyncOpenAI", FakeOpenAI)
    monkeypatch.setattr(agent_router, "stream_agent", fake_stream_agent)

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            unauthorized_status = await client.get(
                "/api/teams/me/data-status"
            )
            assert unauthorized_status.status_code == 401

            register = await client.post("/api/auth/register", json={
                "username": "integration-coach",
                "password": "strong-password",
                "team_code": "KIA",
            })
            assert register.status_code == 201
            assert register.json()["role"] == "COACH"

            login = await client.post("/api/auth/login", json={
                "username": "integration-coach",
                "password": "strong-password",
            })
            assert login.status_code == 200
            headers = {
                "Authorization": f"Bearer {login.json()['access_token']}"
            }

            future_date = (
                datetime.now(ZoneInfo("Asia/Seoul")).date()
                + timedelta(days=1)
            )
            future_analysis = await client.post(
                "/api/agent/chat/stream",
                headers=headers,
                json={
                    "message": "미래 경기를 분석해줘.",
                    "as_of_date": future_date.isoformat(),
                },
            )
            assert future_analysis.status_code == 422

            data_status = await client.get(
                "/api/teams/me/data-status",
                headers=headers,
            )
            assert data_status.status_code == 200
            assert data_status.json()["scope"] == "TEAM_ACCOUNT_DATA_OPERATIONS"
            assert all(
                row["status"] == "UNTRACKED"
                for row in data_status.json()["data"]
            )

            as_of_pitchers = await client.get(
                "/api/teams/me/pitchers",
                headers=headers,
                params={"season": 2026, "as_of_date": "2026-11-07"},
            )
            assert as_of_pitchers.status_code == 200
            assert as_of_pitchers.json()["as_of_date"] == "2026-11-07"
            assert as_of_pitchers.json()["coverage"]["status"] == "NO_DATA"
            assert as_of_pitchers.json()["provenance"]["status"] == "UNKNOWN"

            response = await client.post(
                "/api/agent/chat/stream",
                headers=headers,
                json={
                    "message": "경기 상황을 분석해줘.",
                    "as_of_date": "2026-11-07",
                },
            )
            assert response.status_code == 200
            events = parse_sse(response.text)
            assert [name for name, _ in events] == [
                "conversation",
                "started",
                "tool_start",
                "tool_result",
                "answer_delta",
                "completed",
            ]

            conversation_id = events[0][1]["conversation_id"]
            messages = await client.get(
                f"/api/agent/conversations/{conversation_id}/messages",
                headers=headers,
            )
            assert messages.status_code == 200
            assert [
                item["content"] for item in messages.json()["messages"]
            ] == ["경기 상황을 분석해줘.", "검증된 최종 답변"]

            run = await client.get(
                f"/api/agent/runs/{run_id}",
                headers=headers,
            )
            assert run.status_code == 200
            assert run.json()["status"] == "COMPLETED"
            assert run.json()["as_of_date"] == "2026-11-07"
            assert run.json()["data_snapshot_ids"] == {
                "kbo_games": None,
                "kbo_pitcher_appearances": None,
                "kbo_official_season_pitchers": None,
                "kbo_pbp_pitching": None,
            }
            assert run.json()["tools"][0]["name"] == "get_game_state"
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_session_factory, None)
        await engine.dispose()
