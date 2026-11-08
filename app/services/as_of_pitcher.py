"""기준일 이전 경기별 기록으로 투수 누적 지표를 재계산한다."""
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo import KboGame
from app.models.kbo_pitcher_appearance import KboPitcherAppearance
from app.services.team_codes import normalize_official_team_code


IDENTITY_SOURCES = {"OFFICIAL_VERIFIED", "TEAM_NAME_UNIQUE"}


def aggregate_as_of_appearances(
    rows: list[dict[str, Any]],
    *,
    team_code: str,
    season: int,
    as_of_date: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """조회된 원천 행을 선수별 누적으로 묶고 불완전한 식별/기록은 보류한다."""
    counts_by_game_name = Counter(
        (row["game_pk"], row["pitcher_name"]) for row in rows
    )
    ambiguous_names = {
        name
        for (_, name), count in counts_by_game_name.items()
        if count > 1
    }
    unidentified_names = {
        row["pitcher_name"] for row in rows if row["pitcher_id"] is None
    }

    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    withheld: list[dict[str, Any]] = []
    withheld_names: set[str] = set()
    for row in rows:
        if row["pitcher_id"] is None:
            name = row["pitcher_name"]
            if name not in withheld_names:
                withheld.append({
                    "pitcher_id": None,
                    "pitcher_name": name,
                    "reason": "공식 선수 ID와 연결되지 않은 기록이 있어 누적 성적을 확정할 수 없습니다.",
                })
                withheld_names.add(name)
            continue
        by_id[str(row["pitcher_id"])].append(row)

    pitchers: list[dict[str, Any]] = []
    for pitcher_id, appearances in by_id.items():
        names = {row["pitcher_name"] for row in appearances}
        sources = {row["pitcher_id_source"] for row in appearances}
        name = sorted(names)[0]
        reason = None

        if len(names) != 1 or len(sources) != 1 or None in sources:
            reason = "기준일 이전 기록의 선수 이름 또는 ID 연결 근거가 일관되지 않습니다."
        elif next(iter(sources)) not in IDENTITY_SOURCES:
            reason = "허용된 선수 ID 연결 근거를 확인할 수 없습니다."
        elif name in ambiguous_names or name in unidentified_names:
            reason = "같은 구단의 동명이인 또는 미식별 기록과 분리할 수 없습니다."
        elif any(
            row["batters_faced"] is None
            or row["strikeouts"] is None
            or row["walks"] is None
            or row["batters_faced"] < 0
            or row["strikeouts"] < 0
            or row["walks"] < 0
            or row["strikeouts"] + row["walks"] > row["batters_faced"]
            for row in appearances
        ):
            reason = "기준일 이전 등판 기록에 누락되거나 유효하지 않은 BF/SO/BB 값이 있습니다."

        if reason:
            withheld.append({
                "pitcher_id": pitcher_id,
                "pitcher_name": name,
                "reason": reason,
            })
            continue

        batters_faced = sum(row["batters_faced"] for row in appearances)
        strikeouts = sum(row["strikeouts"] for row in appearances)
        walks = sum(row["walks"] for row in appearances)
        if batters_faced == 0:
            withheld.append({
                "pitcher_id": pitcher_id,
                "pitcher_name": name,
                "reason": "기준일 이전 상대 타자 수가 0명이라 비율 지표를 계산할 수 없습니다.",
            })
            continue
        source = next(iter(sources))
        pitchers.append({
            "pitcher_id": pitcher_id,
            "pitcher_name": name,
            "team_code": team_code,
            "season": season,
            "as_of_date": as_of_date.isoformat(),
            "data_through_date": max(row["game_date"] for row in appearances).isoformat(),
            "games": len({row["game_pk"] for row in appearances}),
            "batters_faced": batters_faced,
            "strikeouts": strikeouts,
            "walks": walks,
            "k_pct": round(100 * strikeouts / batters_faced, 2),
            "bb_pct": round(100 * walks / batters_faced, 2),
            "k_minus_bb_pct": round(100 * (strikeouts - walks) / batters_faced, 2),
            "identity_status": "VERIFIED" if source == "OFFICIAL_VERIFIED" else "TENTATIVE",
            "identity_source": source,
            "sample_tier": (
                "LARGER" if batters_faced >= 150
                else "LIMITED" if batters_faced >= 50
                else "VERY_SMALL"
            ),
            "stat_source": "KBO_PITCHER_APPEARANCES_AS_OF",
        })

    pitchers.sort(key=lambda row: (row["pitcher_name"], row["pitcher_id"]))
    return pitchers, withheld


async def get_pitcher_stats_as_of(
    session: AsyncSession,
    *,
    season: int,
    team_code: str,
    as_of_date: date,
) -> dict[str, Any]:
    if not 1982 <= season <= 2100:
        raise ValueError("지원하지 않는 시즌입니다.")
    if as_of_date.year != season:
        raise ValueError("기준일과 시즌 연도가 일치해야 합니다.")
    team = normalize_official_team_code(team_code)

    statement = (
        select(
            KboPitcherAppearance.game_pk,
            KboGame.game_date,
            KboPitcherAppearance.pitcher_id,
            KboPitcherAppearance.pitcher_name,
            KboPitcherAppearance.pitcher_id_source,
            KboPitcherAppearance.source_batch_id,
            KboGame.source_batch_id.label("game_source_batch_id"),
            KboPitcherAppearance.batters_faced,
            KboPitcherAppearance.strikeouts,
            KboPitcherAppearance.walks,
        )
        .join(KboGame, KboGame.game_pk == KboPitcherAppearance.game_pk)
        .where(
            KboGame.season == season,
            KboGame.season_type == "REGULAR",
            KboGame.status == "Final",
            KboGame.game_date < as_of_date,
            KboPitcherAppearance.team_code == team,
        )
        .order_by(KboGame.game_date, KboGame.game_pk, KboPitcherAppearance.appearance_order)
    )
    rows = [dict(row) for row in (await session.execute(statement)).mappings().all()]

    expected_games = set((await session.scalars(
        select(KboGame.game_pk).where(
            KboGame.season == season,
            KboGame.season_type == "REGULAR",
            KboGame.status == "Final",
            KboGame.game_date < as_of_date,
            or_(KboGame.home_team_code == team, KboGame.away_team_code == team),
        )
    )).all())
    observed_games = {row["game_pk"] for row in rows}
    missing_games = expected_games - observed_games
    pitchers, withheld = aggregate_as_of_appearances(
        rows,
        team_code=team,
        season=season,
        as_of_date=as_of_date,
    )
    coverage_status = (
        "NO_DATA" if not expected_games
        else "PARTIAL" if missing_games
        else "COMPLETE"
    )
    source_batch_ids = sorted({
        source_id
        for row in rows
        for source_id in (row["source_batch_id"], row["game_source_batch_id"])
        if source_id is not None
    })
    untracked_rows = sum(row["source_batch_id"] is None for row in rows)
    untracked_game_rows = sum(row["game_source_batch_id"] is None for row in rows)
    return {
        "team_code": team,
        "season": season,
        "season_type": "REGULAR",
        "as_of_date": as_of_date.isoformat(),
        "date_boundary": "game_date < as_of_date; all games on as_of_date are excluded",
        "coverage": {
            "status": coverage_status,
            "expected_final_games": len(expected_games),
            "games_with_appearance_data": len(observed_games & expected_games),
            "missing_games": len(missing_games),
        },
        "provenance": {
            "status": "UNTRACKED" if untracked_rows or untracked_game_rows else "TRACKED" if rows else "UNKNOWN",
            "source_batch_ids": source_batch_ids,
            "untracked_appearance_rows": untracked_rows,
            "untracked_game_rows": untracked_game_rows,
        },
        "data_through_date": max((row["game_date"] for row in rows), default=None).isoformat() if rows else None,
        "pitchers": pitchers,
        "withheld": withheld,
        "stat_source": "KBO_PITCHER_APPEARANCES_AS_OF",
        "limitations": [
            "해당 기준일 당일 경기는 더블헤더 포함 전부 제외합니다.",
            "공식 ID 연결이 불명확하거나 핵심 기록이 누락된 선수는 누적 집계에서 보류합니다.",
            "결과/표본은 과거 기록의 재현이며 승률 또는 교체 성공 확률이 아닙니다.",
        ],
    }


async def compare_pitcher_stats_as_of(
    session: AsyncSession,
    *,
    season: int,
    team_code: str,
    as_of_date: date,
    first_pitcher_id: str,
    second_pitcher_id: str,
) -> dict[str, Any]:
    if first_pitcher_id == second_pitcher_id:
        raise ValueError("서로 다른 두 투수를 선택해야 합니다.")
    result = await get_pitcher_stats_as_of(
        session,
        season=season,
        team_code=team_code,
        as_of_date=as_of_date,
    )
    by_id = {row["pitcher_id"]: row for row in result["pitchers"]}
    withheld_by_id = {row["pitcher_id"]: row for row in result["withheld"] if row["pitcher_id"]}
    requested = [first_pitcher_id, second_pitcher_id]
    missing = [
        withheld_by_id.get(pid, {
            "pitcher_id": pid,
            "reason": "기준일까지 확인된 누적 등판 기록이 없습니다.",
        })
        for pid in requested
        if pid not in by_id
    ]
    if missing or result["coverage"]["status"] != "COMPLETE":
        return {
            **result,
            "pitchers": [by_id[pid] for pid in requested if pid in by_id],
            "withheld": missing,
            "comparison_status": "WITHHELD",
            "comparison_reason": (
                "경기별 기록이 불완전하거나 후보의 누적 기록을 확정할 수 없어 비교를 보류합니다."
            ),
        }
    first, second = (by_id[pid] for pid in requested)
    difference = round(first["k_minus_bb_pct"] - second["k_minus_bb_pct"], 2)
    return {
        **result,
        "pitchers": [first, second],
        "comparison_status": "COMPARABLE",
        "k_minus_bb_pct_gap": difference,
        "higher_k_minus_bb_pitcher_id": (
            first_pitcher_id if difference > 0
            else second_pitcher_id if difference < 0
            else None
        ),
    }
