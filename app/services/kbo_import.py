from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo import KboGame, KboTeam


class InvalidKboDataset(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedGame:
    game_pk: str
    season: int
    game_date: date
    home_code: str
    home_name: str
    away_code: str
    away_name: str
    home_score: int | None
    away_score: int | None
    status: str


def _team(side: dict[str, Any]) -> tuple[str, str]:
    details = side["team"]
    code = str(details["abbrev"]).strip().upper()
    name = str(details["name"]).strip()
    if not code or not name or len(code) > 8:
        raise InvalidKboDataset("팀 코드 또는 이름이 올바르지 않습니다.")
    return code, name


def normalize_game(raw: dict[str, Any], season: int) -> NormalizedGame:
    try:
        sides = raw["teams"]
        home = sides["home"]
        away = sides["away"]
        home_code, home_name = _team(home)
        away_code, away_name = _team(away)
        game_pk = str(raw["gamePk"])
        game_date = date.fromisoformat(str(raw["officialDate"]))
        status = str(raw["status"]["detailedState"])
        home_score = home.get("score")
        away_score = away.get("score")
        if not game_pk or len(game_pk) > 32 or home_code == away_code:
            raise ValueError("경기 ID 또는 팀 정보가 유효하지 않습니다.")
        if game_date.year != season:
            raise ValueError("시즌과 경기 날짜의 연도가 다릅니다.")
        for score in (home_score, away_score):
            if score is not None and (type(score) is not int or score < 0):
                raise ValueError("점수가 유효하지 않습니다.")
        return NormalizedGame(game_pk, season, game_date, home_code, home_name,
                              away_code, away_name, home_score, away_score, status)
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidKboDataset(f"경기 데이터 형식 오류: {exc}") from exc


def normalize_dataset(
    payload: dict[str, Any] | list[dict[str, Any]],
) -> list[NormalizedGame]:
    try:
        if isinstance(payload, list):
            # 실제 KBO 데이터는 경기 목록이 최상위 배열이다.
            records = payload

            if not records:
                raise ValueError("경기 데이터가 비어 있습니다.")

            # 시즌 정보가 따로 없으므로 경기 날짜에서 추출한다.
            first_date = date.fromisoformat(
                str(records[0]["officialDate"])
            )
            season = first_date.year

        elif isinstance(payload, dict):
            # 기존 테스트 데이터 형태도 계속 지원한다.
            season = int(payload["season"])
            records = payload["games"]

        else:
            raise ValueError("지원하지 않는 JSON 구조입니다.")

        if (
            not isinstance(records, list)
            or not 1982 <= season <= 2100
        ):
            raise ValueError("시즌 또는 경기 배열이 유효하지 않습니다.")

    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise InvalidKboDataset(
            f"시즌 데이터 형식 오류: {exc}"
        ) from exc

    result = [
        normalize_game(record, season)
        for record in records
    ]

    ids = [game.game_pk for game in result]

    if len(ids) != len(set(ids)):
        raise InvalidKboDataset("경기 ID가 중복됐습니다.")

    return result


async def import_games(session: AsyncSession, games: list[NormalizedGame], source_name: str) -> int:
    """한 배치 전체를 검증한 뒤 동일 경기 ID는 갱신한다.

    PostgreSQL/SQLite 양쪽에서 동작하는 소규모 배치용 ORM 구현.
    작업 도중 예외가 나면 호출자가 rollback할 수 있도록 commit하지 않는다.
    """
    for game in games:
        for code, name in ((game.home_code, game.home_name), (game.away_code, game.away_name)):
            team = await session.get(KboTeam, code)
            if team is None:
                session.add(KboTeam(code=code, name=name))
                await session.flush()
            else:
                team.name = name

        existing = await session.get(KboGame, game.game_pk)
        if existing is None:
            existing = KboGame(game_pk=game.game_pk)
            session.add(existing)
        existing.season = game.season
        existing.game_date = game.game_date
        existing.home_team_code = game.home_code
        existing.away_team_code = game.away_code
        existing.home_score = game.home_score
        existing.away_score = game.away_score
        existing.status = game.status
        existing.source_name = source_name
    await session.flush()
    return len(games)
