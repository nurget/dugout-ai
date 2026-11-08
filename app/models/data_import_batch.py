from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DataImportBatch(Base):
    """감사/재현을 위한 원천 데이터 적재 스냅샷 메타데이터."""

    __tablename__ = "data_import_batches"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    dataset: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    freshness: Mapped[str] = mapped_column(String(20), nullable=False)
    season: Mapped[int | None] = mapped_column(Integer)
    season_type: Mapped[str | None] = mapped_column(String(20))
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
