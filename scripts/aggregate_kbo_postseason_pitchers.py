import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.kbo import KboGame
from app.models.kbo_pitcher_appearance import KboPitcherAppearance
from app.services.kbo_official_pitching import import_official_pitchers

async def main():
 async with AsyncSessionLocal() as db:
  rows=(await db.execute(select(KboPitcherAppearance,KboGame).join(KboGame,KboGame.game_pk==KboPitcherAppearance.game_pk).where(KboGame.season==2026,KboGame.season_type=='POSTSEASON'))).all(); groups={}
  for a,_ in rows:
   key=(a.team_code,a.pitcher_name); x=groups.setdefault(key,dict(season_type='POSTSEASON',pitcher_id=f'post-{a.team_code}-{a.pitcher_name}',pitcher_name=a.pitcher_name,team_code=a.team_code,games=0,batters_faced=0,walks=0,strikeouts=0)); x['games']+=1; x['batters_faced']+=a.batters_faced or 0; x['walks']+=a.walks or 0; x['strikeouts']+=a.strikeouts or 0
  data=[]
  for x in groups.values():
   bf=x['batters_faced']; x['batters_faced']=bf or None; x['k_pct']=round(100*x['strikeouts']/bf,2) if bf else None; x['bb_pct']=round(100*x['walks']/bf,2) if bf else None; x['k_minus_bb_pct']=round(100*(x['strikeouts']-x['walks'])/bf,2) if bf else None; data.append(x)
  print('포스트시즌 투수:',len(data)); print('저장:',await import_official_pitchers(db,data,season=2026))
asyncio.run(main())
