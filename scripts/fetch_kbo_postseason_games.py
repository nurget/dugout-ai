"""KBO 공식 일정 API에서 2026 포스트시즌 경기 목록을 저장한다."""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

URL = "https://www.koreabaseball.com/ws/Main.asmx/GetKboGameList"
TEAM = {"HT": "KIA", "KT": "KT", "LG": "LG", "NC": "NC", "SK": "SSG", "SS": "SAM", "OB": "DOO", "LT": "LOT", "HH": "HAN", "WO": "KIW"}

def fetch(day: date) -> list[dict]:
    request = Request(URL, data=urlencode({"leId": 1, "srId": "3,4,5,6", "date": day.strftime("%Y%m%d")}).encode(), headers={"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest", "Referer": "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx"})
    return json.loads(urlopen(request, timeout=30).read())["game"]

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-10-14")
    parser.add_argument("--end", default="2026-11-30")
    parser.add_argument("--output", type=Path, default=Path("data/private/kbo_2026_postseason.json"))
    args = parser.parse_args(); start = date.fromisoformat(args.start); end = date.fromisoformat(args.end)
    games: dict[str, dict] = {}
    while start <= end:
        for item in fetch(start):
            game_id = item["G_ID"]
            score = lambda value: int(value) if str(value).isdigit() else None
            games[game_id] = {"gamePk": game_id, "officialDate": f"{item['G_DT'][:4]}-{item['G_DT'][4:6]}-{item['G_DT'][6:]}", "status": {"detailedState": "Final" if item.get("GAME_RESULT_CK") == 1 else "Scheduled"}, "isPostseason": True, "series_id": item["SR_ID"], "teams": {"away": {"team": {"abbrev": TEAM.get(item["AWAY_ID"], item["AWAY_ID"]), "name": item["AWAY_NM"]}, "score": score(item.get("T_SCORE_CN"))}, "home": {"team": {"abbrev": TEAM.get(item["HOME_ID"], item["HOME_ID"]), "name": item["HOME_NM"]}, "score": score(item.get("B_SCORE_CN"))}}}
        start += timedelta(days=1)
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(list(games.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"포스트시즌 일정 {len(games)}경기: {args.output}")

if __name__ == "__main__": main()
