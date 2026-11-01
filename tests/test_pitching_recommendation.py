
from app.services.pitching_recommendation import recommend_bullpen


def season(pid, name, kbb, tbf):
    return {
        "pitcher_id": pid,
        "pitcher_name": name,
        "team_code": "KT",
        "k_minus_bb_pct": kbb,
        "batters_faced": tbf,
    }


def workload(pid, status, pitches):
    return {
        "pitcher_id": pid,
        "workload_status": status,
        "pitches_last_3_days": pitches,
        "consecutive_days": 0,
        "days_rest": 1,
    }


def test_prefers_lower_workload_when_candidates_are_verified():
    result = recommend_bullpen(
        team_code="KT",
        verified_candidate_ids=["100", "200"],
        season_pitchers=[
            season("100", "투수A", 18.5, 200),
            season("200", "투수B", 15.0, 200),
        ],
        workloads=[
            workload("100", "REVIEW_REQUIRED", 48),
            workload("200", "NO_HIGH_LOAD_FLAG", 15),
        ],
    )

    assert result["ranking"][0]["pitcher_id"] == "200"
    assert result["ranking"][1]["pitcher_id"] == "100"


def test_does_not_guess_missing_identity():
    result = recommend_bullpen(
        team_code="KT",
        verified_candidate_ids=["100"],
        season_pitchers=[
            season("100", "동명이인", 20.0, 200),
        ],
        workloads=[
            workload(None, "AMBIGUOUS_IDENTITY", None),
        ],
    )

    assert result["ranking"] == []
    assert len(result["withheld"]) == 1


def test_does_not_include_unverified_candidates():
    result = recommend_bullpen(
        team_code="KT",
        verified_candidate_ids=["100"],
        season_pitchers=[
            season("100", "투수A", 18.0, 200),
            season("200", "투수B", 25.0, 200),
        ],
        workloads=[
            workload("100", "NO_HIGH_LOAD_FLAG", 10),
            workload("200", "NO_HIGH_LOAD_FLAG", 5),
        ],
    )

    assert len(result["ranking"]) == 1
    assert result["ranking"][0]["pitcher_id"] == "100"


def test_excludes_unknown_workload():
    result = recommend_bullpen(
        team_code="KT",
        verified_candidate_ids=["100"],
        season_pitchers=[
            season("100", "투수A", 18.0, 200),
        ],
        workloads=[
            workload("100", "UNKNOWN", None),
        ],
    )

    assert result["ranking"] == []
    assert len(result["withheld"]) == 1