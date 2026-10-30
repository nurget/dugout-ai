from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import (
    Conversation,
    ConversationMessage,
    utc_now,
)


async def create_conversation(
    session: AsyncSession,
) -> Conversation:
    conversation = Conversation()
    session.add(conversation)

    # ID를 실제로 확보한 뒤 메시지의 FK에 사용해야 한다.
    await session.flush()
    return conversation


async def get_conversation(
    session: AsyncSession,
    conversation_id: str,
) -> Conversation | None:
    return await session.get(Conversation, conversation_id)


async def get_messages(
    session: AsyncSession,
    conversation_id: str,
) -> list[ConversationMessage]:
    result = await session.execute(
        select(ConversationMessage)
        .where(
            ConversationMessage.conversation_id == conversation_id
        )
        .order_by(
            ConversationMessage.created_at.asc(),
            ConversationMessage.id.asc(),
        )
    )
    return list(result.scalars().all())


async def get_recent_messages(
    session: AsyncSession,
    conversation_id: str,
    limit: int = 20,
) -> list[ConversationMessage]:
    result = await session.execute(
        select(ConversationMessage)
        .where(
            ConversationMessage.conversation_id == conversation_id
        )
        .order_by(
            ConversationMessage.created_at.desc(),
            ConversationMessage.id.desc(),
        )
        .limit(limit)
    )

    return list(reversed(result.scalars().all()))


async def save_exchange(
    session: AsyncSession,
    conversation: Conversation,
    user_message: str,
    assistant_message: str,
) -> None:
    # 응답이 끝났을 때 사용자 질문과 AI 답변을 함께 확정한다.
    session.add_all([
        ConversationMessage(
            conversation_id=conversation.id,
            role="user",
            content=user_message,
        ),
        ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=assistant_message,
        ),
    ])

    conversation.updated_at = utc_now()
    await session.commit()