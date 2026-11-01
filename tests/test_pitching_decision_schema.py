import pytest
from pydantic import ValidationError

from app.schemas.pitching_decision import PitchingDecisionContext


def valid_context() -> dict:
    return {
        "defending_team_code": "KIA",
        "inning": 7,
        "inning_half": "TOP",
        "outs": 1,
        "runners": {
            "first": True,
            "second": True,
            "third": False,
        },
        "score_diff": 1,
        "current_pitch_count": 98,
        "next_batter_hand": "L",
    }


def test_valid_pitching_decision_context():
    context = PitchingDecisionContext.model_validate(
        valid_context()
    )

    assert context.inning == 7
    assert context.outs == 1
    assert context.runners.first is True
    assert context.runners.second is True
    assert context.score_diff == 1
    assert context.current_pitch_count == 98
    assert context.source == "USER_INPUT"


@pytest.mark.parametrize("outs", [-1, 3, 4])
def test_invalid_outs(outs):
    data = valid_context()
    data["outs"] = outs

    with pytest.raises(ValidationError):
        PitchingDecisionContext.model_validate(data)


def test_negative_pitch_count_rejected():
    data = valid_context()
    data["current_pitch_count"] = -1

    with pytest.raises(ValidationError):
        PitchingDecisionContext.model_validate(data)


def test_unknown_batter_hand_is_allowed():
    data = valid_context()
    data["next_batter_hand"] = None

    context = PitchingDecisionContext.model_validate(data)

    assert context.next_batter_hand is None


def test_invalid_data_source_rejected():
    data = valid_context()
    data["source"] = "LIVE"

    with pytest.raises(ValidationError):
        PitchingDecisionContext.model_validate(data)


def test_negative_score_diff_means_trailing():
    data = valid_context()
    data["score_diff"] = -2

    context = PitchingDecisionContext.model_validate(data)

    assert context.score_diff == -2