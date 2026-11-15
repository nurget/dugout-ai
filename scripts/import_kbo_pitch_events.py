"""투구 단위 KBO PBP를 원본 필드와 함께 검증하고 적재한다.

기본은 검증 전용이다. DB 전체 적재:
  uv run python -m scripts.import_kbo_pitch_events data/private/kbo_pbp_2025.parquet --season 2025 --apply
"""
import argparse
import asyncio
from datetime import date
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterator

import pyarrow.parquet as pq
from sqlalchemy import delete, insert

from app.db.session import AsyncSessionLocal
from app.models.kbo_pitch_event import KboPitchEvent
from app.services.data_catalog import record_import_batch
from app.services.team_codes import normalize_official_team_code


IDENTITY_COLUMNS = (
    "game_pk", "game_date", "at_bat_number", "pitch_number", "batter", "pitcher",
)


def _date_value(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        return _json_value(value.item())
    return str(value)


def _signature(row: dict[str, Any]) -> str:
    normalized = {key: _json_value(value) for key, value in row.items()}
    return hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _to_record(row: dict[str, Any], season: int, source_batch_id: str | None = None) -> dict[str, Any]:
    game_date = _date_value(row["game_date"])
    release_speed = _json_value(row.get("release_speed_kmh"))
    return {
        "season": season,
        "game_pk": str(row["game_pk"]).strip(),
        "game_date": game_date,
        "inning": int(row["inning"]) if row.get("inning") is not None else None,
        "inning_topbot": str(row["inning_topbot"]) if row.get("inning_topbot") else None,
        "at_bat_number": int(row["at_bat_number"]),
        "pitch_number": int(row["pitch_number"]),
        "home_team_code": normalize_official_team_code(str(row["home_team"])) if row.get("home_team") else None,
        "away_team_code": normalize_official_team_code(str(row["away_team"])) if row.get("away_team") else None,
        "batter_id": str(row["batter"]).strip(),
        "batter_name": str(row["batter_name"])[:120] if row.get("batter_name") else None,
        "pitcher_id": str(row["pitcher"]).strip(),
        "pitcher_name": str(row["pitcher_name"])[:120] if row.get("pitcher_name") else None,
        "pitch_result": str(row["pitch_result"])[:32] if row.get("pitch_result") else None,
        "pitch_type": str(row["pitch_type"])[:16] if row.get("pitch_type") else None,
        "pitch_name": str(row["pitch_name"])[:80] if row.get("pitch_name") else None,
        "release_speed_kmh": float(release_speed) if release_speed is not None else None,
        "events": str(row["events"])[:40] if row.get("events") else None,
        "raw_payload": {key: _json_value(value) for key, value in row.items()},
        "source_batch_id": source_batch_id,
    }


def _rows(path: Path) -> Iterator[dict[str, Any]]:
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=4096):
        yield from batch.to_pylist()


def validate_file(path: Path, season: int) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    columns = set(parquet.schema_arrow.names)
    missing = set(IDENTITY_COLUMNS) - columns
    if missing:
        raise ValueError(f"필수 투구 식별 컬럼이 없습니다: {sorted(missing)}")

    quality: dict[str, Any] = {
        "pitch_rows_seen": 0,
        "valid_rows": 0,
        "duplicate_rows": 0,
        "conflicting_duplicates": 0,
        "invalid_identity": 0,
        "out_of_season": 0,
        "game_count": 0,
        "batter_count": 0,
        "pitcher_count": 0,
        "date_min": None,
        "date_max": None,
        "columns": sorted(columns),
    }
    seen: dict[tuple[str, int, int], str] = {}
    games: set[str] = set()
    batters: set[str] = set()
    pitchers: set[str] = set()
    dates: list[date] = []
    for row in _rows(path):
        quality["pitch_rows_seen"] += 1
        try:
            game_date = _date_value(row["game_date"])
            if game_date.year != season:
                quality["out_of_season"] += 1
                continue
            game_pk = str(row["game_pk"]).strip()
            at_bat = int(row["at_bat_number"])
            pitch_number = int(row["pitch_number"])
            batter_id = str(row["batter"]).strip()
            pitcher_id = str(row["pitcher"]).strip()
            if not game_pk or at_bat < 1 or pitch_number < 0 or not batter_id or not pitcher_id:
                raise ValueError("empty or invalid identity")
        except (KeyError, TypeError, ValueError, OverflowError):
            quality["invalid_identity"] += 1
            continue

        key = (game_pk, at_bat, pitch_number)
        signature = _signature(row)
        previous = seen.get(key)
        if previous is not None:
            if previous == signature:
                quality["duplicate_rows"] += 1
            else:
                quality["conflicting_duplicates"] += 1
            continue
        seen[key] = signature
        quality["valid_rows"] += 1
        games.add(game_pk)
        batters.add(batter_id)
        pitchers.add(pitcher_id)
        dates.append(game_date)

    quality["game_count"] = len(games)
    quality["batter_count"] = len(batters)
    quality["pitcher_count"] = len(pitchers)
    quality["date_min"] = min(dates).isoformat() if dates else None
    quality["date_max"] = max(dates).isoformat() if dates else None
    if quality["valid_rows"] == 0:
        raise ValueError(f"{season} 시즌에 적재할 유효 투구가 없습니다.")
    if quality["conflicting_duplicates"]:
        raise ValueError("동일 투구 키의 상충 데이터가 있어 적재를 중단했습니다.")
    return quality


async def import_file(path: Path, *, season: int, apply: bool) -> dict[str, Any]:
    quality = validate_file(path, season)
    manifest_path = path.with_suffix(path.suffix + ".source.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    source_name = (
        f"{manifest.get('dataset_repository', 'unknown')}@{manifest.get('repository_revision', 'unknown')}"
    )
    print(json.dumps(quality, ensure_ascii=False, indent=2))
    if not apply:
        print("검증만 진행했습니다. DB 반영에는 --apply가 필요합니다.")
        return quality

    batch_size = 2000
    async with AsyncSessionLocal() as session:
        try:
            batch = await record_import_batch(
                session,
                dataset="kbo_pitch_events",
                source_name=source_name,
                season=season,
                record_count=quality["valid_rows"],
                status="PARTIAL" if quality["invalid_identity"] or quality["out_of_season"] else "SUCCESS",
                quality_summary={
                    **quality,
                    "source_file": path.name,
                    "license_as_listed": manifest.get("license_as_listed"),
                    "attribution": manifest.get("attribution"),
                    "source_url": manifest.get("source_url"),
                    "sha256": manifest.get("sha256"),
                },
            )
            # Validate the full source before replacing only this season's snapshot.
            await session.execute(delete(KboPitchEvent).where(KboPitchEvent.season == season))
            pending = []
            seen: set[tuple[str, int, int]] = set()
            for row in _rows(path):
                try:
                    game_date = _date_value(row["game_date"])
                    key = (str(row["game_pk"]).strip(), int(row["at_bat_number"]), int(row["pitch_number"]))
                    if game_date.year != season or not str(row["batter"]).strip() or not str(row["pitcher"]).strip():
                        continue
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
                if key in seen:
                    continue
                seen.add(key)
                pending.append(_to_record(row, season, batch.id))
                if len(pending) >= batch_size:
                    await session.execute(insert(KboPitchEvent), pending)
                    pending.clear()
            if pending:
                await session.execute(insert(KboPitchEvent), pending)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    print(f"저장 완료: {quality['valid_rows']:,} 투구 ({season} 시즌; 시즌 기존 snapshot 교체)")
    return quality


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(import_file(args.path, season=args.season, apply=args.apply))


if __name__ == "__main__":
    main()
