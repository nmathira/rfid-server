from datetime import date, datetime
from typing import List, Optional

from db.database import Base
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(Base):
    __tablename__ = "users"

    uid: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    royalties: Mapped[Optional[List[str]]] = mapped_column(String(255), nullable=True)
    campus_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    inside: Mapped[bool] = mapped_column(Boolean, default=False)
    total_taps: Mapped[int] = mapped_column(Integer, default=0)

    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    streak_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_tap_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_tap_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    past_streaks: Mapped[Optional[list]] = mapped_column(JSONB, default=list)

    tap_events: Mapped[List["TapEvent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    year: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class TapEvent(Base):
    __tablename__ = "tap_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_uid: Mapped[str] = mapped_column(ForeignKey("users.uid"))
    mqtt_client_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("mqtt_clients.id"), nullable=True
    )
    tapped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="tap_events")
    mqtt_client: Mapped[Optional["MQTTClient"]] = relationship(
        back_populates="tap_events"
    )
    direction: Mapped[bool] = mapped_column(Boolean)


class MQTTClient(Base):
    __tablename__ = "mqtt_clients"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    direction: Mapped[bool] = mapped_column(Boolean)  # "in" or "out"

    tap_events: Mapped[List["TapEvent"]] = relationship(back_populates="mqtt_client")
