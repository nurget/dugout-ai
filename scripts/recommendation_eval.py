"""Run the deterministic bullpen ranking evaluation dataset."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
import stat
from pathlib import Path

from app.evaluation.recommendation_eval import (
    evaluate_recommendation_dataset,
    load_recommendation_dataset,
    load_recommendation_fixtures,
)
from app.evaluation.recommendation_export import build_recommendation_export
from app.db.session import AsyncSessionLocal
from app.models.recommendation_review import RecommendationReview
from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evals/recommendation/v1.jsonl"
DEFAULT_FIXTURES = ROOT / "evals/recommendation/fixtures/v1.json"
PRIVATE_DIR = (ROOT / "data/private").resolve()


def _require_private_file(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(PRIVATE_DIR):
        raise ValueError("실제 추천 평가 데이터는 data/private/ 아래에만 둘 수 있습니다.")
    if resolved.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ValueError(f"실제 추천 평가 파일 권한은 0600이어야 합니다: {resolved}")
    return resolved


def _private_output_dir(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(PRIVATE_DIR):
        raise ValueError("추천 평가 내보내기 경로는 data/private/ 아래여야 합니다.")
    resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(resolved, 0o700)
    return resolved


def _write_private(path: Path, content: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise ValueError(f"기존 파일을 덮어쓰지 않습니다. --force가 필요합니다: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(content)
    temporary.replace(path)
    os.chmod(path, 0o600)


async def _export_reviews(args) -> None:
    salt = os.getenv("RECOMMENDATION_EVAL_REVIEWER_SALT", "")
    query = select(RecommendationReview).order_by(
        RecommendationReview.updated_at,
        RecommendationReview.review_id,
    )
    if args.team_code:
        query = query.where(RecommendationReview.team_code == args.team_code)
    async with AsyncSessionLocal() as session:
        reviews = list((await session.scalars(query)).all())
    export = build_recommendation_export(
        reviews,
        reviewer_salt=salt,
        label_protocol_version=args.label_protocol_version,
    )
    output_dir = _private_output_dir(args.output_dir)
    dataset = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in export.cases)
    fixtures = json.dumps({
        "notice": "PRIVATE HUMAN REVIEW CANDIDATES. PENDING labels are excluded from approved real metrics.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixtures": export.fixtures,
    }, ensure_ascii=False, indent=2) + "\n"
    audit = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in export.audit)
    _write_private(output_dir / "dataset.jsonl", dataset, force=args.force)
    _write_private(output_dir / "fixtures.json", fixtures, force=args.force)
    _write_private(output_dir / "audit.jsonl", audit, force=args.force)
    print(json.dumps({"output_dir": str(output_dir), **export.summary}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "run", "export-reviews"))
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output-dir", type=Path, default=PRIVATE_DIR / "recommendation-eval/latest")
    parser.add_argument("--team-code")
    parser.add_argument("--label-protocol-version", default="coach-review-v1")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        if args.command == "export-reviews":
            asyncio.run(_export_reviews(args))
            return
        cases = load_recommendation_dataset(args.dataset)
        fixtures = load_recommendation_fixtures(args.fixtures)
        missing = sorted({case["fixture_ref"] for case in cases} - fixtures.keys())
        if missing:
            raise ValueError(f"fixture 누락: {', '.join(missing)}")
        real_cases = any(case["record_type"] == "HUMAN_REVIEWED_REAL" for case in cases)
        if real_cases:
            _require_private_file(args.dataset)
            _require_private_file(args.fixtures)
        if args.command == "validate":
            print(
                f"유효한 추천 평가 케이스: {len(cases)}건; "
                f"synthetic={sum(case['record_type'] == 'SYNTHETIC' for case in cases)}건"
            )
            print("synthetic 성적은 실제 추천 정확도에 포함하지 않습니다.")
            return
        if real_cases:
            if args.report is None:
                raise ValueError("실제 라벨이 포함된 결과는 --report data/private/... 로 저장해야 합니다.")
        report = evaluate_recommendation_dataset(cases, fixtures)
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.report is not None:
            report_path = args.report.resolve()
            if not report_path.is_relative_to(PRIVATE_DIR):
                raise ValueError("추천 평가 보고서는 data/private/ 아래에만 저장합니다.")
            report_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                report_path,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(rendered)
        if real_cases:
            print(json.dumps({
                "approved_real_metrics": report["approved_real_metrics"],
                "case_count": report["result_count"],
            }, ensure_ascii=False, indent=2))
        else:
            print(rendered)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
