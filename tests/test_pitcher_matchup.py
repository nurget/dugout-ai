from app.services.pitcher_matchup import aggregate_pitcher_matchup


def make_pitch(
    game_pk: str,
    pa: int,
    pitch: int,
    pitcher: str,
    batter: str,
    event: str | None,
):
    return {
        "game_pk": game_pk,
        "at_bat_number": pa,
        "pitch_number": pitch,
        "pitcher": pitcher,
        "batter": batter,
        "events": event,
    }


def test_multiple_pitches_count_as_one_pa():
    rows = [
        make_pitch("G1", 1, 1, "P1", "B1", "strikeout"),
        make_pitch("G1", 1, 2, "P1", "B1", "strikeout"),
        make_pitch("G1", 1, 3, "P1", "B1", "strikeout"),
    ]

    result = aggregate_pitcher_matchup(rows, "P1", "B1")

    assert result["plate_appearances"] == 1
    assert result["strikeouts"] == 1


def test_hits_and_walks_are_counted():
    rows = [
        make_pitch("G1", 1, 1, "P1", "B1", "single"),
        make_pitch("G1", 2, 1, "P1", "B1", "walk"),
        make_pitch("G1", 3, 1, "P1", "B1", "home_run"),
    ]

    result = aggregate_pitcher_matchup(rows, "P1", "B1")

    assert result["plate_appearances"] == 3
    assert result["hits"] == 2
    assert result["walks"] == 1
    assert result["home_runs"] == 1


def test_mixed_pitcher_pa_is_excluded():
    rows = [
        make_pitch("G1", 1, 1, "P1", "B1", "walk"),
        make_pitch("G1", 1, 2, "P2", "B1", "walk"),
    ]

    result = aggregate_pitcher_matchup(rows, "P1", "B1")

    assert result["plate_appearances"] == 0
    assert result["excluded_mixed_pitcher_pa"] == 1


def test_incomplete_pa_is_excluded():
    rows = [
        make_pitch("G1", 1, 1, "P1", "B1", None),
    ]

    result = aggregate_pitcher_matchup(rows, "P1", "B1")

    assert result["plate_appearances"] == 0
    assert result["excluded_incomplete_pa"] == 1


def test_different_batter_is_not_counted():
    rows = [
        make_pitch("G1", 1, 1, "P1", "B2", "single"),
    ]

    result = aggregate_pitcher_matchup(rows, "P1", "B1")

    assert result["plate_appearances"] == 0
    assert result["hits"] == 0