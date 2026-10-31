from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KboOfficialSeasonPitcher(Base):
    """KBO 기록실의 1군 정규시즌 기본 투수 기록.

    공식 기본 기록에는 BF가 없으므로 PBP 집계 테이블과 분리한다.
    """

    __tablename__ = "kbo_official_season_pitchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    season_type: Mapped[str] = mapped_column(String(16), nullable=False, default="REGULAR")
    pitcher_id: Mapped[str] = mapped_column(String(32), nullable=False)
    pitcher_name: Mapped[str] = mapped_column(String(120), nullable=False)
    team_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    games: Mapped[int] = mapped_column(Integer, nullable=False)
    batters_faced: Mapped[int | None] = mapped_column(Integer)
    strikeouts: Mapped[int] = mapped_column(Integer, nullable=False)
    walks: Mapped[int] = mapped_column(Integer, nullable=False)
    k_pct: Mapped[float | None] = mapped_column(nullable=True)
    bb_pct: Mapped[float | None] = mapped_column(nullable=True)
    k_minus_bb_pct: Mapped[float | None] = mapped_column(nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("season", "season_type", "pitcher_id", "team_code", name="uq_kbo_official_season_pitcher"),
    )
