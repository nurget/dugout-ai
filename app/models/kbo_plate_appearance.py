from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KboPlateAppearance(Base):
    """완료된 단일 투수 상대 타석. 원천 투구 데이터에서 보수적으로 정리한다."""

    __tablename__ = "kbo_plate_appearances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    game_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    at_bat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    inning: Mapped[int | None] = mapped_column(Integer)
    inning_topbot: Mapped[str | None] = mapped_column(String(8))
    batting_team_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    fielding_team_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    batter_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    batter_name: Mapped[str] = mapped_column(String(120), nullable=False)
    batter_stand: Mapped[str | None] = mapped_column(String(1))
    pitcher_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    pitcher_name: Mapped[str] = mapped_column(String(120), nullable=False)
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    source_batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("data_import_batches.id"), nullable=True, index=True
    )

    __table_args__ = (
        UniqueConstraint("game_pk", "at_bat_number", name="uq_kbo_plate_appearance_game_ab"),
    )
