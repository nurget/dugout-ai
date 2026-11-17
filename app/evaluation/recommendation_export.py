"""Build private, pending recommendation-evaluation candidates from coach reviews."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class RecommendationExport:
    cases: list[dict[str, Any]]
    fixtures: list[dict[str, Any]]
    audit: list[dict[str, Any]]
    summary: dict[str, int]


def _digest(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _reviewer_alias(user_id: str, salt: str) -> str:
    return "reviewer:" + hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()[:16]


def _fixture_input(review, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    team_code = str(review.team_code)
    return {
        "team_code": team_code,
        "season_pitchers": [{
            "pitcher_id": str(row["pitcher_id"]),
            "pitcher_name": str(row.get("pitcher_name") or row["pitcher_id"]),
            "team_code": team_code,
            "k_minus_bb_pct": row.get("k_minus_bb_pct"),
            "batters_faced": row.get("batters_faced"),
            "identity_status": row.get("identity_status"),
            "identity_source": row.get("identity_source"),
        } for row in candidates],
        "workloads": [{
            "pitcher_id": str(row["pitcher_id"]),
            "workload_status": row.get("workload_status"),
            "pitches_last_3_days": row.get("pitches_last_3_days"),
            "consecutive_days": row.get("consecutive_days"),
            "days_rest": row.get("days_rest"),
        } for row in candidates],
    }


def build_recommendation_export(
    reviews: Iterable[Any],
    *,
    reviewer_salt: str,
    label_protocol_version: str,
) -> RecommendationExport:
    if len(reviewer_salt) < 16:
        raise ValueError("검토자 비식별화 솔트는 16자 이상이어야 합니다.")
    if not label_protocol_version.strip():
        raise ValueError("라벨 프로토콜 버전이 필요합니다.")

    cases: list[dict[str, Any]] = []
    fixtures: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    counts = {"reviewed": 0, "exported_pending": 0, "skipped": 0}

    for review in reviews:
        counts["reviewed"] += 1
        snapshot = review.recommendation_snapshot if isinstance(review.recommendation_snapshot, dict) else {}
        candidates = snapshot.get("candidates")
        valid_candidates = isinstance(candidates, list) and all(isinstance(row, dict) for row in candidates)
        candidate_ids = [str(row.get("pitcher_id")) for row in candidates if row.get("pitcher_id")] if valid_candidates else []
        acceptable_ids = [str(value) for value in (review.acceptable_candidate_ids or [])]
        reasons = []
        if review.outcome != "ACCEPTABLE_SET":
            reasons.append(f"OUTCOME_{review.outcome}")
        if not valid_candidates or not candidates or len(candidate_ids) != len(candidates) or len(candidate_ids) != len(set(candidate_ids)):
            reasons.append("INVALID_CANDIDATE_SNAPSHOT")
        if not acceptable_ids:
            reasons.append("NO_ACCEPTABLE_LABEL")
        elif not set(acceptable_ids).issubset(candidate_ids):
            reasons.append("LABEL_OUTSIDE_CANDIDATES")
        if not review.data_snapshot_ids:
            reasons.append("MISSING_DATA_SNAPSHOT")

        review_alias = _reviewer_alias(str(review.reviewer_user_id), reviewer_salt)
        audit_row = {
            "review_id": str(review.review_id),
            "run_id": str(review.run_id),
            "reviewer_id": review_alias,
            "outcome": str(review.outcome),
            "status": "SKIPPED" if reasons else "EXPORTED_PENDING",
            "reasons": reasons,
            "reviewed_at": review.updated_at.isoformat(),
        }
        audit.append(audit_row)
        if reasons:
            counts["skipped"] += 1
            continue

        case_id = f"review:{review.review_id}"
        fixture_ref = f"fixture:{case_id}"
        snapshot_id = _digest(review.data_snapshot_ids)
        cases.append({
            "dataset_version": "1.0.0",
            "case_id": case_id,
            "record_type": "HUMAN_REVIEWED_REAL",
            "label_status": "PENDING",
            "fixture_ref": fixture_ref,
            "candidate_ids": candidate_ids,
            "acceptable_candidate_ids": acceptable_ids,
            "reviewer_id": review_alias,
            "team_code": str(review.team_code),
            "as_of_date": review.as_of_date.isoformat(),
            "data_snapshot_id": snapshot_id,
            "candidate_pool_source": "COACH_CONFIRMED_BULLPEN_COMPARISON",
            "label_protocol_version": label_protocol_version,
            "reviewed_at": review.updated_at.isoformat(),
            "notes": "코치 화면 검토에서 생성된 승인 전 후보 라벨입니다. 독립 검토 전 실제 성능 지표에 포함하지 않습니다.",
        })
        fixtures.append({
            "fixture_ref": fixture_ref,
            "record_type": "HUMAN_REVIEWED_REAL",
            "data_snapshot_id": snapshot_id,
            "data_snapshot_ids": review.data_snapshot_ids,
            "recommendation_snapshot_digest": _digest(snapshot),
            "recommendation_input": _fixture_input(review, candidates),
        })
        counts["exported_pending"] += 1

    return RecommendationExport(cases=cases, fixtures=fixtures, audit=audit, summary=counts)
