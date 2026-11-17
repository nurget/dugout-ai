from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KboPlayerRecord(Base):
    """원문 필드와 함께 저장하는 KBO 시즌 선수 기록."""

    __tablename__ = "kbo_player_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    season_type: Mapped[str] = mapped_column(String(16), nullable=False, default="REGULAR")
    category: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    player_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    player_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    team_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(300), nullable=False)
    raw_fields: Mapped[dict] = mapped_column(JSON, nullable=False)
    profile: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_urls: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("data_import_batches.id"), index=True
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "season", "season_type", "category", "player_id", "team_code",
            name="uq_kbo_player_record_scope",
        ),
    )
