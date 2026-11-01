from datetime import date

from app.services.bullpen_workload import (
    aggregate_bullpen_workload,
)


def make_pitch(
    game_pk: str,
    game_date: str,
    pitch_number: int,
    pitcher: str = "P1",
):
    return {
        "game_pk": game_pk,
        "game_date": game_date,
        "at_bat_number": 1,
        "pitch_number": pitch_number,
        "pitcher": pitcher,
    }


def test_recent_workload_is_calculated():
    rows = [
        make_pitch("G1", "2026-07-16", 1),
        make_pitch("G2", "2026-07-18", 1),
        make_pitch("G2", "2026-07-18", 2),
        make_pitch("G3", "2026-07-19", 1),
    ]

    result = aggregate_bullpen_workload(
        rows,
        pitcher_id="P1",
        as_of_date=date(2026, 7, 20),
    )

    assert result["last_appearance"] == "2026-07-19"
    assert result["days_rest"] == 0
    assert result["appearances_last_3_days"] == 2
    assert result["pitches_last_3_days"] == 3
    assert result["consecutive_days"] == 2
    assert result["workload_status"] == "REVIEW_REQUIRED"


def test_duplicate_pitch_is_not_counted_twice():
    pitch = make_pitch("G1", "2026-07-19", 1)

    result = aggregate_bullpen_workload(
        [pitch, pitch],
        pitcher_id="P1",
        as_of_date=date(2026, 7, 20),
    )

    assert result["pitches_last_3_days"] == 1


def test_future_and_same_day_pitches_are_excluded():
    rows = [
        make_pitch("G1", "2026-07-19", 1),
        make_pitch("G2", "2026-07-20", 1),
        make_pitch("G3", "2026-07-21", 1),
    ]

    result = aggregate_bullpen_workload(
        rows,
        pitcher_id="P1",
        as_of_date=date(2026, 7, 20),
    )

    assert result["pitches_last_3_days"] == 1
    assert result["last_appearance"] == "2026-07-19"


def test_other_pitcher_is_excluded():
    rows = [
        make_pitch("G1", "2026-07-19", 1, pitcher="P2"),
    ]

    result = aggregate_bullpen_workload(
        rows,
        pitcher_id="P1",
        as_of_date=date(2026, 7, 20),
    )

    assert result["workload_status"] == "UNKNOWN"
    assert result["last_appearance"] is None


def test_high_pitch_count_requires_review():
    rows = [
        make_pitch("G1", "2026-07-19", number)
        for number in range(1, 42)
    ]

    result = aggregate_bullpen_workload(
        rows,
        pitcher_id="P1",
        as_of_date=date(2026, 7, 20),
    )

    assert result["pitches_last_3_days"] == 41
    assert result["workload_status"] == "REVIEW_REQUIRED"


def test_old_dataset_cannot_confirm_low_workload():
    rows = [
        make_pitch("G1", "2026-07-20", 1),
    ]

    result = aggregate_bullpen_workload(
        rows,
        pitcher_id="P1",
        as_of_date=date(2026, 9, 10),
        data_through=date(2026, 7, 26),
    )

    assert result["workload_status"] == "UNKNOWN"
    assert result["data_warning"] is not None


def test_rest_and_low_load_flag():
    rows = [
        make_pitch("G1", "2026-07-16", 1),
        make_pitch("G2", "2026-07-18", 1),
    ]

    result = aggregate_bullpen_workload(
        rows,
        pitcher_id="P1",
        as_of_date=date(2026, 7, 20),
        data_through=date(2026, 7, 26),
    )

    assert result["days_rest"] == 1
    assert result["consecutive_days"] == 0
    assert result["workload_status"] == "NO_HIGH_LOAD_FLAG"