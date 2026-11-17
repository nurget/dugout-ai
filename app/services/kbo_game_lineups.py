"""Preserve KBO game batting sheets; never infer starters from season records."""
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo import KboGame
from app.models.kbo_game_lineup import KboGameBoxscore, KboGameLineup
from app.services.data_catalog import record_import_batch
from app.services.team_codes import normalize_official_team_code


def _validate_player_identity(row: Any, *, label: str) -> tuple[str, str]:
    if not isinstance(row, dict):
        raise ValueError(f"{label} 기록은 객체여야 합니다.")
    player_id = row.get("player_id")
    name = row.get("player_name")
    if not isinstance(player_id, str) or not player_id.strip() or len(player_id) > 32:
        raise ValueError(f"{label} 선수 ID가 비어 있거나 올바르지 않습니다.")
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise ValueError(f"{label} 선수 이름이 비어 있거나 올바르지 않습니다.")
    raw_fields = row.get("raw_fields")
    if not isinstance(raw_fields, dict) or not raw_fields or not all(isinstance(k, str) and isinstance(v, str) for k, v in raw_fields.items()):
        raise ValueError(f"{label} 경기 원문 필드는 비어 있지 않은 문자열 객체여야 합니다.")
    return player_id.strip(), name.strip()


def normalize_game_boxscore(payload: dict[str, Any]) -> tuple[dict, list[dict]]:
    if not isinstance(payload, dict):
        raise ValueError("경기 기록지는 객체여야 합니다.")
    try:
        season = int(payload["season"])
        game_pk = str(payload["game_pk"]).strip()
        game_date = date.fromisoformat(str(payload["game_date"]))
        source_url = str(payload["source_url"])
        teams = payload["teams"]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("경기 기록지 식별 정보가 올바르지 않습니다.") from error
    if not 1982 <= season <= 2100 or game_date.year != season or not game_pk or len(game_pk) > 32:
        raise ValueError("경기 기록지의 시즌 및 경기 ID를 확인해 주세요.")
    if not source_url.startswith("https://www.koreabaseball.com/") or len(source_url) > 500:
        raise ValueError("KBO 경기 기록지 URL이 필요합니다.")
    if not isinstance(teams, list) or len(teams) != 2:
        raise ValueError("경기 기록지에는 두 구단이 필요합니다.")
    rows = []
    team_codes: set[str] = set()
    for team in teams:
        if not isinstance(team, dict):
            raise ValueError("구단 기록은 객체여야 합니다.")
        code = normalize_official_team_code(str(team.get("team_code", "")))
        if code not in {"HT", "SS", "LG", "KT", "SK", "NC", "OB", "LT", "HH", "WO"} or code in team_codes:
            raise ValueError("경기 기록지 구단이 비어 있거나 중복됩니다.")
        team_codes.add(code)
        seen: set[str] = set()
        starters: set[int] = set()
        batters = team.get("batters")
        if not isinstance(batters, list):
            raise ValueError("구단 타자 기록은 배열이어야 합니다.")
        for batter in batters:
            player_id, name = _validate_player_identity(batter, label="타자")
            try:
                order = int(batter["batting_order"])
                is_starter = batter["is_starter"]
                raw_fields = batter["raw_fields"]
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("타순 선수 기록이 올바르지 않습니다.") from error
            if not player_id or len(player_id) > 32 or not name or len(name) > 120 or player_id in seen:
                raise ValueError("타순 선수 식별 정보가 비어 있거나 중복됩니다.")
            if isinstance(batter["batting_order"], bool) or not 1 <= order <= 9 or not isinstance(is_starter, bool):
                raise ValueError("타순은 1~9, 선발 여부는 참/거짓이어야 합니다.")
            if not isinstance(raw_fields, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in raw_fields.items()):
                raise ValueError("경기 원문 필드는 문자열이어야 합니다.")
            if is_starter and order in starters:
                raise ValueError("같은 타순의 선발 선수가 중복됩니다.")
            seen.add(player_id)
            if is_starter:
                starters.add(order)
            rows.append({
                "team_code": code, "player_id": player_id, "player_name": name,
                "batting_order": order, "is_starter": is_starter,
                "position": str(batter["position"])[:40] if batter.get("position") else None,
                "raw_fields": raw_fields,
            })
        pitchers = team.get("pitchers", [])
        if not isinstance(pitchers, list):
            raise ValueError("구단 투수 기록은 배열이어야 합니다.")
        seen_pitchers: set[str] = set()
        for pitcher in pitchers:
            pitcher_id, _ = _validate_player_identity(pitcher, label="투수")
            if pitcher_id in seen_pitchers:
                raise ValueError("같은 구단의 투수 기록이 중복됩니다.")
            seen_pitchers.add(pitcher_id)
    if not rows:
        raise ValueError("경기 타자 기록이 없습니다.")
    return {"season": season, "game_pk": game_pk, "game_date": game_date, "source_url": source_url}, rows


async def import_game_boxscore(session: AsyncSession, payload: dict[str, Any]) -> int:
    metadata, rows = normalize_game_boxscore(payload)
    game = await session.get(KboGame, metadata["game_pk"])
    if not game or game.game_date != metadata["game_date"] or game.season != metadata["season"]:
        raise ValueError("기록지와 일치하는 경기 일정을 먼저 적재해 주세요.")
    expected = {normalize_official_team_code(game.home_team_code), normalize_official_team_code(game.away_team_code)}
    if {row["team_code"] for row in rows} != expected:
        raise ValueError("기록지 구단과 경기 일정 구단이 일치하지 않습니다.")
    await session.execute(delete(KboGameLineup).where(KboGameLineup.game_pk == metadata["game_pk"]))
    batch = await record_import_batch(
        session, dataset="kbo_game_lineups", source_name=metadata["source_url"],
        season=metadata["season"], season_type=game.season_type, record_count=len(rows),
        quality_summary={"game_pk": metadata["game_pk"], "team_count": 2, "raw_fields_preserved": True, "validation": "PASSED"},
    )
    now = datetime.now(timezone.utc)
    boxscore = await session.get(KboGameBoxscore, metadata["game_pk"])
    if boxscore is None:
        boxscore = KboGameBoxscore(game_pk=metadata["game_pk"])
        session.add(boxscore)
    boxscore.raw_payload = payload
    boxscore.source_url = metadata["source_url"]
    boxscore.imported_at = now
    session.add_all([KboGameLineup(**metadata, **row, source_batch_id=batch.id, imported_at=now) for row in rows])
    await session.flush()
    return len(rows)


async def get_game_boxscore(session: AsyncSession, game_pk: str) -> dict[str, Any] | None:
    game = await session.get(KboGame, game_pk)
    if game is None:
        return None
    boxscore = await session.get(KboGameBoxscore, game_pk)
    if boxscore:
        return {**boxscore.raw_payload, "available": True, "imported_at": boxscore.imported_at.isoformat()}
    rows = list((await session.scalars(select(KboGameLineup).where(KboGameLineup.game_pk == game_pk).order_by(KboGameLineup.team_code, KboGameLineup.batting_order, KboGameLineup.is_starter.desc(), KboGameLineup.id))).all())
    teams = []
    for code in (normalize_official_team_code(game.away_team_code), normalize_official_team_code(game.home_team_code)):
        teams.append({"team_code": code, "batters": [{"player_id": row.player_id, "player_name": row.player_name, "batting_order": row.batting_order, "is_starter": row.is_starter, "position": row.position, "raw_fields": row.raw_fields} for row in rows if row.team_code == code]})
    return {"game_pk": game.game_pk, "game_date": game.game_date.isoformat(), "teams": teams, "source_url": rows[0].source_url if rows else None, "available": bool(rows)}
