from datetime import date
from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class KboPitchingAppearance(Base):
    __tablename__ = "kbo_pitching_appearances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    team_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    # 원본에 안정적인 선수 ID가 없어 이름은 임시 식별자다.
    pitcher_name: Mapped[str] = mapped_column(String(120), nullable=False)
    strikeouts: Mapped[int] = mapped_column(Integer, nullable=False)
    walks: Mapped[int] = mapped_column(Integer, nullable=False)
    batters_faced: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outs_recorded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        UniqueConstraint("season", "game_date", "team_code", "pitcher_name", name="uq_pitcher_daily_identity"),
    )
