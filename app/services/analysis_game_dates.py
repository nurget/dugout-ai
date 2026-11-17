"""Resolve analysis cutoffs from the authenticated club's playable game dates."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo import KboGame
from app.services.team_codes import game_team_code_candidates


def eligible_game_conditions(team_code: str, today: date | None = None) -> list:
    """Share the same date policy between the date picker and the stream preflight."""
    codes = game_team_code_candidates(team_code)
    today = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    status = func.lower(func.trim(KboGame.status))
    return [
        or_(KboGame.home_team_code.in_(codes), KboGame.away_team_code.in_(codes)),
        KboGame.game_date <= today,
        *(~status.like(f"%{token}%") for token in ("cancel", "postpon", "취소", "연기")),
    ]


async def resolve_analysis_game_date(
    session: AsyncSession, *, team_code: str, requested_date: date | None,
    today: date | None = None,
) -> date:
    today = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    if requested_date is not None and requested_date > today:
        raise ValueError("분석 기준일은 미래일 수 없습니다.")
    query = select(KboGame.game_date).where(*eligible_game_conditions(team_code, today))
    if requested_date is not None:
        query = query.where(KboGame.game_date == requested_date)
    result = await session.scalar(query.order_by(KboGame.game_date.desc()).limit(1))
    if result is None:
        if requested_date is None:
            raise ValueError("분석할 경기 날짜가 없어요. 소속 구단의 경기 일정을 먼저 불러와 주세요.")
        raise ValueError("소속 구단의 경기가 있었던 날짜를 선택해 주세요. 취소·연기된 경기는 분석할 수 없어요.")
    return result
