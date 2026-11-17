from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KboTeamRecord(Base):
    """KBO 기록실의 구단별 원문 기록과 수집 시각."""

    __tablename__ = "kbo_team_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    season_type: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    team_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    raw_fields: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_url: Mapped[str] = mapped_column(String(300), nullable=False)
    source_urls: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("data_import_batches.id"))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("season", "season_type", "category", "team_code", name="uq_kbo_team_record_scope"),
    )
