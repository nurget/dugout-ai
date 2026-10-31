"""PBP 집계 CSV를 검증하고 투수별 시즌 성적을 비교한다."""
import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo_season_pitcher import KboSeasonPitcher

FIELDS = {
    "pitcher_id", "pitcher_name", "team_code", "games", "batters_faced",
    "strikeouts", "walks", "k_pct", "bb_pct", "k_minus_bb_pct",
}


class SeasonPitcherDataError(ValueError):
    pass


def parse_season_pitchers(path: Path) -> list[dict]:
    if not path.is_file():
        raise SeasonPitcherDataError(f"CSV 파일이 없습니다: {path}")
    parsed: list[dict] = []
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = FIELDS - set(reader.fieldnames or ())
        if missing:
            raise SeasonPitcherDataError(f"필수 컬럼 누락: {sorted(missing)}")
        for line_no, row in enumerate(reader, start=2):
            try:
                pid = (row["pitcher_id"] or "").strip()
                name = (row["pitcher_name"] or "").strip()
                team = (row["team_code"] or "").strip().upper()
                if not pid or not name or not team:
                    raise ValueError("선수/팀 식별자가 비어 있습니다")
                key = (pid, team)
                if key in seen:
                    raise ValueError("같은 팀·선수의 중복 행")
                games, bf, so, bb = [int(row[k]) for k in ("games", "batters_faced", "strikeouts", "walks")]
                if games < 1 or bf < 1 or min(so, bb) < 0 or so + bb > bf:
                    raise ValueError("경기 수 또는 BF/SO/BB 수치가 유효하지 않습니다")
                k, b, kb = (round(100 * so / bf, 2), round(100 * bb / bf, 2), round(100 * (so - bb) / bf, 2))
                # CSV에 담긴 계산값이 원시 집계와 다르면 잘못된 데이터로 간주한다.
                for col, expected in (("k_pct", k), ("bb_pct", b), ("k_minus_bb_pct", kb)):
                    if abs(float(row[col]) - expected) > 0.011:
                        raise ValueError(f"{col} 검증 실패")
                parsed.append(dict(pitcher_id=pid, pitcher_name=name, team_code=team,
                                   games=games, batters_faced=bf, strikeouts=so, walks=bb,
                                   k_pct=k, bb_pct=b, k_minus_bb_pct=kb))
                seen.add(key)
            except (TypeError, ValueError, KeyError) as exc:
                raise SeasonPitcherDataError(f"{line_no}행: {exc}") from exc
    if not parsed:
        raise SeasonPitcherDataError("유효한 투수 기록이 없습니다")
    return parsed


async def import_season_pitchers(db: AsyncSession, rows: list[dict], *, season: int, source: str) -> int:
    # 동일한 시즌·투수·팀 조합을 갱신하여 반복 적재 시 중복을 방지한다.
    for row in rows:
        result = await db.execute(select(KboSeasonPitcher).where(
            KboSeasonPitcher.season == season,
            KboSeasonPitcher.pitcher_id == row["pitcher_id"],
            KboSeasonPitcher.team_code == row["team_code"],
        ))
        obj = result.scalar_one_or_none()
        if obj is None:
            obj = KboSeasonPitcher(season=season, source=source, **row)
            db.add(obj)
        else:
            for key, value in row.items():
                setattr(obj, key, value)
            obj.source = source
    await db.commit()
    return len(rows)


def present_pitcher(p: KboSeasonPitcher) -> dict:
    return {"pitcher_id": p.pitcher_id, "pitcher_name": p.pitcher_name,
            "team_code": p.team_code, "season": p.season, "games": p.games,
            "batters_faced": p.batters_faced, "strikeouts": p.strikeouts,
            "walks": p.walks, "k_pct": p.k_pct, "bb_pct": p.bb_pct,
            "k_minus_bb_pct": p.k_minus_bb_pct, "source": p.source}


async def get_pitchers(db: AsyncSession, *, season: int = 2026, team: str | None = None) -> list[dict]:
    query = select(KboSeasonPitcher).where(KboSeasonPitcher.season == season)
    if team:
        query = query.where(KboSeasonPitcher.team_code == team.upper())
    result = await db.execute(query.order_by(KboSeasonPitcher.team_code, KboSeasonPitcher.pitcher_name))
    return [present_pitcher(row) for row in result.scalars()]


async def compare_pitchers(db: AsyncSession, *, season: int, first_pitcher_id: str,
                           second_pitcher_id: str, team: str | None = None) -> dict:
    ids = [first_pitcher_id, second_pitcher_id]
    if ids[0] == ids[1]:
        raise ValueError("서로 다른 두 투수를 선택해야 합니다")
    query = select(KboSeasonPitcher).where(
        KboSeasonPitcher.season == season,
        KboSeasonPitcher.pitcher_id.in_(ids),
    )
    if team:
        query = query.where(KboSeasonPitcher.team_code == team.upper())
    result = await db.execute(query)
    rows = list(result.scalars())
    matched = {p.pitcher_id: p for p in rows}
    if any(pid not in matched for pid in ids) or len(rows) != 2:
        raise ValueError("두 투수의 동일 시즌 기록을 찾을 수 없거나 팀 정보가 모호합니다")
    first, second = (matched[pid] for pid in ids)
    return {
        "season": season,
        "pitchers": [present_pitcher(first), present_pitcher(second)],
        "k_minus_bb_pct_gap": round(first.k_minus_bb_pct - second.k_minus_bb_pct, 2),
        "higher_k_minus_bb_pitcher_id": (
            first.pitcher_id if first.k_minus_bb_pct > second.k_minus_bb_pct
            else second.pitcher_id if first.k_minus_bb_pct < second.k_minus_bb_pct else None
        ),
        "limitations": [
            "2026년 7월 26일까지의 부분 PBP 데이터를 사용한 집계입니다.",
            "일부 미완료 타석과 타석 도중 투수 교체 기록은 제외되었습니다.",
            "K-BB%는 투수의 시즌 기록 비교 지표이며, 교체 시 승률이나 기대 실점을 뜻하지 않습니다.",
            "최근 등판·휴식·부상·상대 타선 정보는 포함하지 않습니다.",
        ],
    }
