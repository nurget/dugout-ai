
import argparse
import asyncio
import json
import re
import time
from datetime import date
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import select, delete
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

        if len(values) <= 13:
            raise ValueError(
                f"투수 기록 컬럼 부족: {team_code} {name}"
            )

        pitchers.append({
            "appearance_order": len(pitchers) + 1,
            "pitcher_id": None,
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
    # 양 팀 데이터가 모두 파싱된 뒤 호출한다.
    # 게임 전체의 기록을 하나의 트랜잭션으로 갱신한다.

    if not rows:
        raise ValueError("저장할 투수 기록이 없습니다.")

    teams = {row["team_code"] for row in rows}

    if len(teams) != 2:
        raise ValueError("양 팀의 투수 기록이 필요합니다.")

    keys = [
        (row["team_code"], row["appearance_order"])
        for row in rows
    ]

    if len(keys) != len(set(keys)):
        raise ValueError("경기 내 등장 순서가 중복되었습니다.")

    try:
        # 공식 박스스코어의 전체 기록으로 해당 경기 내용을
        # 교체한다. 이름 기준의 이전 Upsert 잔재를 남기지 않는다.
        #
        # 주의: 이 테이블의 행 ID를 참조하는 FK가 없는 현재 구조를 전제로 한다.
        await db.execute(
            delete(KboPitcherAppearance).where(
                KboPitcherAppearance.game_pk == game_pk
            )
        )

        db.add_all([
            KboPitcherAppearance(
                game_pk=game_pk,
                **row,
            )
            for row in rows
        ])

        await db.commit()

    except Exception:
        await db.rollback()
        raise

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
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="종료 경기 중 투수 등판 기록이 없는 경기만 수집",
    )

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
        
        
        # 먼저 DB 객체를 일반 데이터로 변환한다.
        # 실패 후 rollback이 발생해도 경기 정보는 유지된다.
        games = [
            {
                "game_pk": game.game_pk,
                "game_date": game.game_date,
                "away_team_code": game.away_team_code,
                "home_team_code": game.home_team_code,
                "status": game.status,
            }
            for game in games
        ]

        if args.missing_only:
            result = await db.scalars(
                select(KboPitcherAppearance.game_pk).distinct()
            )
            collected_game_ids = set(result.all())

            # 완료된 경기 중 등판 기록이 전혀 없는 경기만 선택한다.
            # 기존 데이터에 손대지 않기 위한 필터다.
            games = [
                game
                for game in games
                if game["status"] == "Final"
                and game["game_pk"] not in collected_game_ids
            ]

        # 필터링한 다음 limit을 적용해야 빠진 경기를 놓치지 않는다.
        games = games[:args.limit]

        print(f"수집 대상 경기: {len(games)}건")
        print(
            "실행 모드:",
            "DB 저장" if args.apply else "검증 전용",
        )

        succeeded = 0
        failed = []

        for game in games:
            game_pk = game["game_pk"]

            try:
                response = await asyncio.to_thread(
                    fetch_box_score,
                    game_pk,
                    args.season,
                )

                rows = parse_game_pitchers(
                    response,
                    normalize_team(game["away_team_code"]),
                    normalize_team(game["home_team_code"]),
                )

                print(
                    f"[OK] {game['game_date']} {game_pk}: "
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