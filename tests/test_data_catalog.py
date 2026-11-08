from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.data_import_batch import DataImportBatch
from app.services.data_catalog import (
    get_latest_dataset_statuses,
    record_import_batch,
)


@pytest.mark.asyncio
async def test_import_batch_records_unknown_source_freshness():
    session = AsyncMock()
    session.add = MagicMock()

    batch = await record_import_batch(
        session,
        dataset="kbo_games",
        source_name="games.json",
        season=2026,
        record_count=720,
        quality_summary={"validation": "PASSED"},
    )

    assert batch.status == "SUCCESS"
    assert batch.freshness == "UNKNOWN"
    assert batch.record_count == 720
    session.add.assert_called_once_with(batch)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_batch_marks_old_source_timestamp_stale():
    session = AsyncMock()
    session.add = MagicMock()

    batch = await record_import_batch(
        session,
        dataset="kbo_games",
        source_name="KBO",
        record_count=10,
        source_updated_at=datetime.now(timezone.utc) - timedelta(days=2),
    )

    assert batch.freshness == "STALE"


@pytest.mark.asyncio
async def test_dataset_status_returns_untracked_for_unregistered_sources():
    session = AsyncMock()
    result_proxy = MagicMock()
    result_proxy.all.return_value = []
    session.scalars = AsyncMock(return_value=result_proxy)

    result = await get_latest_dataset_statuses(session)

    assert {row["status"] for row in result} == {"UNTRACKED"}
    assert {row["freshness"] for row in result} == {"UNKNOWN"}
    assert all(row["snapshot_id"] is None for row in result)


@pytest.mark.asyncio
async def test_dataset_status_uses_latest_batch_per_dataset():
    older = DataImportBatch(
        id="older",
        dataset="kbo_games",
        source_name="old.json",
        status="SUCCESS",
        freshness="STALE",
        imported_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        record_count=5,
        quality_summary={},
    )
    newer = DataImportBatch(
        id="newer",
        dataset="kbo_games",
        source_name="new.json",
        status="PARTIAL",
        freshness="UNKNOWN",
        imported_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        record_count=7,
        quality_summary={"unmapped": 1},
    )
    session = AsyncMock()
    result_proxy = MagicMock()
    result_proxy.all.return_value = [newer, older]
    session.scalars = AsyncMock(return_value=result_proxy)

    result = await get_latest_dataset_statuses(session)
    games = next(row for row in result if row["dataset"] == "kbo_games")

    assert games["snapshot_id"] == "newer"
    assert games["status"] == "PARTIAL"
    assert games["record_count"] == 7
    assert games["quality_summary"] == {"unmapped": 1}
