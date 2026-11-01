
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.team_bullpen import (
    get_team_bullpen_candidates,
    normalize_official_team_code,
)


def make_pitcher(
    pitcher_id="P1",
    team_code="HT",
    k_minus_bb_pct=18.5,
):
    return SimpleNamespace(
        pitcher_id=pitcher_id,
        pitcher_name="테스트 투수",
        team_code=team_code,
        batters_faced=250,
        k_minus_bb_pct=k_minus_bb_pct,
    )


@pytest.mark.asyncio
async def test_kia_team_code_is_normalized(monkeypatch):
    repository = AsyncMock(
        return_value=[make_pitcher()]
    )

    monkeypatch.setattr(
        "app.services.team_bullpen.get_team_official_pitchers",
        repository,
    )

    result = await get_team_bullpen_candidates(
        AsyncMock(),
        season=2026,
        team_code="KIA",
    )

    repository.assert_awaited_once()
    assert repository.await_args.kwargs["team_code"] == "HT"

    assert result["official_pitcher_count"] == 1
    assert result["team_code"] == "HT"


@pytest.mark.asyncio
async def test_unverified_pitcher_is_not_recommended(monkeypatch):
    monkeypatch.setattr(
        "app.services.team_bullpen.get_team_official_pitchers",
        AsyncMock(return_value=[make_pitcher()]),
    )

    result = await get_team_bullpen_candidates(
        AsyncMock(),
        season=2026,
        team_code="HT",
    )

    assert result["recommended_candidates"] == []
    assert len(result["excluded_candidates"]) == 1
    assert result["recommendation_status"] == (
        "INSUFFICIENT_VERIFIED_CANDIDATES"
    )


@pytest.mark.asyncio
async def test_verified_candidate_uses_official_stats(monkeypatch):
    monkeypatch.setattr(
        "app.services.team_bullpen.get_team_official_pitchers",
        AsyncMock(return_value=[make_pitcher()]),
    )

    result = await get_team_bullpen_candidates(
        AsyncMock(),
        season=2026,
        team_code="KIA",
        verified_roles={"P1": "RELIEVER"},
        verified_availability={"P1": "AVAILABLE"},
        workloads={
            "P1": {
                "workload_status": "NO_HIGH_LOAD_FLAG",
                "pitches_last_3_days": 8,
                "data_warning": None,
            },
        },
    )

    assert result["recommendation_status"] == "CANDIDATES_FOUND"

    recommended = result["recommended_candidates"][0]

    assert recommended["pitcher_id"] == "P1"
    assert recommended["k_minus_bb_pct"] == 18.5
    assert recommended["batters_faced"] == 250


@pytest.mark.asyncio
async def test_empty_team_records(monkeypatch):
    monkeypatch.setattr(
        "app.services.team_bullpen.get_team_official_pitchers",
        AsyncMock(return_value=[]),
    )

    result = await get_team_bullpen_candidates(
        AsyncMock(),
        season=2026,
        team_code="HT",
    )

    assert result["official_pitcher_count"] == 0
    assert result["recommended_candidates"] == []


def test_team_code_mapping():
    assert normalize_official_team_code("KIA") == "HT"
    assert normalize_official_team_code("HT") == "HT"
    assert normalize_official_team_code("LG") == "LG"