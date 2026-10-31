
import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


TEAM_CODES = {
    "KIA": "KIA",
    "KIA TIGERS": "KIA",
    "SAMSUNG": "SS",
    "SAMSUNG LIONS": "SS",
    "SS": "SS",
    "LG": "LG",
    "KT": "KT",
    "SSG": "SSG",
    "NC": "NC",
    "DOOSAN": "OB",
    "OB": "OB",
    "LOTTE": "LT",
    "LT": "LT",
    "HANWHA": "HH",
    "HH": "HH",
    "KIWOOM": "WO",
    "WO": "WO",
}


class PitchingDataError(ValueError):
    pass


@dataclass(frozen=True)
class DailyPitching:
    season: int
    game_date: date
    team_code: str
    pitcher_name: str
    strikeouts: int
    walks: int
    batters_faced: int | None
    outs_recorded: int | None

    @property
    def identity(self):
        return (
            self.season,
            self.game_date,
            self.team_code,
            self.pitcher_name,
        )


def optional_int(raw, field, line):
    if raw is None or str(raw).strip() == "":
        return None

    try:
        value = int(float(str(raw)))

        if value < 0 or float(raw) != value:
            raise ValueError

        return value

    except (ValueError, TypeError):
        raise PitchingDataError(
            f"{line}행: {field}는 0 이상의 정수여야 합니다"
        )


def load_pitching_csv(
    path: Path,
    season: int = 2026,
    skip_unknown: bool = False,
):
    if not path.is_file():
        raise PitchingDataError(f"CSV가 없습니다: {path}")

    records: dict[tuple, DailyPitching] = {}

    duplicates = 0
    merged_pa = 0
    unknown_players = []

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as fp:
        reader = csv.DictReader(fp)

        required = {
            "Name",
            "Date",
            "Tm",
            "SO",
            "BB",
            "Season",
            "PitOuts",
            "PA",
        }

        columns = set(reader.fieldnames or [])
        missing_columns = required - columns

        if missing_columns:
            raise PitchingDataError(
                f"필수 컬럼 누락: {sorted(missing_columns)}"
            )

        for line, row in enumerate(reader, start=2):
            if not any(row.values()):
                continue

            # 경기 날짜와 시즌이 일치하는지 확인한다.
            try:
                row_season = int(row["Season"])
                game_date = datetime.strptime(
                    row["Date"].strip(),
                    "%m/%d/%Y",
                ).date()

            except (ValueError, AttributeError, TypeError) as exc:
                raise PitchingDataError(
                    f"{line}행: 시즌/날짜 오류"
                ) from exc

            if row_season != season:
                raise PitchingDataError(
                    f"{line}행: 요청 시즌 {season}과 "
                    f"실제 시즌 {row_season} 불일치"
                )

            if game_date.year != season:
                raise PitchingDataError(
                    f"{line}행: 경기 날짜가 시즌과 다릅니다"
                )

            # 원본 CSV에서 혼용되는 구단명을 동일한 코드로 변환한다.
            team_name = (row["Tm"] or "").strip().upper()
            team = TEAM_CODES.get(team_name)

            if not team:
                raise PitchingDataError(
                    f"{line}행: 알 수 없는 팀 {row['Tm']!r}"
                )

            name = (row["Name"] or "").strip()

            # 식별할 수 없는 선수는 명시적으로 허용한 경우에만 제외한다.
            if not name or name.lower().startswith("unknown_"):
                if not skip_unknown:
                    raise PitchingDataError(
                        f"{line}행: 선수 식별 불가 ({name})"
                    )

                unknown_players.append({
                    "line": line,
                    "name": name,
                    "date": row["Date"],
                    "team": row["Tm"],
                })
                continue

            so = optional_int(row["SO"], "SO", line)
            bb = optional_int(row["BB"], "BB", line)
            pa = optional_int(row["PA"], "PA", line)
            outs = optional_int(
                row["PitOuts"],
                "PitOuts",
                line,
            )

            if so is None or bb is None:
                raise PitchingDataError(
                    f"{line}행: SO/BB 누락"
                )

            if pa is not None and pa < so + bb:
                raise PitchingDataError(
                    f"{line}행: PA가 SO+BB보다 작습니다"
                )

            record = DailyPitching(
                season=season,
                game_date=game_date,
                team_code=team,
                pitcher_name=name,
                strikeouts=so,
                walks=bb,
                batters_faced=pa,
                outs_recorded=outs,
            )

            identity = record.identity

            if identity not in records:
                records[identity] = record
                continue

            existing = records[identity]
            duplicates += 1

            # 모든 기록이 같은 경우에는 한 건만 유지한다.
            if existing == record:
                continue

            # PA 이외의 값이 모두 일치하는 경우에만
            # 결측 PA를 보완할 수 있는 중복으로 판단한다.
            same_except_pa = (
                existing.season == record.season
                and existing.game_date == record.game_date
                and existing.team_code == record.team_code
                and existing.pitcher_name == record.pitcher_name
                and existing.strikeouts == record.strikeouts
                and existing.walks == record.walks
                and existing.outs_recorded == record.outs_recorded
            )

            if not same_except_pa:
                raise PitchingDataError(
                    f"{line}행: 서로 다른 값이 포함된 중복 기록: "
                    f"{identity}"
                )

            existing_pa = existing.batters_faced
            incoming_pa = record.batters_faced

            # 기존 기록에 PA가 없고 새 기록에 있으면 교체한다.
            if existing_pa is None and incoming_pa is not None:
                records[identity] = record
                merged_pa += 1
                continue

            # 기존 기록에 PA가 있으면 PA가 없는 행은 무시한다.
            if existing_pa is not None and incoming_pa is None:
                merged_pa += 1
                continue

            # 두 행 모두 PA가 없으면 기록 자체는 동일하다고 본다.
            if existing_pa is None and incoming_pa is None:
                continue

            # PA가 둘 다 존재하지만 값이 다르면 임의로 선택하지 않는다.
            if existing_pa != incoming_pa:
                raise PitchingDataError(
                    f"{line}행: PA 값이 충돌하는 중복 기록: "
                    f"{identity} "
                    f"(기존={existing_pa}, 신규={incoming_pa})"
                )

    if not records:
        raise PitchingDataError(
            "유효한 경기별 투수 기록이 없습니다"
        )

    result = list(records.values())

    # 중복 제거와 PA 보완이 끝난 뒤 실제 누락 건수를 계산한다.
    missing_pa = sum(
        record.batters_faced is None
        for record in result
    )

    return result, {
        "duplicates": duplicates,
        "merged_pa": merged_pa,
        "missing_pa": missing_pa,
        "unknown_players": unknown_players,
        "skipped_unknown": len(unknown_players),
    }


def aggregate_pitchers(records: list[DailyPitching]):
    groups = defaultdict(list)

    for record in records:
        groups[
            (record.team_code, record.pitcher_name)
        ].append(record)

    results = []

    for (team, name), group in sorted(groups.items()):
        strikeouts = sum(
            record.strikeouts
            for record in group
        )

        walks = sum(
            record.walks
            for record in group
        )

        # 상대 타자 수가 누락된 경기가 하나라도 있으면
        # 시즌 전체 K-BB%를 임의로 추정하지 않는다.
        complete = all(
            record.batters_faced is not None
            for record in group
        )

        batters_faced = (
            sum(record.batters_faced for record in group)
            if complete
            else None
        )

        k_minus_bb_pct = (
            round(
                (strikeouts - walks) / batters_faced * 100,
                2,
            )
            if batters_faced
            else None
        )

        results.append({
            "team_code": team,
            "pitcher_name": name,
            "games": len(group),
            "strikeouts": strikeouts,
            "walks": walks,
            "batters_faced": batters_faced,
            "k_minus_bb_pct": k_minus_bb_pct,
            "complete_bf": complete,
        })

    return results