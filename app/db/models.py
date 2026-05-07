from datetime import date, datetime
from typing import List, Optional

from db.database import Base
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(Base):
    __tablename__ = "users"

    uid: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    campus_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    royalties: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    inside: Mapped[bool] = mapped_column(Boolean, default=False)
    total_taps: Mapped[int] = mapped_column(Integer, default=0)
    semester_taps: Mapped[int] = mapped_column(Integer, default=0)

    streaks: Mapped[List["Streak"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tap_events: Mapped[List["TapEvent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def current_streak(self) -> Optional["Streak"]:
        return next((s for s in self.streaks if s.is_active), None)

    @property
    def past_streaks(self) -> List["Streak"]:
        return [s for s in self.streaks if not s.is_active]


class Streak(Base):
    __tablename__ = "streaks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_uid: Mapped[str] = mapped_column(
        ForeignKey("users.uid", ondelete="CASCADE"), nullable=False
    )
    semester: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streak_start: Mapped[date] = mapped_column(Date, nullable=False)
    last_tap_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_tap_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    streak_points: Mapped[int] = mapped_column(Integer, default=0)
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="streaks")


class MQTTClient(Base):
    __tablename__ = "mqtt_clients"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    direction: Mapped[bool] = mapped_column(Boolean)
    capabilities: Mapped[Optional[list]] = mapped_column(JSONB, default=list)

    tap_events: Mapped[List["TapEvent"]] = relationship(back_populates="mqtt_client")


class TapEvent(Base):
    __tablename__ = "tap_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_uid: Mapped[str] = mapped_column(
        ForeignKey("users.uid", ondelete="CASCADE"), nullable=False
    )
    mqtt_reader_uid: Mapped[Optional[str]] = mapped_column(
        ForeignKey("mqtt_clients.id"), nullable=True
    )
    direction: Mapped[bool] = mapped_column(Boolean)
    tapped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="tap_events")
    mqtt_client: Mapped[Optional["MQTTClient"]] = relationship(
        back_populates="tap_events"
    )
