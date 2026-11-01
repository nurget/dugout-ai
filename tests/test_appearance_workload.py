
from datetime import date

import pytest

from app.services.appearance_workload import (
    calculate_appearance_workloads,
)


def appearance(
    team,
    pitcher,
    game_date,
    pitches,
    game_pk,
):
    return {
        "team_code": team,
        "pitcher_name": pitcher,
        "game_date": game_date,
        "pitches": pitches,
        "game_pk": game_pk,
    }


def test_two_consecutive_appearances():
    rows = [
        appearance("HT", "투수A", "2026-03-28", 17, "G1"),
        appearance("HT", "투수A", "2026-03-29", 26, "G2"),
    ]

    result = calculate_appearance_workloads(
        rows,
        as_of_date=date(2026, 3, 30),
    )[0]

    assert result["consecutive_days"] == 2
    assert result["pitches_last_3_days"] == 43
    assert result["days_rest"] == 0
    assert result["workload_status"] == "REVIEW_REQUIRED"


def test_multiple_teams_are_independent():
    rows = [
        appearance("LG", "투수A", "2026-03-29", 15, "G1"),
        appearance("SS", "투수B", "2026-03-29", 20, "G2"),
    ]

    result = calculate_appearance_workloads(
        rows,
        as_of_date=date(2026, 3, 30),
    )

    assert len(result) == 2
    assert {row["team_code"] for row in result} == {"LG", "SS"}


def test_same_day_is_excluded():
    rows = [
        appearance("KT", "투수A", "2026-03-29", 10, "G1"),
        appearance("KT", "투수A", "2026-03-30", 90, "G2"),
    ]

    result = calculate_appearance_workloads(
        rows,
        as_of_date=date(2026, 3, 30),
    )[0]

    assert result["pitches_last_3_days"] == 10


def test_missing_pitch_count_returns_unknown():
    rows = [
        appearance("NC", "투수A", "2026-03-29", None, "G1"),
    ]

    result = calculate_appearance_workloads(
        rows,
        as_of_date=date(2026, 3, 30),
    )[0]

    assert result["workload_status"] == "UNKNOWN"
    assert result["data_completeness"] == "NOT_VERIFIED"


def test_duplicate_game_record_raises_error():
    row = appearance("OB", "투수A", "2026-03-29", 10, "G1")

    with pytest.raises(ValueError):
        calculate_appearance_workloads(
            [row, row],
            as_of_date=date(2026, 3, 30),
        )