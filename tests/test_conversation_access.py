from uuid import uuid4

import pytest
from fastapi import HTTPException

from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base
from app.models.user import User
from app.models.conversation import Conversation
from app.models.conversation_owner import ConversationOwner

from app.repositories.conversation_owner import (
    assign_conversation_owner,
    has_conversation_access,
    require_conversation_access,
)


@pytest.mark.asyncio
async def test_conversation_owner_access():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:"
    )

    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                Base.metadata.create_all,
                tables=[
                    User.__table__,
                    Conversation.__table__,
                    ConversationOwner.__table__,
                ],
            )

        session_factory = async_sessionmaker(
            engine,
            expire_on_commit=False,
        )

        kia_user_id = str(uuid4())
        samsung_user_id = str(uuid4())
        conversation_id = str(uuid4())

        async with session_factory() as session:
            session.add_all([
                User(
                    id=kia_user_id,
                    username="kia_test_coach",
                    password_hash="test-hash",
                    team_code="KIA",
                    role="COACH",
                ),
                User(
                    id=samsung_user_id,
                    username="samsung_test_coach",
                    password_hash="test-hash",
                    team_code="SS",
                    role="COACH",
                ),
                Conversation(id=conversation_id),
            ])

            await session.flush()

            await assign_conversation_owner(
                session=session,
                conversation_id=conversation_id,
                user_id=kia_user_id,
                team_code="KIA",
            )

            await session.commit()

        async with session_factory() as session:
            # 대화 생성자는 정상 접근 가능
            assert await has_conversation_access(
                session,
                conversation_id,
                kia_user_id,
                "KIA",
            )

            # 다른 구단 계정은 접근 불가
            assert not await has_conversation_access(
                session,
                conversation_id,
                samsung_user_id,
                "SS",
            )

            # 같은 구단이라는 이유만으로 접근을 허용하지 않음
            assert not await has_conversation_access(
                session,
                conversation_id,
                str(uuid4()),
                "KIA",
            )

            # 존재하지 않는 대화 역시 접근 불가
            assert not await has_conversation_access(
                session,
                str(uuid4()),
                kia_user_id,
                "KIA",
            )

            with pytest.raises(HTTPException) as exc:
                await require_conversation_access(
                    session,
                    conversation_id,
                    samsung_user_id,
                    "SS",
                )

            assert exc.value.status_code == 404

    finally:
        await engine.dispose()