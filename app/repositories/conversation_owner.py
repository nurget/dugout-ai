from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.conversation_owner import ConversationOwner


async def assign_conversation_owner(
    session: AsyncSession,
    conversation_id: str,
    user_id: str,
    team_code: str,
) -> None:
    session.add(
        ConversationOwner(
            conversation_id=conversation_id,
            user_id=user_id,
            team_code=team_code,
        )
    )

    # 대화 생성과 소유권 연결을 같은 트랜잭션에서 처리한다.
    await session.flush()


async def has_conversation_access(
    session: AsyncSession,
    conversation_id: str,
    user_id: str,
    team_code: str,
) -> bool:
    statement = select(ConversationOwner.conversation_id).where(
        ConversationOwner.conversation_id == conversation_id,
        ConversationOwner.user_id == user_id,
        ConversationOwner.team_code == team_code,
    )

    result = await session.scalar(statement)
    return result is not None

async def require_conversation_access(
    session: AsyncSession,
    conversation_id: str,
    user_id: str,
    team_code: str,
) -> None:
    allowed = await has_conversation_access(
        session=session,
        conversation_id=conversation_id,
        user_id=user_id,
        team_code=team_code,
    )

    if not allowed:
        raise HTTPException(
            status_code=404,
            detail="대화를 찾을 수 없습니다.",
        )