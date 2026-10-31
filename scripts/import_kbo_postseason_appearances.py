import asyncio, json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import app.models
from sqlalchemy import select
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models.kbo_pitcher_appearance import KboPitcherAppearance

URL="https://www.koreabaseball.com/ws/Schedule.asmx/GetBoxScoreScroll"
INTERNAL={"KIA":"HT","LG":"LG","DOO":"OB","SAM":"SS"}
async def main():
 games=json.load(open("data/private/kbo_2026_postseason.json"))
 async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
 async with AsyncSessionLocal() as db:
  saved=0
  for g in games:
   sr={4:4,3:3,5:5,6:6}.get(g.get("series_id"),0)
   req=Request(URL,data=urlencode({"leId":1,"srId":sr,"seasonId":2026,"gameId":g["gamePk"]}).encode(),headers={"User-Agent":"Mozilla/5.0","X-Requested-With":"XMLHttpRequest","Referer":"https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx"})
   box=json.loads(urlopen(req,timeout=30).read())
   if not box.get("arrPitcher"):
    continue
   for side, table in zip((g["teams"]["away"],g["teams"]["home"]),box["arrPitcher"]):
    team=INTERNAL.get(side["team"]["abbrev"],side["team"]["abbrev"])
    for row in json.loads(table["table"])["rows"]:
     v=[c["Text"] for c in row["row"]]; name=v[0]
     obj=await db.scalar(select(KboPitcherAppearance).where(KboPitcherAppearance.game_pk==g["gamePk"],KboPitcherAppearance.team_code==team,KboPitcherAppearance.pitcher_name==name))
     data=dict(batters_faced=int(v[7]) if v[7].isdigit() else None,pitches=int(v[8]) if v[8].isdigit() else None,walks=int(v[12]) if v[12].isdigit() else None,strikeouts=int(v[13]) if v[13].isdigit() else None)
     if obj is None: db.add(KboPitcherAppearance(game_pk=g["gamePk"],team_code=team,pitcher_name=name,**data))
     else:
      for k,x in data.items(): setattr(obj,k,x)
     saved+=1
  await db.commit(); print(f"저장 완료: {saved} 등판")
asyncio.run(main())
