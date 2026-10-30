from app.agent.context import build_conversation_input


def test_new_conversation_contains_only_current_message():
    result = build_conversation_input(
        message="KIA 투수 후보를 알려줘."
    )

    assert result == [
        {
            "role": "user",
            "content": "KIA 투수 후보를 알려줘.",
        }
    ]


def test_followup_preserves_previous_messages():
    history = [
        {
            "role": "user",
            "content": "KIA 투수 후보를 알려줘.",
        },
        {
            "role": "assistant",
            "content": "샘플 불펜 B가 있습니다.",
        },
    ]

    result = build_conversation_input(
        message="그 투수는 등판 가능해?",
        history=history,
    )

    assert len(result) == 3

    assert result[0]["role"] == "user"
    assert result[1]["role"] == "assistant"

    assert result[2] == {
        "role": "user",
        "content": "그 투수는 등판 가능해?",
    }


def test_original_history_is_not_modified():
    history = [
        {"role": "user", "content": "첫 질문"}
    ]

    build_conversation_input(
        message="두 번째 질문",
        history=history,
    )

    assert len(history) == 1