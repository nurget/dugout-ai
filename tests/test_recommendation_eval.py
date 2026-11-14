import json
from pathlib import Path

import pytest

from app.evaluation.recommendation_eval import (
    evaluate_recommendation_dataset,
    load_recommendation_dataset,
    load_recommendation_fixtures,
)


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals/recommendation/v1.jsonl"
FIXTURES = ROOT / "evals/recommendation/fixtures/v1.json"


def test_recommendation_eval_measures_label_ranking_and_excludes_synthetic_from_real_metrics():
    cases = load_recommendation_dataset(DATASET)
    fixtures = load_recommendation_fixtures(FIXTURES)

    report = evaluate_recommendation_dataset(cases, fixtures)

    assert report["synthetic_count"] == 2
    assert report["approved_real_metrics"] == {
        "n": 0,
        "top1_acceptable_rate": None,
        "mean_reciprocal_rank": None,
        "mean_candidate_coverage": None,
    }
    top1, miss = report["results"]
    assert top1["ranked_candidate_ids"] == ["P2", "P1", "P3"]
    assert top1["top1_acceptable"] is True
    assert top1["reciprocal_rank"] == 1.0
    assert miss["top1_acceptable"] is False
    assert miss["reciprocal_rank"] == 0.5
    assert "승률" in report["interpretation"]


def test_real_recommendation_labels_require_review_and_snapshot_provenance(tmp_path):
    case = {
        "dataset_version": "1.0.0",
        "case_id": "real-review-case",
        "record_type": "HUMAN_REVIEWED_REAL",
        "label_status": "APPROVED",
        "fixture_ref": "fixture:private-real-case",
        "candidate_ids": ["P1", "P2"],
        "acceptable_candidate_ids": ["P1"],
    }
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(json.dumps(case), encoding="utf-8")

    with pytest.raises(ValueError, match="reviewer_id"):
        load_recommendation_dataset(dataset)
