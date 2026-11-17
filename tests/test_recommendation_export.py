import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.evaluation.recommendation_eval import (
    evaluate_recommendation_dataset,
    load_recommendation_dataset,
    load_recommendation_fixtures,
)
from app.evaluation.recommendation_export import build_recommendation_export


def review(*, review_id: str, outcome: str = "ACCEPTABLE_SET", acceptable=None, snapshots=None):
    candidates = [
        {"pitcher_id": "P1", "pitcher_name": "투수 1", "batters_faced": 200,
         "k_minus_bb_pct": 12.0, "workload_status": "NO_HIGH_LOAD_FLAG",
         "pitches_last_3_days": 10, "consecutive_days": 0, "days_rest": 2},
        {"pitcher_id": "P2", "pitcher_name": "투수 2", "batters_faced": 180,
         "k_minus_bb_pct": 18.0, "workload_status": "NO_HIGH_LOAD_FLAG",
         "pitches_last_3_days": 5, "consecutive_days": 0, "days_rest": 3},
    ]
    return SimpleNamespace(
        review_id=review_id,
        run_id=f"run-{review_id}",
        reviewer_user_id="raw-user-uuid",
        team_code="HT",
        as_of_date=date(2026, 6, 30),
        outcome=outcome,
        acceptable_candidate_ids=["P2"] if acceptable is None else acceptable,
        recommendation_snapshot={"comparison_status": "COMPARABLE", "candidates": candidates},
        data_snapshot_ids={"kbo_pitching_appearances": "snapshot-1"} if snapshots is None else snapshots,
        updated_at=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
    )


def test_review_export_is_pending_anonymized_and_replayable(tmp_path):
    result = build_recommendation_export(
        [review(review_id="accepted")],
        reviewer_salt="test-reviewer-salt-long",
        label_protocol_version="coach-review-v1",
    )
    assert result.summary == {"reviewed": 1, "exported_pending": 1, "skipped": 0}
    case = result.cases[0]
    assert case["label_status"] == "PENDING"
    assert case["reviewer_id"].startswith("reviewer:")
    assert "raw-user-uuid" not in json.dumps(result.cases)
    assert case["data_snapshot_id"].startswith("sha256:")
    assert result.audit[0]["status"] == "EXPORTED_PENDING"

    dataset = tmp_path / "dataset.jsonl"
    fixtures = tmp_path / "fixtures.json"
    dataset.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    fixtures.write_text(json.dumps({"notice": "private pending label", "fixtures": result.fixtures}), encoding="utf-8")
    cases = load_recommendation_dataset(dataset)
    loaded_fixtures = load_recommendation_fixtures(fixtures)
    report = evaluate_recommendation_dataset(cases, loaded_fixtures)
    assert report["approved_real_metrics"]["n"] == 0
    assert report["results"][0]["ranked_candidate_ids"] == ["P2", "P1"]


def test_review_export_skips_non_labels_and_missing_provenance():
    result = build_recommendation_export(
        [
            review(review_id="none", outcome="NONE_ACCEPTABLE", acceptable=[]),
            review(review_id="missing", snapshots={}),
        ],
        reviewer_salt="test-reviewer-salt-long",
        label_protocol_version="coach-review-v1",
    )
    assert result.summary == {"reviewed": 2, "exported_pending": 0, "skipped": 2}
    assert result.cases == []
    assert "OUTCOME_NONE_ACCEPTABLE" in result.audit[0]["reasons"]
    assert "MISSING_DATA_SNAPSHOT" in result.audit[1]["reasons"]


def test_review_export_requires_explicit_privacy_and_protocol_inputs():
    try:
        build_recommendation_export([review(review_id="x")], reviewer_salt="short", label_protocol_version="v1")
    except ValueError as error:
        assert "16자" in str(error)
    else:
        raise AssertionError("short salt must fail")
