"""Import and direct read access for approved KBO player records."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import re
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo_player_record import KboPlayerRecord
from app.models.kbo_team_record import KboTeamRecord
from app.models.kbo import KboGame
from app.services.data_catalog import record_import_batch
from app.services.team_codes import (
    OFFICIAL_TEAM_CODES, game_team_code_candidates, normalize_official_team_code,
)


CATEGORIES = {"batter", "pitcher"}
SEASON_TYPES = {"REGULAR", "POSTSEASON"}
TEAM_CATEGORIES = {"standings", "batting", "pitching", "defense", "running"}
TEAM_DISPLAY_CODES = {"HT": "KIA", "SK": "SSG"}
QUALIFICATION_STANDARDS = {
    "plate_appearances_per_game": "3.1", "innings_per_game": 1,
    "rounding": "FLOOR", "regular_season_only": True,
    "definition": "KBO 야구규칙 9.22의 규정 타석·투구 횟수 충족 여부. 개인상 미달 타석 예외 판정은 포함하지 않음",
}


def canonical_team_code(code: str) -> str:
    value = normalize_official_team_code(code)
    return TEAM_DISPLAY_CODES.get(value, value)


def team_code_aliases(code: str) -> list[str]:
    canonical = canonical_team_code(code)
    return sorted({canonical, *game_team_code_candidates(code), *(
        key for key in OFFICIAL_TEAM_CODES if canonical_team_code(key) == canonical
    )})


class PlayerRecordError(ValueError):
    pass


def normalize_snapshot(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        season = int(payload["season"])
        season_type = str(payload["season_type"]).upper()
        category = str(payload["category"]).lower()
        source_url = str(payload["source_url"]).strip()
        records = payload["records"]
    except (KeyError, TypeError, ValueError) as error:
        raise PlayerRecordError(f"스냅샷 필드가 올바르지 않습니다: {error}") from error

    if not 1982 <= season <= 2100:
        raise PlayerRecordError("시즌이 허용 범위를 벗어났습니다.")
    if season_type not in SEASON_TYPES or category not in CATEGORIES:
        raise PlayerRecordError("대회 또는 기록 구분이 지원되지 않습니다.")
    if not source_url.startswith("https://www.koreabaseball.com/"):
        raise PlayerRecordError("KBO 사이트 출처 URL이 필요합니다.")
    fetched_at = payload.get("fetched_at")
    collected_at = None
    if fetched_at:
        try:
            collected_at = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
        except ValueError as error:
            raise PlayerRecordError("fetched_at이 ISO 날짜 형식이 아닙니다.") from error
        if collected_at.tzinfo is None:
            raise PlayerRecordError("fetched_at에는 시간대가 포함되어야 합니다.")
    if not isinstance(records, list) or not records:
        raise PlayerRecordError("선수 기록이 없거나 배열 형식이 아닙니다.")

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(records, start=1):
        if not isinstance(row, dict):
            raise PlayerRecordError(f"{index}번째 기록이 객체가 아닙니다.")
        player_id = str(row.get("player_id") or "").strip()
        player_name = str(row.get("선수명") or row.get("player_name") or "").strip()
        team_code = str(row.get("team_code") or "").strip().upper()
        raw_fields = row.get("raw_fields")
        profile = row.get("profile", {})
        if not isinstance(raw_fields, dict) or not raw_fields:
            raise PlayerRecordError(f"{index}번째 기록의 원문 필드가 없습니다.")
        if not player_id or not player_name or not team_code:
            raise PlayerRecordError(f"{index}번째 기록의 선수 식별 정보가 없습니다.")
        if len(player_id) > 32 or len(player_name) > 120 or len(team_code) > 12:
            raise PlayerRecordError(f"{index}번째 기록의 식별 정보가 너무 깁니다.")
        key = (player_id, team_code)
        if key in seen:
            raise PlayerRecordError(f"선수·구단 중복 기록: {key}")
        if not all(isinstance(field, str) and isinstance(value, str) for field, value in raw_fields.items()):
            raise PlayerRecordError(f"{index}번째 원문 필드는 문자열이어야 합니다.")
        if not isinstance(profile, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in profile.items()):
            raise PlayerRecordError(f"{index}번째 선수 프로필은 문자열 필드 객체여야 합니다.")
        seen.add(key)
        normalized.append({
            "player_id": player_id,
            "player_name": player_name,
            "team_code": team_code,
            "raw_fields": raw_fields,
            "profile": profile,
        })

    metadata = {
        "season": season,
        "season_type": season_type,
        "category": category,
        "source_url": source_url,
        "collected_at": collected_at,
        "source_urls": validate_source_urls(payload.get("source_urls", [source_url])),
    }
    return metadata, normalized


async def import_snapshot(session: AsyncSession, payload: dict[str, Any]) -> int:
    metadata, rows = normalize_snapshot(payload)
    await session.execute(
        delete(KboPlayerRecord).where(
            KboPlayerRecord.season == metadata["season"],
            KboPlayerRecord.season_type == metadata["season_type"],
            KboPlayerRecord.category == metadata["category"],
        )
    )
    batch = await record_import_batch(
        session,
        dataset="kbo_player_records",
        source_name=metadata["source_url"],
        season=metadata["season"],
        season_type=metadata["season_type"],
        record_count=len(rows),
        quality_summary={
            "category": metadata["category"],
            "team_count": len({row["team_code"] for row in rows}),
            "unique_players": len({row["player_id"] for row in rows}),
            "raw_fields_preserved": True,
            "generative_ai_used": False,
            "collected_at": metadata["collected_at"].isoformat() if metadata["collected_at"] else None,
            "validation": "PASSED",
        },
    )
    imported_at = datetime.now(timezone.utc)
    session.add_all([
        KboPlayerRecord(
            season=metadata["season"],
            season_type=metadata["season_type"],
            category=metadata["category"],
            player_id=row["player_id"],
            player_name=row["player_name"],
            team_code=row["team_code"],
            source_url=metadata["source_url"],
            raw_fields=row["raw_fields"],
            profile=row["profile"],
            source_urls=metadata["source_urls"],
            collected_at=metadata["collected_at"],
            source_batch_id=batch.id,
            imported_at=imported_at,
        )
        for row in rows
    ])
    await session.flush()
    return len(rows)


async def get_player_records(
    session: AsyncSession,
    *,
    season: int,
    category: str,
    season_type: str = "REGULAR",
    team_code: str | None = None,
    name: str | None = None,
    limit: int = 500,
) -> list[KboPlayerRecord]:
    query = select(KboPlayerRecord).where(
        KboPlayerRecord.season == season,
        KboPlayerRecord.category == category,
        KboPlayerRecord.season_type == season_type,
    )
    if team_code:
        query = query.where(KboPlayerRecord.team_code.in_(team_code_aliases(team_code)))
    if name and name.strip():
        query = query.where(KboPlayerRecord.player_name.ilike(f"%{name.strip()}%"))
    query = query.order_by(KboPlayerRecord.team_code, KboPlayerRecord.player_name).limit(limit)
    return list((await session.scalars(query)).all())


def validate_source_urls(value: Any) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(url, str) and url.startswith("https://www.koreabaseball.com/") and len(url) <= 300
        for url in value
    ):
        raise PlayerRecordError("출처 목록은 KBO 사이트 URL 배열이어야 합니다.")
    return list(dict.fromkeys(value))


def field_number(fields: dict[str, str], *keys: str) -> float | None:
    for key in keys:
        value = fields.get(key, "").strip().replace(",", "")
        if value in {"", "-", "—"}:
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return None


def nonnegative_integer(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value.strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0 or parsed != parsed.to_integral_value():
        return None
    return int(parsed)


def innings_to_outs(value: str | None) -> int | None:
    """Parse baseball thirds without rounding 143 2/3 innings into 144."""
    if value is None:
        return None
    text = value.strip().replace(",", "").replace("⅓", " 1/3").replace("⅔", " 2/3")
    if match := re.fullmatch(r"(\d+)(?:\.0+)?", text):
        return int(match[1]) * 3
    if match := re.fullmatch(r"(\d+)\s+([12])/3", text):
        return int(match[1]) * 3 + int(match[2])
    if match := re.fullmatch(r"([12])/3", text):
        return int(match[1])
    if match := re.fullmatch(r"(\d+)\.([12])", text):
        return int(match[1]) * 3 + int(match[2])
    return None


async def get_qualification_team_games(
    session: AsyncSession, *, season: int, season_type: str,
) -> dict[str, dict[str, Any]]:
    if season_type != "REGULAR":
        return {}
    rows = list((await session.scalars(select(KboTeamRecord).where(
        KboTeamRecord.season == season, KboTeamRecord.season_type == season_type,
    ).order_by(KboTeamRecord.imported_at.desc(), KboTeamRecord.id.desc()))).all())
    result: dict[str, dict[str, Any]] = {}
    # Prefer the standings team's game count; never use a player's maximum G.
    for category in ("standings", "batting", "pitching", "defense", "running"):
        for row in rows:
            code = canonical_team_code(row.team_code)
            if row.category != category or code in result:
                continue
            count = next((count for key in ("경기", "G", "경기수", "경기 수")
                if (count := nonnegative_integer(row.raw_fields.get(key))) is not None), None)
            if count is not None:
                result[code] = {"games": count, "basis": "TEAM_RECORD", "source_url": row.source_url}
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    completed = (await session.execute(select(KboGame.home_team_code, KboGame.away_team_code).where(
        KboGame.season == season, KboGame.season_type == season_type, KboGame.game_date <= today,
        func.lower(func.trim(KboGame.status)).in_(("final", "completed", "종료", "경기종료", "경기 종료")),
    ))).all()
    completed_counts: dict[str, int] = {}
    for home, away in completed:
        for code in {canonical_team_code(home), canonical_team_code(away)}:
            completed_counts[code] = completed_counts.get(code, 0) + 1
    for code, count in completed_counts.items():
        result.setdefault(code, {"games": count, "basis": "COMPLETED_GAMES", "source_url": None})
    return result


def player_qualification(row: KboPlayerRecord, team_games: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = team_games.get(canonical_team_code(row.team_code), {})
    games = source.get("games")
    min_pa = int((Decimal(games) * Decimal("3.1")).to_integral_value(rounding=ROUND_FLOOR)) if games is not None else None
    plate_appearances = nonnegative_integer(row.raw_fields.get("PA"))
    outs = innings_to_outs(row.raw_fields.get("IP"))
    qualification = {
        "team_games": games, "min_plate_appearances": min_pa, "min_innings": games,
        "actual_plate_appearances": plate_appearances, "actual_outs": outs,
        "is_qualified": None, "basis": source.get("basis", "UNKNOWN"),
        "source_url": source.get("source_url"), "reason": None,
    }
    if row.season_type != "REGULAR":
        qualification["reason"] = "NOT_REGULAR_SEASON"
    elif games is None:
        qualification["reason"] = "UNKNOWN_TEAM_GAME_COUNT"
    elif games <= 0:
        qualification["reason"] = "NO_TEAM_GAMES"
    elif row.category == "batter" and plate_appearances is None:
        qualification["reason"] = "MISSING_PLATE_APPEARANCES"
    elif row.category == "pitcher" and outs is None:
        qualification["reason"] = "MISSING_INNINGS"
    else:
        qualified = plate_appearances >= max(min_pa, 1) if row.category == "batter" else outs >= games * 3
        qualification["is_qualified"] = qualified
        qualification["reason"] = "MEETS_MINIMUM" if qualified else "BELOW_MINIMUM"
    return qualification


def record_metrics(fields: dict[str, str], category: str) -> dict[str, float | None]:
    """Calculate only metrics whose complete denominator is present in the source."""
    avg = field_number(fields, "AVG")
    obp = field_number(fields, "OBP")
    slg = field_number(fields, "SLG")
    ops = field_number(fields, "OPS")
    if ops is None and obp is not None and slg is not None:
        ops = round(obp + slg, 3)
    iso = round(slg - avg, 3) if slg is not None and avg is not None else None
    denominator = field_number(fields, "TBF", "BF") if category in {"pitcher", "pitching"} else field_number(fields, "PA")
    so, bb = field_number(fields, "SO"), field_number(fields, "BB")
    k_pct = round(100 * so / denominator, 2) if denominator and so is not None else None
    bb_pct = round(100 * bb / denominator, 2) if denominator and bb is not None else None
    return {
        "avg": avg, "obp": obp, "slg": slg, "ops": ops, "iso": iso,
        "era": field_number(fields, "ERA"), "whip": field_number(fields, "WHIP"),
        "k_pct": k_pct, "bb_pct": bb_pct,
        "k_minus_bb_pct": round(k_pct - bb_pct, 2) if k_pct is not None and bb_pct is not None else None,
    }


def player_position(row: KboPlayerRecord, pitcher_ids: set[str] | None = None) -> str | None:
    profile = row.profile or {}
    explicit = profile.get("position") or profile.get("포지션") or row.raw_fields.get("포지션")
    if explicit:
        return explicit
    if row.category == "pitcher" or row.player_id in (pitcher_ids or set()):
        return "투수"
    return None


def is_primary_pitcher(row: KboPlayerRecord, pitcher_ids: set[str] | None = None) -> bool:
    position = player_position(row, pitcher_ids)
    return bool(position and "투수" in position and not any(
        token in position for token in ("겸", "외야", "내야", "타자")
    ))


async def get_pitcher_player_ids(session: AsyncSession, *, season: int, season_type: str = "REGULAR") -> set[str]:
    return set((await session.scalars(select(KboPlayerRecord.player_id).where(
        KboPlayerRecord.season == season, KboPlayerRecord.season_type == season_type,
        KboPlayerRecord.category == "pitcher",
    ))).all())


async def filter_primary_batters(session: AsyncSession, rows: list[KboPlayerRecord], *,
    season: int, season_type: str = "REGULAR") -> list[KboPlayerRecord]:
    pitcher_ids = await get_pitcher_player_ids(session, season=season, season_type=season_type)
    return [row for row in rows if not is_primary_pitcher(row, pitcher_ids)]


def serialize_player_record(row: KboPlayerRecord, position: str | None = None) -> dict[str, Any]:
    return {
        "player_id": row.player_id, "player_name": row.player_name,
        "team_code": canonical_team_code(row.team_code), "category": row.category,
        "position": position or player_position(row), "profile": row.profile or {},
        "raw_fields": row.raw_fields, "metrics": record_metrics(row.raw_fields, row.category),
        "source_url": row.source_url, "source_urls": row.source_urls or [row.source_url],
        "source_batch_id": row.source_batch_id, "stat_source": "KBO_RECORDS",
        "collected_at": row.collected_at.isoformat() if row.collected_at else None,
        "imported_at": row.imported_at.isoformat(),
    }


async def get_player_record_payload(
    session: AsyncSession, *, season: int, category: str, season_type: str = "REGULAR",
    team_code: str | None = None, name: str | None = None,
    include_pitchers: bool = False, limit: int = 1000,
    qualified_only: bool = False,
) -> dict[str, Any]:
    rows = await get_player_records(session, season=season, category=category,
        season_type=season_type, team_code=team_code, name=name, limit=10000)
    pitcher_ids = await get_pitcher_player_ids(session, season=season, season_type=season_type) if category == "batter" else set()
    team_games = await get_qualification_team_games(session, season=season, season_type=season_type)
    data = []
    excluded_pitchers = 0
    for row in rows:
        position = player_position(row, pitcher_ids)
        if category == "batter" and not include_pitchers and is_primary_pitcher(row, pitcher_ids):
            excluded_pitchers += 1
            continue
        record = serialize_player_record(row, position)
        record["qualification"] = player_qualification(row, team_games)
        data.append(record)
    qualification_summary = {
        "qualified": sum(row["qualification"]["is_qualified"] is True for row in data),
        "unqualified": sum(row["qualification"]["is_qualified"] is False for row in data),
        "unknown": sum(row["qualification"]["is_qualified"] is None for row in data),
    }
    if qualified_only:
        data = [row for row in data if row["qualification"]["is_qualified"] is True]
    return {
        "season": season, "season_type": season_type, "category": category,
        "team_code": canonical_team_code(team_code) if team_code else None,
        "count": len(data[:limit]), "total_count": len(data), "limit": limit,
        "include_pitchers": include_pitchers, "excluded_pitchers": excluded_pitchers,
        "qualified_only": qualified_only, "qualification_standards": QUALIFICATION_STANDARDS,
        "qualification_summary": qualification_summary,
        "stat_source": "KBO_RECORDS", "data": data[:limit],
        "note": "KBO 기록실의 시즌 누적 기록이에요. 투수의 타격 기록은 '투수 타격 포함'을 켜면 볼 수 있어요." if category == "batter" else "KBO 기록실의 시즌 누적 투수 기록이에요.",
    }


def normalize_team_snapshot(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    category = payload.get("category")
    if category not in TEAM_CATEGORIES:
        raise PlayerRecordError("지원하지 않는 구단 기록 구분입니다.")
    if isinstance(payload.get("records"), list) and not all(isinstance(row, dict) for row in payload["records"]):
        raise PlayerRecordError("구단 기록은 객체 배열이어야 합니다.")
    # Reuse the same source/time/schema validation used for player snapshots.
    adapted = {**payload, "category": "batter", "records": [
        {**row, "player_id": row.get("team_code"), "player_name": row.get("team_code")}
        for row in payload.get("records", [])
    ]} if isinstance(payload.get("records"), list) else {**payload, "category": "batter"}
    metadata, rows = normalize_snapshot(adapted)
    metadata["category"] = category
    normalized = []
    seen = set()
    for row in rows:
        code = canonical_team_code(row["team_code"])
        if code in seen:
            raise PlayerRecordError(f"구단 중복 기록: {code}")
        seen.add(code)
        normalized.append({"team_code": code, "raw_fields": row["raw_fields"]})
    return metadata, normalized


async def import_team_snapshot(session: AsyncSession, payload: dict[str, Any]) -> int:
    metadata, rows = normalize_team_snapshot(payload)
    await session.execute(delete(KboTeamRecord).where(
        KboTeamRecord.season == metadata["season"], KboTeamRecord.season_type == metadata["season_type"],
        KboTeamRecord.category == metadata["category"],
    ))
    batch = await record_import_batch(session, dataset="kbo_team_records", source_name=metadata["source_url"],
        season=metadata["season"], season_type=metadata["season_type"], record_count=len(rows),
        quality_summary={"category": metadata["category"], "team_count": len(rows), "raw_fields_preserved": True,
            "collected_at": metadata["collected_at"].isoformat() if metadata["collected_at"] else None,
            "generative_ai_used": False, "validation": "PASSED"})
    imported_at = datetime.now(timezone.utc)
    session.add_all([KboTeamRecord(**metadata, **row, source_batch_id=batch.id, imported_at=imported_at) for row in rows])
    await session.flush()
    return len(rows)


async def get_team_record_payload(session: AsyncSession, *, season: int, category: str,
    season_type: str = "REGULAR", team_code: str | None = None) -> dict[str, Any]:
    query = select(KboTeamRecord).where(KboTeamRecord.season == season,
        KboTeamRecord.season_type == season_type, KboTeamRecord.category == category)
    if team_code:
        query = query.where(KboTeamRecord.team_code.in_(team_code_aliases(team_code)))
    rows = list((await session.scalars(query.order_by(KboTeamRecord.team_code))).all())
    data = [{"team_code": canonical_team_code(row.team_code), "raw_fields": row.raw_fields,
        "metrics": record_metrics(row.raw_fields, row.category), "source_url": row.source_url,
        "source_urls": row.source_urls or [row.source_url], "source_batch_id": row.source_batch_id,
        "collected_at": row.collected_at.isoformat() if row.collected_at else None,
        "imported_at": row.imported_at.isoformat()} for row in rows]
    return {"season": season, "season_type": season_type, "category": category,
        "count": len(data), "stat_source": "KBO_RECORDS", "data": data,
        "note": "KBO 기록실의 구단 기록을 그대로 표시해요."}


async def get_record_coverage(session: AsyncSession, *, season: int) -> dict[str, Any]:
    data = []
    for model, scope in ((KboPlayerRecord, "players"), (KboTeamRecord, "teams")):
        rows = (await session.execute(select(model.category, model.season_type, func.count(model.id),
            func.max(model.collected_at), func.max(model.imported_at)).where(model.season == season)
            .group_by(model.category, model.season_type))).all()
        for category, season_type, count, collected_at, imported_at in rows:
            data.append({"scope": scope, "category": category, "season_type": season_type,
                "count": count, "collected_at": collected_at.isoformat() if collected_at else None,
                "imported_at": imported_at.isoformat() if imported_at else None})
    return {"season": season, "stat_source": "KBO_RECORDS", "data": data}
