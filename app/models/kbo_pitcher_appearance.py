
from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KboPitcherAppearance(Base):
    """KBO 공식 박스스코어의 경기별 투수 등판 기록."""

    __tablename__ = "kbo_pitcher_appearances"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    game_pk: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    team_code: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        index=True,
    )

    # 같은 경기, 같은 팀에 동명이인이 있어도
    # 박스스코어의 등장 순서로 행을 구분한다.
    appearance_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 공식 선수 ID가 확인되기 전에는 추정값을 저장하지 않는다.
    pitcher_id: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    pitcher_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    batters_faced: Mapped[int | None] = mapped_column(Integer)
    pitches: Mapped[int | None] = mapped_column(Integer)
    walks: Mapped[int | None] = mapped_column(Integer)
    strikeouts: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint(
            "game_pk",
            "team_code",
            "appearance_order",
            name="uq_kbo_pitcher_appearance_order",
        ),
    )