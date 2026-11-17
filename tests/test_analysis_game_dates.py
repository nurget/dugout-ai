from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import get_current_user
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db, get_session_factory
from app.main import app
from app.models.agent_run import AgentRun
from app.models.conversation import Conversation
from app.models.kbo import KboGame, KboTeam
from app.models.user import User
from app.routers import agent as agent_router
from app.services.analysis_game_dates import resolve_analysis_game_date


@pytest_asyncio.fixture
async def calendar_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'analysis-dates.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        session.add_all([KboTeam(code=code, name=code) for code in ("KIA", "HT", "LG", "SS")])
        user = User(id=str(uuid4()), username="dates-coach", password_hash="test", team_code="KIA", role="COACH", is_active=True)
        session.add(user)
        await session.flush()
        for suffix, days, home, away, status in (
            ("older", -4, "KIA", "LG", "Final"),
            ("latest", -3, "LG", "HT", "Final"),
            ("cancelled", -2, "KIA", "LG", "Cancelled"),
            ("postponed", -1, "LG", "KIA", "Postponed"),
            ("other-teams", 0, "LG", "SS", "Final"),
            ("future", 1, "KIA", "LG", "Final"),
        ):
            day = today + timedelta(days=days)
            session.add(KboGame(game_pk=f"date-{suffix}", season=day.year, season_type="REGULAR", season_phase="REGULAR",
                game_date=day, home_team_code=home, away_team_code=away, status=status, source_name="test"))
        await session.commit()

    async def override_db():
        async with factory() as session:
            yield session

    async def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_current_user] = override_user
    try:
        yield factory, today
    finally:
        for dependency in (get_db, get_session_factory, get_current_user):
            app.dependency_overrides.pop(dependency, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_invalid_analysis_dates_do_not_start_llm_or_create_run(calendar_db, monkeypatch):
    factory, today = calendar_db
    calls = []
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    def unexpected_openai(**kwargs):
        calls.append(kwargs)
        raise AssertionError("부적합한 경기일에 LLM을 생성하면 안 됩니다.")

    monkeypatch.setattr(agent_router, "AsyncOpenAI", unexpected_openai)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for days in (-8, -2, -1, 0, 1):
            response = await client.post("/api/agent/chat/stream", json={
                "message": "경기를 분석해줘", "as_of_date": (today + timedelta(days=days)).isoformat(),
            })
            assert response.status_code == 422, response.text
        assert calls == []
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Conversation)) == 0
        assert await session.scalar(select(func.count()).select_from(AgentRun)) == 0


@pytest.mark.asyncio
async def test_explicit_game_date_and_default_latest_game_keep_context_cutoff(calendar_db, monkeypatch):
    factory, today = calendar_db
    seen_dates = []
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    async def fake_stream(**kwargs):
        seen_dates.append(kwargs["context"].as_of_date)
        run_id = str(uuid4())
        yield "started", {"run_id": run_id}
        yield "answer_delta", {"delta": "분석 완료"}
        yield "completed", {"run_id": run_id, "llm_calls": 1, "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(agent_router, "AsyncOpenAI", FakeOpenAI)
    monkeypatch.setattr(agent_router, "stream_agent", fake_stream)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        latest = await client.post("/api/agent/chat/stream", json={"message": "최근 경기를 분석해줘"})
        assert latest.status_code == 200
        assert f'"as_of_date": "{today - timedelta(days=3)}"' in latest.text
        explicit_day = today - timedelta(days=4)
        explicit = await client.post("/api/agent/chat/stream", json={"message": "지난 경기를 분석해줘", "as_of_date": explicit_day.isoformat()})
        assert explicit.status_code == 200
        assert seen_dates == [today - timedelta(days=3), explicit_day]
    async with factory() as session:
        rows = list((await session.scalars(select(AgentRun))).all())
        assert {row.as_of_date for row in rows} == set(seen_dates)
        assert all(row.status == "COMPLETED" for row in rows)


@pytest.mark.asyncio
async def test_missing_team_schedule_has_no_default_analysis_date(calendar_db):
    factory, today = calendar_db
    async with factory() as session:
        await session.execute(delete(KboGame).where(KboGame.game_pk != "date-other-teams"))
        with pytest.raises(ValueError, match="분석할 경기 날짜가 없어요"):
            await resolve_analysis_game_date(session, team_code="KIA", requested_date=None, today=today)
