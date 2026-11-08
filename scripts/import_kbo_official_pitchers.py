
import argparse
import asyncio
import json
import math
from pathlib import Path

from app.db.session import AsyncSessionLocal
from app.services.kbo_official_pitching import (
    fetch_official_pitchers,
    import_official_pitchers,
)
from app.services.data_catalog import record_import_batch


def load_pitchers_from_json(
    file_path: str,
    season: int,
) -> list[dict]:
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"JSON 파일이 없습니다: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("JSON 최상위 구조가 객체가 아닙니다.")

    if data.get("season") != season:
        raise ValueError(
            f"시즌 불일치: 요청={season}, "
            f"JSON={data.get('season')}"
        )

    if data.get("season_type") != "REGULAR":
        raise ValueError(
            "이 JSON Import는 REGULAR 기록만 지원합니다."
        )

    raw_rows = data.get("records")

    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("records가 없거나 비어 있습니다.")

    rows = []
    seen = set()

    for index, record in enumerate(raw_rows, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"{index}번째 기록이 객체가 아닙니다.")

        try:
            pitcher_id = str(record["player_id"]).strip()
            pitcher_name = str(record["player_name"]).strip()
            team_code = str(record["team_code"]).strip()

            games = record["games"]
            batters_faced = record["batters_faced"]
            walks = record["walks"]
            strikeouts = record["strikeouts"]

            if not all(
                type(value) is int
                for value in (games, batters_faced, walks, strikeouts)
            ):
                raise ValueError("기록 숫자는 정수여야 합니다.")

            if not pitcher_id or not pitcher_name or not team_code:
                raise ValueError("선수 ID·이름·팀은 필수입니다.")

            if games < 0 or batters_faced <= 0:
                raise ValueError("경기 수 또는 TBF가 유효하지 않습니다.")

            if not (0 <= walks <= batters_faced):
                raise ValueError("BB가 유효하지 않습니다.")

            if not (0 <= strikeouts <= batters_faced):
                raise ValueError("SO가 유효하지 않습니다.")

            key = (season, "REGULAR", pitcher_id, team_code)

            if key in seen:
                raise ValueError(f"중복 선수 기록: {key}")

            seen.add(key)

            calculated = {
                "k_pct": round(100 * strikeouts / batters_faced, 2),
                "bb_pct": round(100 * walks / batters_faced, 2),
                "k_minus_bb_pct": round(
                    100 * (strikeouts - walks) / batters_faced, 2
                ),
            }

            # JSON에 계산값이 들어 있다면 다시 계산해 비교한다.
            for field, expected in calculated.items():
                supplied = record.get(field)

                if isinstance(supplied, bool) or not isinstance(
                    supplied, (int, float)
                ):
                    raise ValueError(f"{field} 값이 숫자가 아닙니다.")

                if not math.isfinite(supplied) or not math.isclose(
                    supplied, expected, abs_tol=0.011
                ):
                    raise ValueError(
                        f"{field} 불일치: "
                        f"JSON={supplied}, 계산={expected}"
                    )

            rows.append({
                "season_type": "REGULAR",
                "pitcher_id": pitcher_id,
                "pitcher_name": pitcher_name,
                "team_code": team_code,
                "games": games,
                "batters_faced": batters_faced,
                "walks": walks,
                "strikeouts": strikeouts,
                **calculated,
            })

        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"{index}번째 선수 기록 검증 실패: {error}"
            ) from error

    print(f"JSON 검증 성공: {len(rows)}명")

    return rows


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="KBO 공식 투수 기록을 검증하고 DB에 적재합니다."
    )

    parser.add_argument(
        "--season",
        type=int,
        default=2026,
    )

    parser.add_argument(
        "--from-json",
        type=str,
        default=None,
        help="병합된 KBO 공식 기록 JSON 경로",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
    )

    parser.add_argument(
        "--include-postseason",
        action="store_true",
    )

    args = parser.parse_args()

    if args.from_json and args.include_postseason:
        parser.error(
            "--from-json과 --include-postseason은 함께 사용할 수 없습니다."
        )

    if args.from_json:
        rows = load_pitchers_from_json(
            args.from_json,
            args.season,
        )
    else:
        rows = fetch_official_pitchers(
            args.season,
            include_postseason=args.include_postseason,
        )

    print(f"공식 KBO 투수 기록: {len(rows)}명")

    if not args.apply:
        print("미리보기 모드: DB는 변경하지 않았습니다.")
        return

    async with AsyncSessionLocal() as db:
        try:
            count = await import_official_pitchers(
                db,
                rows,
                season=args.season,
            )
        except Exception as error:
            await db.rollback()
            await record_import_batch(
                db,
                dataset="kbo_official_season_pitchers",
                source_name="KBO_RECORDS_OFFICIAL",
                season=args.season,
                record_count=0,
                status="FAILED",
                error_message=f"{type(error).__name__}: {error}",
                quality_summary={"attempted_records": len(rows), "validation": "FAILED"},
            )
            await db.commit()
            raise

    print(f"DB 저장 완료: {count}명")


if __name__ == "__main__":
    asyncio.run(main())
