
import argparse
import asyncio
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

import app.models
from app.db.session import AsyncSessionLocal
from app.models.kbo import KboGame
from app.models.kbo_pitcher_appearance import KboPitcherAppearance
from scripts.import_kbo_regular_appearances import (
    fetch_box_score,
    normalize_team,
    parse_game_pitchers,
)


FIELDS = (
    "team_code",
    "appearance_order",
    "pitcher_name",
    "batters_faced",
    "pitches",
    "walks",
    "strikeouts",
)


def signature(row: dict) -> tuple:
    """원본과 DB를 같은 필드 순서로 비교한다."""
    return tuple(row[field] for field in FIELDS)


async def audit_game(db, game: dict) -> dict:
    game_pk = game["game_pk"]

    try:
        response = await asyncio.to_thread(
            fetch_box_score,
            game_pk,
            game["season"],
        )

        original = parse_game_pitchers(
            response,
            normalize_team(game["away_team_code"]),
            normalize_team(game["home_team_code"]),
        )

        result = await db.scalars(
            select(KboPitcherAppearance)
            .where(KboPitcherAppearance.game_pk == game_pk)
            .order_by(
                KboPitcherAppearance.team_code,
                KboPitcherAppearance.appearance_order,
            )
        )

        stored = [
            {field: getattr(row, field) for field in FIELDS}
            for row in result.all()
        ]

        original_signatures = Counter(
            signature(row) for row in original
        )
        stored_signatures = Counter(
            signature(row) for row in stored
        )

        missing = original_signatures - stored_signatures
        extra = stored_signatures - original_signatures

        if not missing and not extra:
            return {
                "game_pk": game_pk,
                "status": "MATCH",
                "original_count": len(original),
                "stored_count": len(stored),
            }

        def unpack(counter):
            return [
                dict(zip(FIELDS, values))
                for values, count in counter.items()
                for _ in range(count)
            ]

        return {
            "game_pk": game_pk,
            "status": "MISMATCH",
            "original_count": len(original),
            "stored_count": len(stored),
            "missing_from_db": unpack(missing),
            "extra_in_db": unpack(extra),
        }

    except Exception as error:
        await db.rollback()

        return {
            "game_pk": game_pk,
            "status": "ERROR",
            "error_type": type(error).__name__,
            "error": str(error),
        }


async def main():
    parser = argparse.ArgumentParser(
        description="KBO 정규시즌 투수 기록 원본 대조"
    )

    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument(
        "--output",
        default="data/private/pitcher_appearance_audit_2026.json",
    )

    args = parser.parse_args()

    if args.limit < 1 or args.delay < 0:
        parser.error("limit은 1 이상, delay는 0 이상이어야 합니다.")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                KboGame.game_pk,
                KboGame.season,
                KboGame.game_date,
                KboGame.away_team_code,
                KboGame.home_team_code,
            )
            .where(
                KboGame.season == args.season,
                KboGame.season_type == "REGULAR",
                KboGame.status == "Final",
            )
            .order_by(
                KboGame.game_date,
                KboGame.game_pk,
            )
        )

        # ORM 객체가 아닌 값으로 저장하므로
        # DB rollback 이후에도 경기 정보를 안전하게 사용한다.
        games = [dict(row) for row in result.mappings().all()]

        if not args.all:
            games = games[:args.limit]

        print(f"검증 대상: {len(games)}경기")

        results = []

        for index, game in enumerate(games, start=1):
            checked = await audit_game(db, game)
            results.append(checked)

            print(
                f"[{index}/{len(games)}]",
                checked["status"],
                checked["game_pk"],
                f"원본={checked.get('original_count', '-')}",
                f"DB={checked.get('stored_count', '-')}",
            )

            if index < len(games):
                await asyncio.sleep(args.delay)

    counts = Counter(row["status"] for row in results)

    report = {
        "season": args.season,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total_checked": len(results),
        "summary": {
            "matched": counts["MATCH"],
            "mismatched": counts["MISMATCH"],
            "errors": counts["ERROR"],
        },
        "results": results,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n=== 검증 결과 ===")
    print("일치:", counts["MATCH"])
    print("불일치:", counts["MISMATCH"])
    print("API/파싱 오류:", counts["ERROR"])
    print("보고서:", output)
    print("DB 변경 없음")

    if counts["MISMATCH"] or counts["ERROR"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())