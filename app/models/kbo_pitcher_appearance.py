from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class KboPitcherAppearance(Base):
    __tablename__ = "kbo_pitcher_appearances"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_pk: Mapped[str] = mapped_column(String(32), index=True)
    pitcher_name: Mapped[str] = mapped_column(String(120))
    team_code: Mapped[str] = mapped_column(String(12), index=True)
    batters_faced: Mapped[int | None] = mapped_column(Integer)
    pitches: Mapped[int | None] = mapped_column(Integer)
    walks: Mapped[int | None] = mapped_column(Integer)
    strikeouts: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("game_pk", "team_code", "pitcher_name", name="uq_kbo_pitcher_appearance"),)
