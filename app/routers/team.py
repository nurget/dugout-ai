from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.db.session import get_db
from app.services.team_data import get_team_games
from app.services.kbo_player_records import get_player_record_payload, field_number
from app.services.data_catalog import get_latest_dataset_statuses
from app.schemas.matchup import LineupMatchupRequest


router = APIRouter(
    prefix="/api/teams/me",
    tags=["my-team"],
)

SessionDep = Annotated[AsyncSession, Depends(get_db)]


def serialize_model(model) -> dict:
    result = {}

    for column in model.__table__.columns:
        value = getattr(model, column.name)

        if isinstance(value, (date, datetime)):
            value = value.isoformat()

        result[column.name] = value

    return result


@router.get("")
async def get_my_team(
    current_user: CurrentUser,
):
    return {
        "username": current_user.username,
        "team_code": current_user.team_code,
        "role": current_user.role,
        "season": 2026,
    }


@router.get("/games")
async def get_my_team_games(
    current_user: CurrentUser,
    session: SessionDep,
    season: int = Query(default=2026, ge=1982, le=2100),
    season_type: str = Query(default="REGULAR", pattern="^(REGULAR|POSTSEASON)$"),
    season_phase: str | None = Query(default=None, pattern="^(WILDCARD|SEMIPLAYOFF|PLAYOFF|KOREAN_SERIES)$"),
):
    games = await get_team_games(
        session=session,
        team_code=current_user.team_code,
        season=season,
        season_type=season_type,
        season_phase=season_phase,
    )

    return {
        "team_code": current_user.team_code,
        "season": season,
        "season_type": season_type,
        "count": len(games),
        "data": [
            serialize_model(game)
            for game in games
        ],
    }


@router.get("/pitchers")
async def get_my_team_pitchers(
    current_user: CurrentUser,
    session: SessionDep,
    season: int = Query(default=2026, ge=1982, le=2100),
    season_type: str = Query(default="REGULAR", pattern="^(REGULAR|POSTSEASON|WILDCARD|SEMIPLAYOFF|PLAYOFF|KOREAN_SERIES)$"),
    as_of_date: date | None = Query(default=None),
    qualified_only: bool = Query(default=False),
):
    if as_of_date is not None:
        if qualified_only:
            raise HTTPException(status_code=422, detail="규정 기록 필터는 시즌 기록 조회에서만 사용할 수 있어요.")
        if season_type != "REGULAR":
            raise HTTPException(status_code=422, detail="기준일 누적 집계는 정규시즌만 지원합니다.")
        if as_of_date.year != season:
            raise HTTPException(status_code=422, detail="기준일과 시즌 연도가 일치해야 합니다.")
        if as_of_date > datetime.now(ZoneInfo("Asia/Seoul")).date():
            raise HTTPException(status_code=422, detail="기준일은 미래일 수 없습니다.")

        from app.services.as_of_pitcher import get_pitcher_stats_as_of

        result = await get_pitcher_stats_as_of(
            session,
            season=season,
            team_code=current_user.team_code,
            as_of_date=as_of_date,
        )
        statuses = await get_latest_dataset_statuses(session)
        snapshot = next(
            row["snapshot_id"]
            for row in statuses
            if row["dataset"] == "kbo_pitcher_appearances"
        )
        return {
            "team_code": current_user.team_code,
            "season": season,
            "season_type": "REGULAR",
            "as_of_date": as_of_date.isoformat(),
            "data_snapshot_id": snapshot,
            "stat_source": result["stat_source"],
            "coverage": result["coverage"],
            "provenance": result["provenance"],
            "data_through_date": result["data_through_date"],
            "count": len(result["pitchers"]),
            "data": result["pitchers"],
            "withheld": result["withheld"],
            "limitations": result["limitations"],
        }

    result = await get_player_record_payload(session, season=season, category="pitcher",
        team_code=current_user.team_code, season_type=season_type, qualified_only=qualified_only)
    for row in result["data"]:
        fields, metrics = row["raw_fields"], row["metrics"]
        row.update({"id": row["player_id"], "pitcher_name": row["player_name"],
            "games": field_number(fields, "G"), "batters_faced": field_number(fields, "TBF", "BF"),
            "strikeouts": field_number(fields, "SO"), "walks": field_number(fields, "BB"),
            "k_pct": metrics["k_pct"], "bb_pct": metrics["bb_pct"], "k_minus_bb_pct": metrics["k_minus_bb_pct"]})
    return result


@router.get("/batters")
async def get_my_team_batting_stats(
    current_user: CurrentUser,
    session: SessionDep,
    season: int = Query(default=2026, ge=1982, le=2100),
    as_of_date: date | None = Query(default=None),
    name: str | None = Query(default=None, min_length=1, max_length=80),
    season_type: str = Query(default="REGULAR", pattern="^(REGULAR|POSTSEASON)$"),
    include_pitchers: bool = Query(default=False),
    qualified_only: bool = Query(default=False),
):
    """KBO 시즌 기록을 표시하고 과거 기준일 요청만 별도 PBP 집계로 처리한다."""
    if as_of_date is None:
        return await get_player_record_payload(session, season=season, category="batter",
            season_type=season_type, team_code=current_user.team_code, name=name,
            include_pitchers=include_pitchers, qualified_only=qualified_only)
    if as_of_date is not None:
        if qualified_only:
            raise HTTPException(status_code=422, detail="규정 기록 필터는 시즌 기록 조회에서만 사용할 수 있어요.")
        if as_of_date.year != season:
            raise HTTPException(status_code=422, detail="기준일과 시즌 연도가 일치해야 합니다.")
        if as_of_date > datetime.now(ZoneInfo("Asia/Seoul")).date():
            raise HTTPException(status_code=422, detail="기준일은 미래일 수 없습니다.")
    from app.services.pbp_season_stats import get_team_batting_stats

    try:
        return await get_team_batting_stats(
            session,
            season=season,
            team_code=current_user.team_code,
            as_of_date=as_of_date,
            name=name,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/pbp-pitchers")
async def get_my_team_pbp_pitching_stats(
    current_user: CurrentUser,
    session: SessionDep,
    season: int = Query(default=2026, ge=1982, le=2100),
    as_of_date: date | None = Query(default=None),
    name: str | None = Query(default=None, min_length=1, max_length=80),
):
    """로그인 구단의 완료 타석 PBP에서 계산한 투수 성적을 반환한다."""
    if as_of_date is not None:
        if as_of_date.year != season:
            raise HTTPException(status_code=422, detail="기준일과 시즌 연도가 일치해야 합니다.")
        if as_of_date > datetime.now(ZoneInfo("Asia/Seoul")).date():
            raise HTTPException(status_code=422, detail="기준일은 미래일 수 없습니다.")
    from app.services.pbp_season_stats import get_team_pbp_pitching_stats

    try:
        return await get_team_pbp_pitching_stats(
            session,
            season=season,
            team_code=current_user.team_code,
            as_of_date=as_of_date,
            name=name,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/data-status")
async def get_my_team_data_status(
    current_user: CurrentUser,
    session: SessionDep,
):
    """인증된 사용자가 서비스가 사용하는 KBO 데이터의 출처/상태를 확인한다."""
    return {
        "team_code": current_user.team_code,
        "scope": "TEAM_ACCOUNT_DATA_OPERATIONS",
        "data": await get_latest_dataset_statuses(session),
    }


@router.post("/pitcher-matchups")
async def get_pitcher_matchups(
    request: LineupMatchupRequest,
    current_user: CurrentUser,
    session: SessionDep,
):
    """선택 경기에서 관측한 상대 타자와 후보 투수의 과거 직접 맞대결을 조회한다."""
    if request.as_of_date.year != request.season:
        raise HTTPException(status_code=422, detail="기준일과 시즌 연도가 일치해야 합니다.")
    if request.as_of_date > datetime.now(ZoneInfo("Asia/Seoul")).date():
        raise HTTPException(status_code=422, detail="기준일은 미래일 수 없습니다.")
    from app.services.kbo_matchups import analyze_lineup_matchups

    try:
        return await analyze_lineup_matchups(
            session,
            team_code=current_user.team_code,
            opponent_team_code=request.opponent_team_code,
            pitcher_ids=request.pitcher_ids,
            batter_ids=request.batter_ids,
            season=request.season,
            as_of_date=request.as_of_date,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/matchup-games")
async def get_matchup_games(
    current_user: CurrentUser,
    session: SessionDep,
    game_date: date = Query(),
    season: int = Query(default=2026, ge=1982, le=2100),
):
    """날짜에 소속 구단이 치른 경기와 해당 경기에서 관측된 상대 타자를 조회한다."""
    if game_date.year != season:
        raise HTTPException(status_code=422, detail="기준일과 시즌 연도가 일치해야 합니다.")
    if game_date > datetime.now(ZoneInfo("Asia/Seoul")).date():
        raise HTTPException(status_code=422, detail="기준일은 미래일 수 없습니다.")
    from app.services.kbo_matchups import get_matchup_games_for_date

    try:
        return await get_matchup_games_for_date(
            session,
            team_code=current_user.team_code,
            season=season,
            game_date=game_date,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/matchup-batters")
async def get_matchup_batters(
    current_user: CurrentUser,
    session: SessionDep,
    opponent_team_code: str = Query(min_length=2, max_length=12),
    season: int = Query(default=2026, ge=1982, le=2100),
    as_of_date: date = Query(),
    query: str | None = Query(default=None, min_length=1, max_length=80),
):
    if as_of_date.year != season:
        raise HTTPException(status_code=422, detail="기준일과 시즌 연도가 일치해야 합니다.")
    if as_of_date > datetime.now(ZoneInfo("Asia/Seoul")).date():
        raise HTTPException(status_code=422, detail="기준일은 미래일 수 없습니다.")
    from app.services.kbo_matchups import search_opponent_batters

    try:
        return await search_opponent_batters(
            session,
            opponent_team_code=opponent_team_code,
            season=season,
            as_of_date=as_of_date,
            query=query,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
