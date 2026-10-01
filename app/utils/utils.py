from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from db.models import User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio.session import AsyncSession


@dataclass
class RfidClientTapPayload:
    pico_id: str
    tag_id: str


def parse_tap_response(payload: list[str]) -> RfidClientTapPayload | None:
    if len(payload) != 2:
        print(f"[parse] Expected 2 fields, got {len(payload)}")
        return None
    return RfidClientTapPayload(
        pico_id=payload[0],
        tag_id=payload[1],
    )


@dataclass
class RfidServerTapPayload:
    pico_id: str
    tag_id: str
    user_pref_name: str
    points: int
    streak_score: int
    leaderboard_placement: int
    special_message: str

    def __str__(self) -> str:
        # now = datetime.now(ZoneInfo("America/New_York"))
        return f"{self.pico_id}|{self.tag_id}|{self.user_pref_name}|{self.points}|{self.streak_score}|{self.leaderboard_placement}|{self.special_message}"
        # return (
        #     f"{self.pico_id}|{self.tag_id}|"
        #     f"[{now.strftime('%A %b %d, %Y | %I:%M %p %Z')}]|"
        #     f"{self.user_pref_name}|{self.points}|{self.streak_score}|{self.special_message}"
        # )


async def get_leaderboard_placement(
    db: AsyncSession,
    user_uid: str,
) -> int:
    rank = func.dense_rank().over(order_by=User.semester_taps.desc()).label("rank")

    ranked_users = (
        select(
            User.uid,
            rank,
        )
        .where(User.semester_taps > 0)
        .subquery()
    )

    result = await db.execute(
        select(ranked_users.c.rank).where(ranked_users.c.uid == user_uid)
    )

    return result.scalar_one_or_none() or 0
