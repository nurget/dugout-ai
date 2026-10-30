from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)

    home_team: Mapped[str] = mapped_column(String(50))
    away_team: Mapped[str] = mapped_column(String(50))
    game_date: Mapped[date] = mapped_column(Date)

    states: Mapped[list["GameState"]] = relationship(
        back_populates="game",
    )


class GameState(Base):
    __tablename__ = "game_states"

    id: Mapped[int] = mapped_column(primary_key=True)

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id"),
        index=True,
    )

    inning: Mapped[int]
    outs: Mapped[int]
    pitch_count: Mapped[int]

    game: Mapped["Game"] = relationship(
        back_populates="states",
    )