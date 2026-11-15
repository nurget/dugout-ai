from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.import_kbo_pitch_events import _to_record, validate_file


def pitch_row(**overrides):
    row = {
        "game_pk": "20230401LGSS0",
        "game_date": "2023-04-01",
        "home_team": "LG",
        "away_team": "SSG",
        "inning": 1,
        "inning_topbot": "top",
        "at_bat_number": 1,
        "pitch_number": 1,
        "batter": "12345",
        "pitcher": "54321",
        "batter_name": "타자",
        "pitcher_name": "투수",
        "pitch_result": "S",
        "pitch_type": "FF",
        "pitch_name": "포심",
        "release_speed_kmh": 151.2,
        "events": None,
        "balls": 0,
        "strikes": 0,
        "plate_x": 0.2,
        "plate_z": 1.4,
    }
    row.update(overrides)
    return row


def write_parquet(path: Path, rows: list[dict]) -> None:
    pq.write_table(pa.Table.from_pylist(rows), path)


def test_validate_file_counts_rows_and_preserves_source_schema(tmp_path):
    path = tmp_path / "pitches.parquet"
    write_parquet(path, [pitch_row(), pitch_row(pitch_number=2)])

    quality = validate_file(path, 2023)

    assert quality["valid_rows"] == 2
    assert quality["duplicate_rows"] == 0
    assert quality["game_count"] == 1
    assert quality["batter_count"] == 1
    assert quality["pitcher_count"] == 1
    assert quality["columns"] == sorted(pq.ParquetFile(path).schema_arrow.names)


def test_validate_file_deduplicates_identical_pitch_key(tmp_path):
    path = tmp_path / "pitches.parquet"
    row = pitch_row()
    write_parquet(path, [row, row.copy()])

    quality = validate_file(path, 2023)

    assert quality["valid_rows"] == 1
    assert quality["duplicate_rows"] == 1


def test_validate_file_rejects_conflicting_pitch_key(tmp_path):
    path = tmp_path / "pitches.parquet"
    write_parquet(path, [pitch_row(), pitch_row(pitch_result="B")])

    with pytest.raises(ValueError, match="상충 데이터"):
        validate_file(path, 2023)


def test_to_record_normalizes_teams_and_keeps_unmodeled_raw_fields():
    record = _to_record(pitch_row(on_1b="23456"), 2023, "batch-id")

    assert record["game_date"].isoformat() == "2023-04-01"
    assert record["home_team_code"] == "LG"
    assert record["away_team_code"] == "SK"
    assert record["raw_payload"]["on_1b"] == "23456"
    assert record["raw_payload"]["plate_z"] == 1.4
    assert record["source_batch_id"] == "batch-id"
