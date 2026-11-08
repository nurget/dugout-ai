from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class AgentContext:
    """Agent 실행 시 인증된 사용자 범위를 전달하는 불변 문맥."""

    user_id: str
    team_code: str
    role: str
    as_of_date: date | None = None
    data_snapshot_ids: dict[str, str | None] | None = None


def build_conversation_input(
    message: str,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    return [
        *(history or []),
        {"role": "user", "content": message},
    ]
