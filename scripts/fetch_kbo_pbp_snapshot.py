"""Fetch a versioned KBO PBP Parquet snapshot from the public HF dataset.

This downloads a file only. It never writes to the application database.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Callable
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

import pyarrow.parquet as pq


REPOSITORY = "slothman3878/kbo_playbyplay"
API_URL = f"https://huggingface.co/api/datasets/{REPOSITORY}"
FILE_TEMPLATE = "v0/kbo_pbp_{season}.parquet"
REQUIRED_COLUMNS = {
    "game_pk", "game_date", "home_team", "away_team", "inning", "inning_topbot",
    "at_bat_number", "pitch_number", "batter", "pitcher", "batter_name",
    "pitcher_name", "stand", "events",
}
LICENSE_LABEL = "CC-BY-4.0 (as listed by the dataset publisher)"


def _read_url(url: str, opener: Callable = urlopen) -> tuple[bytes, dict[str, str], str]:
    request = Request(url, headers={"User-Agent": "DUGOUT-AI-PBP-Snapshot/1.0"})
    with opener(request, timeout=60) as response:
        return response.read(), dict(response.headers.items()), response.geturl()


def _validate_parquet(path: Path, season: int) -> dict[str, object]:
    parquet = pq.ParquetFile(path)
    missing = REQUIRED_COLUMNS - set(parquet.schema_arrow.names)
    if missing:
        raise ValueError(f"필수 PBP 컬럼이 없습니다: {sorted(missing)}")

    rows = 0
    dates: list[str] = []
    for batch in parquet.iter_batches(batch_size=16_384, columns=["game_date"]):
        values = [str(value)[:10] for value in batch.column(0).to_pylist() if value is not None]
        if any(not value.startswith(f"{season}-") for value in values):
            raise ValueError(f"다운로드한 파일에 {season}년이 아닌 경기 날짜가 포함돼 있습니다.")
        if values:
            rows += len(values)
            dates.extend((min(values), max(values)))
    if rows == 0:
        raise ValueError("PBP 파일에 유효한 경기 날짜가 없습니다.")
    return {
        "row_count": rows,
        "date_min": min(dates),
        "date_max": max(dates),
        "columns": sorted(parquet.schema_arrow.names),
    }


def fetch_snapshot(
    *,
    season: int,
    output: Path,
    revision: str = "main",
    force: bool = False,
    opener: Callable = urlopen,
) -> dict[str, object]:
    if not 2023 <= season <= 2026:
        raise ValueError("현재 공개 데이터셋은 2023~2026 시즌 파일만 제공합니다.")
    if output.exists() and not force:
        raise FileExistsError(f"파일이 이미 있습니다. 덮어쓰려면 --force를 지정하세요: {output}")

    api_payload, _, _ = _read_url(API_URL, opener)
    info = json.loads(api_payload)
    resolved_revision = info.get("sha") if revision == "main" else revision
    if not isinstance(resolved_revision, str) or len(resolved_revision) < 7:
        raise ValueError("Hugging Face 저장소 revision을 확인할 수 없습니다.")

    relative_file = FILE_TEMPLATE.format(season=season)
    file_url = (
        f"https://huggingface.co/datasets/{REPOSITORY}/resolve/"
        f"{resolved_revision}/{relative_file}"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".kbo-pbp-", suffix=".parquet", dir=output.parent, delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        request = Request(file_url, headers={"User-Agent": "DUGOUT-AI-PBP-Snapshot/1.0"})
        digest = hashlib.sha256()
        downloaded_bytes = 0
        with opener(request, timeout=120) as response, temp_path.open("wb") as target:
            final_url = response.geturl()
            while chunk := response.read(1024 * 1024):
                target.write(chunk)
                digest.update(chunk)
                downloaded_bytes += len(chunk)
            expected_length = response.headers.get("Content-Length")
        if expected_length and downloaded_bytes != int(expected_length):
            raise ValueError("다운로드한 파일 크기가 서버의 Content-Length와 다릅니다.")

        validation = _validate_parquet(temp_path, season)
        os.replace(temp_path, output)
        manifest = {
            "dataset_repository": REPOSITORY,
            "dataset_file": relative_file,
            "repository_revision": resolved_revision,
            "source_url": file_url,
            "final_download_host": urlsplit(final_url).netloc,
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "license_as_listed": LICENSE_LABEL,
            "attribution": "KBO play-by-play dataset by slothman3878",
            "upstream_source_note": "Publisher says extracted from Naver Sports relay API; underlying commercial rights are not independently verified.",
            "sha256": digest.hexdigest(),
            "downloaded_bytes": downloaded_bytes,
            **validation,
        }
        manifest_path = output.with_suffix(output.suffix + ".source.json")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return manifest
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--revision", default="main", help="HF commit SHA; main resolves to a pinned SHA")
    parser.add_argument("--force", action="store_true", help="replace an existing local file after download validation")
    args = parser.parse_args()
    output = args.output or Path(f"data/private/kbo_pbp_{args.season}.parquet")
    manifest = fetch_snapshot(season=args.season, output=output, revision=args.revision, force=args.force)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"\n로컬 snapshot 저장: {output}")
    print("DB 적재는 별도 검토 후 import_kbo_plate_appearances 명령으로 실행하세요.")


if __name__ == "__main__":
    main()
