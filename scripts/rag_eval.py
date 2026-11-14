"""Validate RAG evaluation cases or grade saved retrieval/answer traces."""

import argparse
import json
import os
from pathlib import Path
from typing import Any

from app.evaluation.rag_eval import grade_rag_traces, load_rag_dataset


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIR = (ROOT / "data/private").resolve()
DEFAULT_DATASET = ROOT / "evals/rag/v1.jsonl"


def _load_traces(path: Path) -> list[dict[str, Any]]:
    traces = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        trace = json.loads(line)
        if not isinstance(trace, dict):
            raise ValueError(f"{path}:{line_number}: trace는 JSON 객체여야 합니다.")
        traces.append(trace)
    return traces


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "grade"))
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--traces", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    try:
        cases = load_rag_dataset(args.dataset)
        if args.command == "validate":
            versions = sorted({case["dataset_version"] for case in cases})
            print(f"유효한 RAG 평가 데이터: {len(cases)}건; version={','.join(versions)}")
            print("모델 답변 검증은 grade 명령에 비식별화된 trace를 입력해 실행합니다.")
            return
        if args.traces is None:
            raise ValueError("grade 명령에는 --traces가 필요합니다.")
        trace_path = args.traces.resolve()
        if not trace_path.is_relative_to(PRIVATE_DIR):
            raise ValueError("RAG 답변 trace는 민감할 수 있으므로 data/private/ 아래에 둡니다.")
        report = grade_rag_traces(cases, _load_traces(trace_path))
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.report:
            report_path = args.report.resolve()
            if not report_path.is_relative_to(PRIVATE_DIR):
                raise ValueError("RAG 평가 보고서는 data/private/ 아래에만 저장합니다.")
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(rendered + "\n", encoding="utf-8")
            os.chmod(report_path, 0o600)
        print(rendered)
        if report["failed_checks"]:
            raise ValueError(f"RAG 평가 실패 항목: {report['failed_checks']}")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
