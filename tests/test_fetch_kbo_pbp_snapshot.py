import io
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.fetch_kbo_pbp_snapshot import REQUIRED_COLUMNS, fetch_snapshot


class FakeResponse:
    def __init__(self, payload: bytes, url: str):
        self.payload = io.BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload))}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.payload.read(size)

    def geturl(self):
        return self.url


def small_parquet(season: int) -> bytes:
    values = {column: [None] for column in REQUIRED_COLUMNS}
    values.update({
        "game_pk": [f"{season}0401HTLG02026"],
        "game_date": [f"{season}-04-01"],
        "home_team": ["LG"],
        "away_team": ["HT"],
        "inning": [1],
        "inning_topbot": ["top"],
        "at_bat_number": [1],
        "pitch_number": [1],
        "batter": ["20001"],
        "pitcher": ["10001"],
        "batter_name": ["타자"],
        "pitcher_name": ["투수"],
        "stand": ["R"],
        "events": ["strikeout"],
    })
    buffer = io.BytesIO()
    pq.write_table(pa.table(values), buffer)
    return buffer.getvalue()


def test_fetch_writes_season_file_and_pinned_source_manifest(tmp_path: Path):
    parquet = small_parquet(2026)

    def opener(request, timeout=60):
        if request.full_url.endswith("/api/datasets/slothman3878/kbo_playbyplay"):
            return FakeResponse(json.dumps({"sha": "abcdef1234567890"}).encode(), request.full_url)
        assert "/resolve/abcdef1234567890/v0/kbo_pbp_2026.parquet" in request.full_url
        return FakeResponse(parquet, "https://cdn.example/kbo_pbp_2026.parquet")

    output = tmp_path / "data" / "kbo_pbp_2026.parquet"
    manifest = fetch_snapshot(season=2026, output=output, opener=opener)

    assert output.read_bytes() == parquet
    assert manifest["repository_revision"] == "abcdef1234567890"
    assert manifest["final_download_host"] == "cdn.example"
    assert "final_download_url" not in manifest
    assert manifest["row_count"] == 1
    assert manifest["date_min"] == "2026-04-01"
    assert "underlying commercial rights" in manifest["upstream_source_note"]
    saved_manifest = json.loads(output.with_suffix(".parquet.source.json").read_text())
    assert saved_manifest["sha256"] == manifest["sha256"]


def test_fetch_rejects_mixed_season_and_does_not_replace_destination(tmp_path: Path):
    output = tmp_path / "kbo_pbp_2026.parquet"
    output.write_bytes(b"existing snapshot")
    parquet = small_parquet(2025)

    def opener(request, timeout=60):
        if "/api/datasets/" in request.full_url:
            return FakeResponse(json.dumps({"sha": "abcdef1234567890"}).encode(), request.full_url)
        return FakeResponse(parquet, request.full_url)

    with pytest.raises(FileExistsError):
        fetch_snapshot(season=2026, output=output, opener=opener)
    with pytest.raises(ValueError, match="2026년이 아닌"):
        fetch_snapshot(season=2026, output=output, force=True, opener=opener)
    assert output.read_bytes() == b"existing snapshot"
    assert not list(tmp_path.glob(".kbo-pbp-*.parquet"))
