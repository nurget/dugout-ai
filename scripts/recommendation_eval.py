"""Run the deterministic bullpen ranking evaluation dataset."""

import argparse
import json
import os
import stat
from pathlib import Path

from app.evaluation.recommendation_eval import (
    evaluate_recommendation_dataset,
    load_recommendation_dataset,
    load_recommendation_fixtures,
)


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "run"))
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    try:
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
