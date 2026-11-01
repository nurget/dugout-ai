
from app.services.bullpen_candidates import (
    BullpenCandidate,
    evaluate_bullpen_candidates,
)


def workload(status="NO_HIGH_LOAD_FLAG"):
    return {
        "workload_status": status,
        "pitches_last_3_days": 12,
        "data_warning": None,
    }


def candidate(
    pitcher_id,
    *,
    team_code="HT",
    role="RELIEVER",
    availability="AVAILABLE",
    batters_faced=200,
    k_minus_bb_pct=15.0,
    current_workload=None,
):
    return BullpenCandidate(
        pitcher_id=pitcher_id,
        pitcher_name=f"투수 {pitcher_id}",
        team_code=team_code,
        role=role,
        availability=availability,
        batters_faced=batters_faced,
        k_minus_bb_pct=k_minus_bb_pct,
        workload=(
            current_workload
            if current_workload is not None
            else workload()
        ),
    )


def test_larger_sample_takes_priority():
    result = evaluate_bullpen_candidates(
        [
            candidate(
                "P1",
                batters_faced=4,
                k_minus_bb_pct=25.0,
            ),
            candidate(
                "P2",
                batters_faced=500,
                k_minus_bb_pct=20.0,
            ),
        ],
        defending_team_code="HT",
    )

    assert result["recommended_candidates"][0]["pitcher_id"] == "P2"
    assert result["recommended_candidates"][1]["sample_level"] == "VERY_SMALL"


def test_unavailable_pitcher_is_excluded():
    result = evaluate_bullpen_candidates(
        [
            candidate("P1", availability="UNAVAILABLE"),
        ],
        defending_team_code="HT",
    )

    assert result["recommended_candidates"] == []
    assert len(result["excluded_candidates"]) == 1


def test_unknown_role_is_not_assumed_to_be_reliever():
    result = evaluate_bullpen_candidates(
        [
            candidate("P1", role="UNKNOWN"),
        ],
        defending_team_code="HT",
    )

    assert result["recommendation_status"] == (
        "INSUFFICIENT_VERIFIED_CANDIDATES"
    )


def test_high_workload_requires_additional_review():
    result = evaluate_bullpen_candidates(
        [
            candidate(
                "P1",
                current_workload=workload("REVIEW_REQUIRED"),
            ),
        ],
        defending_team_code="HT",
    )

    assert len(result["excluded_candidates"]) == 1


def test_other_team_is_excluded():
    result = evaluate_bullpen_candidates(
        [
            candidate("P1", team_code="LG"),
        ],
        defending_team_code="HT",
    )

    assert result["recommended_candidates"] == []


def test_unknown_workload_is_excluded():
    result = evaluate_bullpen_candidates(
        [
            candidate(
                "P1",
                current_workload=workload("UNKNOWN"),
            ),
        ],
        defending_team_code="HT",
    )

    assert result["recommended_candidates"] == []


def test_kbb_ranking_for_same_sample_group():
    result = evaluate_bullpen_candidates(
        [
            candidate("P1", k_minus_bb_pct=14.0),
            candidate("P2", k_minus_bb_pct=19.0),
        ],
        defending_team_code="HT",
    )

    assert [
        row["pitcher_id"]
        for row in result["recommended_candidates"]
    ] == ["P2", "P1"]
