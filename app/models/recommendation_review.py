from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RecommendationReview(Base):
    """Coach review labels tied to the exact recommendation and data snapshot."""

    __tablename__ = "recommendation_reviews"

    review_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    acceptable_candidate_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    recommendation_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    data_snapshot_ids: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "reviewer_user_id",
            name="uq_recommendation_review_run_reviewer",
        ),
    )
