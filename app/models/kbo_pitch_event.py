from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KboPitchEvent(Base):
    """PBP 원본의 투구 1개. raw_payload에 원천 필드를 보존한다."""

    __tablename__ = "kbo_pitch_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    game_pk: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    game_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    inning: Mapped[int | None] = mapped_column(Integer)
    inning_topbot: Mapped[str | None] = mapped_column(String(8))
    at_bat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pitch_number: Mapped[int] = mapped_column(Integer, nullable=False)
    home_team_code: Mapped[str | None] = mapped_column(String(12))
    away_team_code: Mapped[str | None] = mapped_column(String(12))
    batter_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    batter_name: Mapped[str | None] = mapped_column(String(120))
    pitcher_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    pitcher_name: Mapped[str | None] = mapped_column(String(120))
    pitch_result: Mapped[str | None] = mapped_column(String(32))
    pitch_type: Mapped[str | None] = mapped_column(String(16))
    pitch_name: Mapped[str | None] = mapped_column(String(80))
    release_speed_kmh: Mapped[float | None] = mapped_column(Float)
    events: Mapped[str | None] = mapped_column(String(40))
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("data_import_batches.id"), nullable=True, index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "game_pk", "at_bat_number", "pitch_number",
            name="uq_kbo_pitch_event_game_ab_pitch",
        ),
    )
