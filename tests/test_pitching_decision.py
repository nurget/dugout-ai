
import pytest

from app.services.pitching_decision import evaluate_pitching_change


def test_late_close_game_with_high_pitch_count():
    result = evaluate_pitching_change(
        inning=7,
        outs=1,
        runners=[1, 2],
        score_diff=2,
        pitch_count=92,
    )

    assert result["status"] == "CONSIDER_CHANGE"
    assert result["risk_score"] == 6


def test_early_game_without_runners():
    result = evaluate_pitching_change(
        inning=3,
        outs=0,
        runners=[],
        score_diff=4,
        pitch_count=40,
    )

    assert result["status"] == "NO_STRONG_CHANGE_SIGNAL"
    assert result["risk_score"] == 0


def test_two_outs_reduces_score():
    result = evaluate_pitching_change(
        inning=7,
        outs=2,
        runners=[2],
        score_diff=1,
        pitch_count=90,
    )

    assert result["risk_score"] == 5
    assert result["status"] == "CONSIDER_CHANGE"


def test_pitch_count_over_100():
    result = evaluate_pitching_change(
        inning=5,
        outs=0,
        runners=[],
        score_diff=5,
        pitch_count=105,
    )

    assert result["risk_score"] == 3
    assert result["status"] == "MONITOR"


def test_invalid_outs():
    with pytest.raises(ValueError):
        evaluate_pitching_change(
            inning=7,
            outs=3,
            runners=[],
            score_diff=0,
            pitch_count=80,
        )


def test_duplicate_runners():
    with pytest.raises(ValueError):
        evaluate_pitching_change(
            inning=7,
            outs=1,
            runners=[1, 1],
            score_diff=0,
            pitch_count=80,
        )


def test_score_difference_uses_defending_team_perspective():
    result = evaluate_pitching_change(
        inning=8,
        outs=1,
        runners=[],
        score_diff=-1,
        pitch_count=60,
    )

    assert result["risk_score"] == 2
    assert result["status"] == "NO_STRONG_CHANGE_SIGNAL"