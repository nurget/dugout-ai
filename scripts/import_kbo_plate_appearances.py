"""Parquet pitch-level data를 완료된 타석으로 바꾸어 저장한다."""
import argparse
import asyncio
from pathlib import Path

import pyarrow.parquet as pq
from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.models.kbo_plate_appearance import KboPlateAppearance
from app.services.data_catalog import record_import_batch
from app.services.kbo_matchups import parse_complete_plate_appearances


COLUMNS = [
    "game_pk", "game_date", "home_team", "away_team", "inning",
    "inning_topbot", "at_bat_number", "pitch_number", "batter", "pitcher",
    "batter_name", "pitcher_name", "stand", "events",
]


def read_plate_appearances(path: Path, season: int):
    parquet = pq.ParquetFile(path)
    missing = set(COLUMNS) - set(parquet.schema_arrow.names)
    if missing:
        raise ValueError(f"필수 컬럼 누락: {sorted(missing)}")

    def rows():
        for batch in parquet.iter_batches(batch_size=8192, columns=COLUMNS):
            yield from batch.to_pylist()

    return parse_complete_plate_appearances(rows(), season=season)


async def import_data(path: Path, *, season: int, source: str, apply: bool) -> None:
    rows, quality = read_plate_appearances(path, season)
    print(f"완료 타석: {len(rows):,}; 품질: {quality}")
    if not apply:
        print("검증만 진행했습니다. DB를 변경하려면 --apply를 사용하세요.")
        return
    if not source.strip():
        raise ValueError("적재에는 --source 출처 표기가 필요합니다.")

    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                delete(KboPlateAppearance).where(KboPlateAppearance.season == season)
            )
            batch = await record_import_batch(
                session,
                dataset="kbo_plate_appearances",
                source_name=source,
                season=season,
                record_count=len(rows),
                status="PARTIAL" if any(quality[key] for key in (
                    "incomplete", "mixed_pitchers", "invalid_identity", "invalid_team_side",
                )) else "SUCCESS",
                quality_summary={
                    **quality,
                    "source_file": path.name,
                    "date_min": min((row["game_date"].isoformat() for row in rows), default=None),
                    "date_max": max((row["game_date"].isoformat() for row in rows), default=None),
                    "validation": "PASSED",
                },
            )
            session.add_all([
                KboPlateAppearance(**row, source_batch_id=batch.id)
                for row in rows
            ])
            await session.commit()
        except Exception as error:
            await session.rollback()
            await record_import_batch(
                session,
                dataset="kbo_plate_appearances",
                source_name=source,
                season=season,
                record_count=0,
                status="FAILED",
                error_message=f"{type(error).__name__}: {error}",
                quality_summary={"source_file": path.name, "validation": "FAILED"},
            )
            await session.commit()
            raise
    print(f"저장 완료: {len(rows):,}건 (시즌 {season} 전체 교체)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--source", required=True, help="원천/라이선스 출처 표기")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(import_data(args.path, season=args.season, source=args.source, apply=args.apply))
