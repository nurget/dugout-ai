
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo import KboGame
from app.models.kbo_pitcher_appearance import KboPitcherAppearance


async def get_recent_pitcher_appearances(
    db: AsyncSession,
    *,
    season: int,
    as_of_date: date,
    team_code: str | None = None,
    lookback_days: int = 7,
) -> list[dict]:
    """
    분석 기준일 이전의 실제 경기별 투수 기록을 조회한다.

    team_code=None:
        KBO 전체 구단 조회

    team_code 지정:
        해당 구단만 조회

    현재 경기의 기록이 분석에 섞이지 않도록
    as_of_date 당일 이후 데이터는 제외한다.
    """

    if lookback_days < 1:
        raise ValueError("lookback_days는 1 이상이어야 합니다.")

    start_date = as_of_date - timedelta(days=lookback_days)

    statement = (
        select(
            KboPitcherAppearance.game_pk,
            KboPitcherAppearance.pitcher_name,
            KboPitcherAppearance.team_code,
            KboPitcherAppearance.pitches,
            KboGame.game_date,
        )
        .join(
            KboGame,
            KboGame.game_pk == KboPitcherAppearance.game_pk,
        )
        .where(
            KboGame.season == season,
            KboGame.season_type == "REGULAR",
            KboGame.game_date >= start_date,
            KboGame.game_date < as_of_date,
        )
        .order_by(
            KboGame.game_date,
            KboPitcherAppearance.team_code,
            KboPitcherAppearance.pitcher_name,
        )
    )

    if team_code is not None:
        statement = statement.where(
            KboPitcherAppearance.team_code == team_code
        )

    result = await db.execute(statement)

    return [
        dict(row)
        for row in result.mappings().all()
    ]