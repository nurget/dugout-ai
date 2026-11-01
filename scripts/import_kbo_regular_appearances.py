
import argparse
import asyncio
import json
import re
import time
from datetime import date
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import app.models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.kbo import KboGame
from app.models.kbo_pitcher_appearance import KboPitcherAppearance


URL = "https://www.koreabaseball.com/ws/Schedule.asmx/GetBoxScoreScroll"

TEAM_ALIASES = {
    "KIA": "HT",
    "DOO": "OB",
    "SAM": "SS",
    "SSG": "SK",
    "HAN": "HH",
    "LOT": "LT",
    "KIW": "WO",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx",
    "Content-Type": "application/x-www-form-urlencoded",
}


def normalize_team(code: str) -> str:
    return TEAM_ALIASES.get(code.upper(), code.upper())


def parse_number(value):
    text = str(value).replace(",", "").strip()

    if not re.fullmatch(r"\d+", text):
        raise ValueError(f"숫자 기록을 읽을 수 없습니다: {value!r}")

    return int(text)


def fetch_box_score(game_pk: str, season: int):
    payload = urlencode({
        "leId": 1,
        "srId": 0,
        "seasonId": season,
        "gameId": game_pk,
    }).encode()

    request = Request(
        URL,
        data=payload,
        headers=HEADERS,
    )

    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_pitcher_table(table: dict, team_code: str):
    raw_table = table.get("table")

    if not raw_table:
        raise ValueError("투수 기록 테이블이 비어 있습니다.")

    parsed = (
        json.loads(raw_table)
        if isinstance(raw_table, str)
        else raw_table
    )

    rows = parsed.get("rows", [])
    pitchers = []
    seen_names = set()

    if not rows:
        raise ValueError("투수 기록 행이 없습니다.")

    for row in rows:
        cells = row.get("row", [])
        values = [
            str(cell.get("Text", "") or "").strip()
            for cell in cells
        ]

        if not values:
            continue

        name = values[0]

        if not name or name.upper() in ("TOTAL", "합계"):
            continue

        # 기존 포스트시즌 수집기가 검증한 열 위치:
        # TBF=7, NP=8, BB=12, SO=13
        if len(values) <= 13:
            raise ValueError(
                f"투수 기록 컬럼 부족: {team_code} {name}"
            )

        if name in seen_names:
            raise ValueError(
                f"같은 팀 내 투수 이름 중복: {team_code} {name}"
            )

        seen_names.add(name)

        pitchers.append({
            "pitcher_name": name,
            "team_code": team_code,
            "batters_faced": parse_number(values[7]),
            "pitches": parse_number(values[8]),
            "walks": parse_number(values[12]),
            "strikeouts": parse_number(values[13]),
        })

    if not pitchers:
        raise ValueError(f"투수 기록 없음: {team_code}")

    return pitchers


def parse_game_pitchers(
    response: dict,
    away_code: str,
    home_code: str,
):
    tables = response.get("arrPitcher")

    if not isinstance(tables, list) or len(tables) != 2:
        raise ValueError("양 팀의 박스스코어가 없습니다.")

    away = parse_pitcher_table(tables[0], away_code)
    home = parse_pitcher_table(tables[1], home_code)

    return away + home


async def save_appearances(
    db: AsyncSession,
    game_pk: str,
    rows: list[dict],
):
    # 한 경기의 모든 투수 기록을 같은 트랜잭션으로 저장한다.
    for row in rows:
        existing = await db.scalar(
            select(KboPitcherAppearance).where(
                KboPitcherAppearance.game_pk == game_pk,
                KboPitcherAppearance.team_code == row["team_code"],
                KboPitcherAppearance.pitcher_name == row["pitcher_name"],
            )
        )

        if existing is None:
            db.add(
                KboPitcherAppearance(
                    game_pk=game_pk,
                    **row,
                )
            )
        else:
            for key in (
                "batters_faced",
                "pitches",
                "walks",
                "strikeouts",
            ):
                setattr(existing, key, row[key])

    await db.commit()


async def get_regular_games(
    db: AsyncSession,
    season: int,
    start_date: date | None,
    end_date: date | None,
):
    statement = (
        select(KboGame)
        .where(
            KboGame.season == season,
            KboGame.season_type == "REGULAR",
        )
        .order_by(
            KboGame.game_date,
            KboGame.game_pk,
        )
    )

    if start_date is not None:
        statement = statement.where(
            KboGame.game_date >= start_date
        )

    if end_date is not None:
        statement = statement.where(
            KboGame.game_date <= end_date
        )

    return list((await db.scalars(statement)).all())


async def main():
    parser = argparse.ArgumentParser(
        description="KBO 정규시즌 경기별 투수 기록 수집"
    )

    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--from-date", type=date.fromisoformat)
    parser.add_argument("--to-date", type=date.fromisoformat)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--apply", action="store_true")

    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit은 1 이상이어야 합니다.")

    if args.delay < 0:
        parser.error("--delay는 0 이상이어야 합니다.")

    if (
        args.from_date is not None
        and args.to_date is not None
        and args.from_date > args.to_date
    ):
        parser.error("시작일이 종료일보다 늦을 수 없습니다.")

    async with AsyncSessionLocal() as db:
        games = await get_regular_games(
            db,
            season=args.season,
            start_date=args.from_date,
            end_date=args.to_date,
        )

        games = games[:args.limit]

        print(f"수집 대상 경기: {len(games)}건")
        print(
            "실행 모드:",
            "DB 저장" if args.apply else "검증 전용",
        )

        succeeded = 0
        failed = []

        for game in games:
            game_pk = game.game_pk

            try:
                response = await asyncio.to_thread(
                    fetch_box_score,
                    game_pk,
                    args.season,
                )

                rows = parse_game_pitchers(
                    response,
                    normalize_team(game.away_team_code),
                    normalize_team(game.home_team_code),
                )

                print(
                    f"[OK] {game.game_date} {game_pk}: "
                    f"{len(rows)}명"
                )

                for pitcher in rows[:4]:
                    print(
                        " ",
                        pitcher["team_code"],
                        pitcher["pitcher_name"],
                        f"NP={pitcher['pitches']}",
                        f"TBF={pitcher['batters_faced']}",
                    )

                if args.apply:
                    await save_appearances(
                        db,
                        game_pk,
                        rows,
                    )

                succeeded += 1

            except Exception as error:
                await db.rollback()
                failed.append(game_pk)

                print(
                    f"[FAIL] {game_pk}: "
                    f"{type(error).__name__}: {error}"
                )

            time.sleep(args.delay)

        print("\n=== 수집 결과 ===")
        print("성공 경기:", succeeded)
        print("실패 경기:", len(failed))

        if failed:
            print("실패 경기 ID:", ", ".join(failed))

        if not args.apply:
            print("DB 변경 없음 — 검증 전용 실행")

        if failed:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())