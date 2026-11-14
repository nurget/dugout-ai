from datetime import date
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.agent_run import AgentRun
from app.models.conversation import Conversation, ConversationMessage
from app.models.conversation_owner import ConversationOwner
from app.models.recommendation_review import RecommendationReview
from app.models.user import User


@pytest.mark.asyncio
async def test_authenticated_coach_can_submit_and_update_recommendation_review(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    run_id = str(uuid4())
    conversation_id = str(uuid4())
    coach_id = str(uuid4())
    other_coach_id = str(uuid4())
    fan_id = str(uuid4())
    recommendation = {
        "type": "bullpen_comparison",
        "run_id": run_id,
        "team_code": "HT",
        "as_of_date": "2026-06-30",
        "comparison_status": "COMPARABLE",
        "coverage": {"status": "COMPLETE"},
        "candidates": [
            {"pitcher_id": "p1", "pitcher_name": "투수 A", "k_minus_bb_pct": 12.0},
            {"pitcher_id": "p2", "pitcher_name": "투수 B", "k_minus_bb_pct": 10.0},
        ],
        "withheld": [],
    }
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(settings, "jwt_secret_key", "review-test-secret-key-at-least-32-bytes")

    try:
        async with session_factory() as session:
            session.add_all([
                User(id=coach_id, username="review-coach", password_hash="x", team_code="KIA", role="COACH"),
                User(id=other_coach_id, username="other-review-coach", password_hash="x", team_code="KIA", role="COACH"),
                User(id=fan_id, username="review-fan", password_hash="x", team_code="KIA", role="FAN"),
                Conversation(id=conversation_id),
                AgentRun(
                    run_id=run_id,
                    conversation_id=conversation_id,
                    status="COMPLETED",
                    as_of_date=date(2026, 6, 30),
                    data_snapshot_ids={"appearances": "snapshot-1"},
                ),
                ConversationOwner(conversation_id=conversation_id, user_id=coach_id, team_code="KIA"),
                ConversationMessage(
                    conversation_id=conversation_id,
                    role="assistant",
                    content="비교 결과",
                    analysis_results=[recommendation],
                ),
            ])
            await session.commit()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            async def headers(user_id: str):
                token = create_access_token(user_id, settings.jwt_secret_key)
                return {"Authorization": f"Bearer {token}"}

            own_headers = await headers(coach_id)
            review_url = f"/api/agent/runs/{run_id}/recommendation-review"

            empty = await client.get(review_url, headers=own_headers)
            assert empty.status_code == 200
            assert empty.json() == {"review": None}

            invalid = await client.put(review_url, headers=own_headers, json={
                "outcome": "ACCEPTABLE_SET",
                "acceptable_candidate_ids": ["another-team-player"],
            })
            assert invalid.status_code == 422

            saved = await client.put(review_url, headers=own_headers, json={
                "outcome": "ACCEPTABLE_SET",
                "acceptable_candidate_ids": ["p1"],
            })
            assert saved.status_code == 200
            assert saved.json()["review"]["acceptable_candidate_ids"] == ["p1"]

            updated = await client.put(review_url, headers=own_headers, json={
                "outcome": "NONE_ACCEPTABLE",
                "acceptable_candidate_ids": [],
            })
            assert updated.status_code == 200
            assert updated.json()["review"]["outcome"] == "NONE_ACCEPTABLE"

            other_team_member = await client.get(
                review_url,
                headers=await headers(other_coach_id),
            )
            assert other_team_member.status_code == 404

            fan = await client.get(review_url, headers=await headers(fan_id))
            assert fan.status_code == 403

        async with session_factory() as session:
            reviews = list((await session.scalars(select(RecommendationReview))).all())
            assert len(reviews) == 1
            assert reviews[0].outcome == "NONE_ACCEPTABLE"
            assert reviews[0].acceptable_candidate_ids == []
            assert reviews[0].data_snapshot_ids == {"appearances": "snapshot-1"}
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
