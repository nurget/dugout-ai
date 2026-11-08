from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_import_batch import DataImportBatch


DATASETS = {
    "kbo_games": {
        "label": "KBO 경기 결과",
        "source_policy": "KBO 일정/결과 데이터. source_updated_at 미제공 시 최신성 미확인",
    },
    "kbo_pitcher_appearances": {
        "label": "경기별 투수 등판",
        "source_policy": "KBO 공식 박스스코어. 선수 ID 연결 상태는 별도 품질 항목",
    },
    "kbo_official_season_pitchers": {
        "label": "KBO 공식 시즌 투수 기록",
        "source_policy": "KBO 기록실 시즌 누적. 기준 시점 누적 기록으로 간주하지 않음",
    },
    "kbo_pbp_pitching": {
        "label": "Play-by-Play 투수 기록",
        "source_policy": "원본 PBP의 타석 집계. 시즌 범위와 집계 품질 요약을 함께 관리",
    },
}


async def record_import_batch(
    session: AsyncSession,
    *,
    dataset: str,
    source_name: str,
    record_count: int,
    quality_summary: dict[str, Any] | None = None,
    season: int | None = None,
    season_type: str | None = None,
    source_updated_at: datetime | None = None,
    status: str = "SUCCESS",
    error_message: str | None = None,
) -> DataImportBatch:
    if dataset not in DATASETS:
        raise ValueError(f"등록되지 않은 데이터셋입니다: {dataset}")
    if status not in {"SUCCESS", "PARTIAL", "FAILED"}:
        raise ValueError("지원하지 않는 적재 상태입니다.")
    if record_count < 0:
        raise ValueError("record_count는 0 이상이어야 합니다.")
    if source_updated_at is not None and source_updated_at.tzinfo is None:
        raise ValueError("source_updated_at은 timezone 정보가 필요합니다.")

    now = datetime.now(timezone.utc)
    if source_updated_at is not None and source_updated_at > now:
        raise ValueError("source_updated_at은 현재 시각보다 늦을 수 없습니다.")
    freshness = (
        "UNKNOWN"
        if source_updated_at is None
        else "FRESH"
        if (now - source_updated_at.astimezone(timezone.utc)).total_seconds() <= 86400
        else "STALE"
    )
    batch = DataImportBatch(
        dataset=dataset,
        source_name=source_name[:160],
        status=status,
        freshness=freshness,
        season=season,
        season_type=season_type,
        source_updated_at=source_updated_at,
        record_count=record_count,
        quality_summary=quality_summary or {},
        error_message=error_message,
    )
    session.add(batch)
    await session.flush()
    return batch


async def get_latest_dataset_statuses(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(DataImportBatch).order_by(
                DataImportBatch.dataset,
                DataImportBatch.imported_at.desc(),
                DataImportBatch.id.desc(),
            )
        )
    ).all()
    by_dataset = {}
    for row in rows:
        by_dataset.setdefault(row.dataset, row)

    results = []
    for dataset, metadata in DATASETS.items():
        row = by_dataset.get(dataset)
        if row is None:
            results.append({
                "dataset": dataset,
                **metadata,
                "snapshot_id": None,
                "status": "UNTRACKED",
                "freshness": "UNKNOWN",
                "season": None,
                "season_type": None,
                "source_name": None,
                "source_updated_at": None,
                "imported_at": None,
                "record_count": 0,
                "quality_summary": {},
                "note": "적재 이력이 없습니다. 원천 데이터 부재와 이력 미등록을 구분할 수 없습니다.",
            })
            continue

        results.append({
            "dataset": dataset,
            **metadata,
            "snapshot_id": row.id,
            "status": row.status,
            "freshness": row.freshness,
            "season": row.season,
            "season_type": row.season_type,
            "source_name": row.source_name,
            "source_updated_at": row.source_updated_at.isoformat() if row.source_updated_at else None,
            "imported_at": row.imported_at.isoformat() if row.imported_at else None,
            "record_count": row.record_count,
            "quality_summary": row.quality_summary,
        })
    return results
