import argparse
import asyncio
from pathlib import Path
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.kbo_pitching import KboPitchingAppearance
from app.services.kbo_pitching import aggregate_pitchers, load_pitching_csv
import csv

async def main(
    path: Path,
    apply: bool,
    source: str,
    skip_unknown: bool,
):
    records, quality = load_pitching_csv(
        path,
        skip_unknown=skip_unknown,
    )

    unknown_players = quality["unknown_players"]

    if unknown_players:
        report_path = path.with_name(
            f"{path.stem}_unknown_report.csv"
        )

        with report_path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as fp:
            writer = csv.DictWriter(
                fp,
                fieldnames=["line", "name", "date", "team"],
            )
            writer.writeheader()
            writer.writerows(unknown_players)

        print(f"미확인 선수 제외: {len(unknown_players)}건")
        print(f"검증 보고서: {report_path}")
        
    summary = aggregate_pitchers(records)
    calculable = sum(row["k_minus_bb_pct"] is not None for row in summary)
    print(f"경기별 기록: {len(records)}건, 선수별 집계: {len(summary)}명")
    print(f"중복: {quality['duplicates']}건, PA 누락: {quality['missing_pa']}건")
    print(f"K-BB% 계산 가능: {calculable}/{len(summary)}명")
    if not apply:
        print("검증만 진행했습니다. DB를 변경하려면 --apply를 사용하세요.")
        return
    if not source:
        raise ValueError("실제 적재 시 --source 출처를 지정해야 합니다")
    async with AsyncSessionLocal() as db:
        for row in records:
            old = (await db.execute(select(KboPitchingAppearance).where(
                KboPitchingAppearance.season == row.season,
                KboPitchingAppearance.game_date == row.game_date,
                KboPitchingAppearance.team_code == row.team_code,
                KboPitchingAppearance.pitcher_name == row.pitcher_name,
            ))).scalar_one_or_none()
            if old is None:
                db.add(KboPitchingAppearance(
                    season=row.season, game_date=row.game_date, team_code=row.team_code,
                    pitcher_name=row.pitcher_name, strikeouts=row.strikeouts, walks=row.walks,
                    batters_faced=row.batters_faced, outs_recorded=row.outs_recorded, source=source,
                ))
            else:
                old.strikeouts = row.strikeouts
                old.walks = row.walks
                old.batters_faced = row.batters_faced
                old.outs_recorded = row.outs_recorded
                old.source = source
        await db.commit()
    print(f"저장 완료: {len(records)}건")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--source", default="")
    parser.add_argument(
        "--skip-unknown",
        action="store_true",
        help="미확인 선수 기록을 제외하고 별도 보고서로 저장",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            args.path,
            args.apply,
            args.source,
            args.skip_unknown,
        )
    )
