"""실제 FastAPI 서버, OpenAI API, PostgreSQL을 연결하는 선택적 E2E 테스트."""

import json
import os
from uuid import UUID

import httpx
import pytest


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("RUN_E2E") != "1",
        reason="실제 OpenAI API 호출이 필요하므로 RUN_E2E=1일 때만 실행",
    ),
]

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")


def stream_chat(client: httpx.Client, payload: dict) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = None
    data_lines: list[str] = []

    def append_event() -> None:
        nonlocal event_name, data_lines
        if event_name and data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
        event_name = None
        data_lines = []

    with client.stream("POST", "/api/agent/chat/stream", json=payload) as response:
        assert response.status_code == 200, response.read().decode("utf-8")
        assert "text/event-stream" in response.headers.get("content-type", "")

        for line in response.iter_lines():
            if not line:
                append_event()
            elif line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").lstrip())

        append_event()

    errors = [data for name, data in events if name == "error"]
    assert not errors, f"Agent 오류 이벤트: {errors}"
    assert any(name == "completed" for name, _ in events), events
    assert any(name == "answer_delta" for name, _ in events), events
    return events


def event_data(events: list[tuple[str, dict]], name: str) -> list[dict]:
    return [data for event_name, data in events if event_name == name]


def test_conversation_tools_streaming_and_persistence():
    with httpx.Client(base_url=BASE_URL, timeout=120.0) as client:
        health = client.get("/health")
        assert health.status_code == 200

        # 고정된 샘플 경기 정보를 활용해 조회 → 규칙 평가를 실제 실행한다.
        first = stream_chat(
            client,
            {
                "message": (
                    "경기 ID 1의 상태 ID 1을 조회해줘. "
                    "1루 주자는 없다고 가정하고 투구 수 기반 교체 검토를 "
                    "simulate_pitching_decision 도구로 수행해줘. "
                    "확인되지 않은 승률이나 기록은 만들지 마."
                )
            },
        )

        conversation_events = event_data(first, "conversation")
        assert conversation_events, "대화 ID 이벤트를 받지 못함"
        conversation_id = conversation_events[-1]["conversation_id"]
        UUID(conversation_id)

        first_tools = [item["tool"] for item in event_data(first, "tool_start")]
        assert "get_game_state" in first_tools, first_tools
        assert "simulate_pitching_decision" in first_tools, first_tools
        assert all(item["ok"] for item in event_data(first, "tool_result"))

        first_completed = event_data(first, "completed")[-1]
        first_run_id = first_completed.get("run_id")
        assert first_run_id, "완료 이벤트에 run_id가 없음"
        UUID(first_run_id)

        first_answer = "".join(item["delta"] for item in event_data(first, "answer_delta"))
        assert first_answer.strip()

        # 같은 ID로 후속 질문을 전송해 DB 문맥을 다시 사용하는지 검증한다.
        second = stream_chat(
            client,
            {
                "conversation_id": conversation_id,
                "message": (
                    "방금 분석한 상황에서 투구 수가 몇 구였지? "
                    "그 숫자와 교체 검토 결과를 간단히 다시 설명해줘."
                ),
            },
        )
        assert event_data(second, "conversation")[-1]["conversation_id"] == conversation_id
        second_answer = "".join(item["delta"] for item in event_data(second, "answer_delta"))
        assert second_answer.strip()

        messages_response = client.get(f"/api/agent/conversations/{conversation_id}/messages")
        assert messages_response.status_code == 200, messages_response.text
        messages = messages_response.json()["messages"]
        assert [item["role"] for item in messages] == ["user", "assistant", "user", "assistant"]
        assert messages[1]["content"] == first_answer
        assert messages[3]["content"] == second_answer

        run_response = client.get(f"/api/agent/runs/{first_run_id}")
        assert run_response.status_code == 200, run_response.text
        run = run_response.json()
        assert run["status"] == "COMPLETED"
        assert run["conversation_id"] == conversation_id
        assert run["llm_calls"] >= 1
        assert isinstance(run["duration_ms"], (int, float))
        assert len(run["tools"]) >= 2
        assert any(tool["name"] == "simulate_pitching_decision" for tool in run["tools"])

        print(f"\nconversation_id={conversation_id}")
        print(f"run_id={first_run_id}")
        print(f"tools={first_tools}")
        print(f"duration_ms={run['duration_ms']}, llm_calls={run['llm_calls']}")