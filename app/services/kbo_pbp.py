"""KBO 투구별 데이터를 타석 단위로 축약한다.

BF는 투구 수가 아니라 완료된 타석 수다. 투수 교체로 한 타석에
두 투수가 등장하거나 타석 결과가 없는 경우는 추정하지 않고 분리한다.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class PitcherLine:
    pitcher_id: str
    pitcher_name: str
    team_code: str
    games: int
    batters_faced: int
    strikeouts: int
    walks: int
    k_pct: float
    bb_pct: float
    k_minus_bb_pct: float


def aggregate_pbp(rows: Iterable[dict[str, Any]], season: int = 2026) -> tuple[list[PitcherLine], dict[str, int]]:
    appearances: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    unique_pitches: dict[tuple[str, int, int], dict[str, Any]] = {}
    quality = {"rows_seen": 0, "rows_in_season": 0, "duplicate_pitches": 0,
               "conflicting_pitches": 0, "incomplete_pa": 0,
               "mixed_pitcher_pa": 0, "invalid_pa": 0, "counted_pa": 0}

    for row in rows:
        quality["rows_seen"] += 1
        date_value = str(row.get("game_date") or "")
        if not date_value.startswith(f"{season}-"):
            continue
        quality["rows_in_season"] += 1
        try:
            game = str(row["game_pk"])
            ab = int(row["at_bat_number"])
            pitch_no = int(row["pitch_number"])
        except (KeyError, TypeError, ValueError):
            quality["invalid_pa"] += 1
            continue
        if not game or ab < 1 or pitch_no < 0:
            quality["invalid_pa"] += 1
            continue
        key = (game, ab, pitch_no)
        if key in unique_pitches:
            if unique_pitches[key] == row:
                quality["duplicate_pitches"] += 1
            else:
                # 같은 투구 식별자의 상충 기록은 타석 전체를 제외한다.
                quality["conflicting_pitches"] += 1
                appearances[(game, ab)].append({"__conflict__": True})
            continue
        unique_pitches[key] = row
        appearances[(game, ab)].append(row)

    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for (game, ab), pitches in appearances.items():
        if any(p.get("__conflict__") for p in pitches):
            quality["invalid_pa"] += 1
            continue
        pitchers = {str(p.get("pitcher") or "") for p in pitches}
        if len(pitchers) != 1 or "" in pitchers:
            quality["mixed_pitcher_pa"] += 1
            continue
        events = {str(p["events"]) for p in pitches if p.get("events") is not None}
        if len(events) != 1:
            # 원본 안내상 events가 비어 있는 미완료 타석도 존재한다.
            quality["incomplete_pa"] += 1
            continue
        event = events.pop()
        last = max(pitches, key=lambda p: int(p["pitch_number"]))
        side = last.get("inning_topbot")
        team = last.get("home_team") if side == "top" else last.get("away_team") if side == "bot" else None
        if not team:
            quality["invalid_pa"] += 1
            continue
        pitcher_id = next(iter(pitchers))
        name = str(last.get("pitcher_name") or pitcher_id)
        group_key = (pitcher_id, name, str(team))
        entry = grouped.setdefault(group_key, {"games": set(), "bf": 0, "so": 0, "bb": 0})
        entry["games"].add(game)
        entry["bf"] += 1
        entry["so"] += int(event == "strikeout")
        entry["bb"] += int(event == "walk")
        quality["counted_pa"] += 1

    lines = []
    for (pitcher_id, name, team), entry in sorted(grouped.items()):
        bf = entry["bf"]
        lines.append(PitcherLine(
            pitcher_id=pitcher_id, pitcher_name=name, team_code=team,
            games=len(entry["games"]), batters_faced=bf,
            strikeouts=entry["so"], walks=entry["bb"],
            k_pct=round(100 * entry["so"] / bf, 2),
            bb_pct=round(100 * entry["bb"] / bf, 2),
            k_minus_bb_pct=round(100 * (entry["so"] - entry["bb"]) / bf, 2),
        ))
    return lines, quality
