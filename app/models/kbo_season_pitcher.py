from sqlalchemy import Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KboSeasonPitcher(Base):
    __tablename__ = "kbo_season_pitchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    pitcher_id: Mapped[str] = mapped_column(String(80), nullable=False)
    pitcher_name: Mapped[str] = mapped_column(String(120), nullable=False)
    team_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    games: Mapped[int] = mapped_column(Integer, nullable=False)
    batters_faced: Mapped[int] = mapped_column(Integer, nullable=False)
    strikeouts: Mapped[int] = mapped_column(Integer, nullable=False)
    walks: Mapped[int] = mapped_column(Integer, nullable=False)
    k_pct: Mapped[float] = mapped_column(Float, nullable=False)
    bb_pct: Mapped[float] = mapped_column(Float, nullable=False)
    k_minus_bb_pct: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(300), nullable=False)

    __table_args__ = (
        UniqueConstraint("season", "pitcher_id", "team_code", name="uq_kbo_season_pitcher"),
    )
