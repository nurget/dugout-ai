"""Parquet에서 2026년 타석을 집계하여 로컬 분석 결과 CSV를 만든다."""
import argparse
import csv
from dataclasses import asdict
from pathlib import Path

from app.services.kbo_pbp import aggregate_pbp

COLUMNS = [
    "game_pk", "game_date", "at_bat_number", "pitch_number",
    "pitcher", "pitcher_name", "inning_topbot", "home_team",
    "away_team", "events",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--output", type=Path, default=Path("data/private/pbp_pitchers_2026.csv"))
    args = parser.parse_args()

    import pyarrow.parquet as pq
    if not args.path.is_file():
        parser.error(f"Parquet 파일이 없습니다: {args.path}")

    pf = pq.ParquetFile(args.path)
    missing = set(COLUMNS) - set(pf.schema_arrow.names)
    if missing:
        parser.error(f"필수 컬럼 누락: {sorted(missing)}")

    def rows():
        for batch in pf.iter_batches(batch_size=8192, columns=COLUMNS):
            yield from batch.to_pylist()

    lines, quality = aggregate_pbp(rows(), season=args.season)
    print("품질 점검:")
    for key, value in quality.items():
        print(f"  {key}: {value}")
    print(f"투수 수: {len(lines)}")
    if not lines:
        raise SystemExit("완료된 타석을 찾지 못했습니다. CSV를 생성하지 않습니다.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(asdict(lines[0])))
        writer.writeheader()
        writer.writerows(asdict(line) for line in lines)
    print(f"결과: {args.output}")
    print("주의: 미완료/투수 교체 타석은 제외됐으므로 공식 시즌 BF와 차이가 날 수 있습니다.")


if __name__ == "__main__":
    main()
