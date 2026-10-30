from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db


client = TestClient(app)


async def fake_get_db():
    raise RuntimeError("DB 연결이 사용되면 안 됩니다.")
    yield


def test_player_id_validation():
    response = client.get("/api/players/not-a-number")

    assert response.status_code == 422


def test_game_id_validation():
    response = client.get("/api/games/not-a-number")

    assert response.status_code == 422