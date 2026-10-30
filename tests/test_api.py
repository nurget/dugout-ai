from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analysis_preview_success():
    payload = {
        "inning": 7,
        "outs": 1,
        "pitch_count": 95,
        "runner_on_first": True,
        "question": "투수를 교체해야 할까?",
    }

    response = client.post(
        "/api/analysis/preview",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["pitch_count"] == 95


def test_analysis_preview_invalid_outs():
    payload = {
        "inning": 7,
        "outs": 4,
        "pitch_count": 95,
        "question": "교체해야 할까?",
    }

    response = client.post(
        "/api/analysis/preview",
        json=payload,
    )

    assert response.status_code == 422