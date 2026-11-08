import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.data_import_batch import DataImportBatch
from app.models.kbo import KboGame, KboTeam
from app.services.kbo_import import InvalidKboDataset, import_games, normalize_dataset


def sample():
    return {"season": "2025", "games": [{
        "gamePk": "20250322NCHT0", "officialDate": "2025-03-22",
        "status": {"detailedState": "Final"},
        "teams": {
            "away": {"team": {"abbrev": "NC", "name": "NC Dinos"}, "score": 2},
            "home": {"team": {"abbrev": "KIA", "name": "KIA Tigers"}, "score": 9},
        },
    }]}


def test_parse_game():
    game = normalize_dataset(sample())[0]
    assert game.game_pk == "20250322NCHT0"
    assert game.home_code == "KIA"
    assert game.home_score == 9
    assert game.away_score == 2


def test_reject_duplicate_games():
    payload = sample()
    payload["games"].append(payload["games"][0])
    with pytest.raises(InvalidKboDataset, match="중복"):
        normalize_dataset(payload)


def test_reject_invalid_score():
    payload = sample()
    payload["games"][0]["teams"]["home"]["score"] = -1
    with pytest.raises(InvalidKboDataset):
        normalize_dataset(payload)

def test_parse_2026_array_dataset():
    payload = [{
        "gamePk": "20260328HTSK0",
        "officialDate": "2026-03-28",
        "status": {
            "detailedState": "Final"
        },
        "teams": {
            "away": {
                "team": {
                    "abbrev": "KIA",
                    "name": "KIA Tigers",
                },
                "score": 6,
            },
            "home": {
                "team": {
                    "abbrev": "SSG",
                    "name": "SSG Landers",
                },
                "score": 7,
            },
        },
    }]

    games = normalize_dataset(payload)

    assert len(games) == 1
    assert games[0].season == 2026
    assert games[0].game_pk == "20260328HTSK0"
    assert games[0].away_code == "KIA"
    assert games[0].home_code == "SSG"


def test_reject_mixed_seasons():
    payload = sample()
    payload["games"][0]["officialDate"] = "2026-03-28"

    with pytest.raises(InvalidKboDataset):
        normalize_dataset(payload)


@pytest.mark.asyncio
async def test_game_import_links_rows_to_its_batch():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [DataImportBatch.__table__, KboTeam.__table__, KboGame.__table__]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        rows = normalize_dataset(sample())
        await import_games(session, rows, source_name="fixture.json")
        await session.commit()

        game = await session.get(KboGame, "20250322NCHT0")
        batch = await session.get(DataImportBatch, game.source_batch_id)

        assert game.source_batch_id
        assert batch.dataset == "kbo_games"
        assert batch.record_count == 1
        assert batch.quality_summary["validation"] == "PASSED"
    await engine.dispose()
