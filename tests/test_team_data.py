from unittest.mock import MagicMock, AsyncMock

import pytest

from app.services.team_data import (
    get_team_games,
    get_team_pitchers,
)


def create_mock_session():
    session = AsyncMock()

    result = MagicMock()
    result.scalars.return_value.all.return_value = []

    session.execute.return_value = result

    return session


@pytest.mark.asyncio
async def test_kia_games_query():
    session = create_mock_session()

    games = await get_team_games(
        session=session,
        team_code="KIA",
        season=2026,
    )

    assert games == []

    session.execute.assert_awaited_once()

    statement = session.execute.await_args.args[0]
    params = statement.compile().params

    assert "KIA" in params.values()
    assert 2026 in params.values()


@pytest.mark.asyncio
async def test_samsung_pitchers_query():
    session = create_mock_session()

    pitchers = await get_team_pitchers(
        session=session,
        team_code="SS",
        season=2026,
    )

    assert pitchers == []

    session.execute.assert_awaited_once()

    statement = session.execute.await_args.args[0]
    params = statement.compile().params

    assert "SS" in params.values()
    assert 2026 in params.values()


@pytest.mark.asyncio
async def test_different_teams_use_different_parameters():
    kia_session = create_mock_session()
    samsung_session = create_mock_session()

    await get_team_pitchers(
        kia_session,
        team_code="KIA",
        season=2026,
    )

    await get_team_pitchers(
        samsung_session,
        team_code="SS",
        season=2026,
    )

    kia_query = kia_session.execute.await_args.args[0]
    samsung_query = samsung_session.execute.await_args.args[0]

    kia_params = kia_query.compile().params
    samsung_params = samsung_query.compile().params

    # KIA 계정은 PBP 데이터셋의 HT 코드로 조회한다.
    assert "HT" in kia_params.values()
    assert "KIA" not in kia_params.values()

    # 삼성은 인증 코드와 데이터셋 코드가 동일하다.
    assert "SS" in samsung_params.values()

    assert kia_params != samsung_params


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("account_code", "pbp_code"),
    [
        ("KIA", "HT"),
        ("LOT", "LT"),
        ("SAM", "SS"),
        ("HAN", "HH"),
        ("KIW", "WO"),
        ("DOO", "OB"),
        ("KT", "KT"),
        ("LG", "LG"),
        ("NC", "NC"),
    ],
)
async def test_pitcher_query_uses_pbp_team_code(
    account_code: str,
    pbp_code: str,
):
    session = create_mock_session()

    await get_team_pitchers(session, team_code=account_code, season=2026)

    statement = session.execute.await_args.args[0]
    assert pbp_code in statement.compile().params.values()
