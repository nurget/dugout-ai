from typing import Any


def build_conversation_input(
    message: str,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    return [
        *(history or []),
        {"role": "user", "content": message},
    ]