from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KboGameLineup(Base):
    """KBO 경기 기록지에서 확인한 타순 및 교체 출전 기록."""

    __tablename__ = "kbo_game_lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[str] = mapped_column(ForeignKey("kbo_games.game_pk"), index=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    team_code: Mapped[str] = mapped_column(String(12), index=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    player_name: Mapped[str] = mapped_column(String(120))
    batting_order: Mapped[int] = mapped_column(Integer)
    is_starter: Mapped[bool] = mapped_column(Boolean)
    position: Mapped[str | None] = mapped_column(String(40))
    raw_fields: Mapped[dict] = mapped_column(JSON)
    source_url: Mapped[str] = mapped_column(String(500))
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("data_import_batches.id"), index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("game_pk", "team_code", "player_id", name="uq_kbo_game_lineup_player"),
    )


class KboGameBoxscore(Base):
    """경기 기록지의 타자·투수 원문 필드를 함께 보존한다."""

    __tablename__ = "kbo_game_boxscores"

    game_pk: Mapped[str] = mapped_column(ForeignKey("kbo_games.game_pk"), primary_key=True)
    raw_payload: Mapped[dict] = mapped_column(JSON)
    source_url: Mapped[str] = mapped_column(String(500))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
