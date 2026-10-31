from app.services.kbo_pbp import aggregate_pbp


def pitch(ab, no, event, pitcher="100", name="테스트투수"):
    return {"game_pk": "20260401KISS02026", "game_date": "2026-04-01",
            "at_bat_number": ab, "pitch_number": no,
            "pitcher": pitcher, "pitcher_name": name,
            "inning_topbot": "top", "home_team": "SS", "away_team": "KIA",
            "events": event}


def test_one_pa_multiple_pitches_is_one_bf():
    lines, q = aggregate_pbp([pitch(1, 1, "strikeout"), pitch(1, 2, "strikeout"),
                              pitch(1, 3, "strikeout"), pitch(2, 1, "walk")])
    assert len(lines) == 1
    assert lines[0].batters_faced == 2
    assert lines[0].strikeouts == 1
    assert lines[0].walks == 1
    assert lines[0].k_minus_bb_pct == 0.0
    assert q["counted_pa"] == 2


def test_incomplete_pa_is_excluded():
    lines, q = aggregate_pbp([pitch(1, 1, None), pitch(1, 2, None)])
    assert lines == []
    assert q["incomplete_pa"] == 1


def test_multiple_pitchers_in_same_pa_is_excluded():
    lines, q = aggregate_pbp([pitch(1, 1, "walk"), pitch(1, 2, "walk", pitcher="200")])
    assert lines == []
    assert q["mixed_pitcher_pa"] == 1


def test_duplicate_pitch_does_not_inflate_bf():
    row = pitch(1, 1, "strikeout")
    lines, q = aggregate_pbp([row, row])
    assert lines[0].batters_faced == 1
    assert q["duplicate_pitches"] == 1
