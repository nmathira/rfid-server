import random
import string
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiomqtt
from db.models import MQTTClient, Streak, TapEvent, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.utils import RfidServerTapPayload, parse_tap_response

EASTERN = ZoneInfo("America/New_York")

# At streak day N+, each tap earns this many points
STREAK_MULTIPLIERS = [
    (8, 4),
    (5, 3),
    (2, 2),
]


def _random_name() -> str:
    return "-".join(random.choices(string.ascii_uppercase, k=4))


def _get_today() -> Datetime:
    """Today's date with a 3am rollover cutoff."""
    now = datetime.now(EASTERN)
    return (now - timedelta(hours=3)).date()


def _get_multiplier(streak_days: int) -> int:
    """Return the point multiplier based on current streak length."""
    for threshold, multiplier in STREAK_MULTIPLIERS:
        if streak_days >= threshold:
            return multiplier
    return 1


def _get_current_semester() -> int:
    """Return the current semester as an offset from the initial semester."""
    # Adjust this to your actual start date and cadence
    INITIAL_SEMESTER_START = datetime(2026, 1, 13).date()
    SEMESTER_LENGTH_DAYS = 120
    days_elapsed = (_get_today() - INITIAL_SEMESTER_START).days
    return max(0, days_elapsed // SEMESTER_LENGTH_DAYS)


# ─── Streak Logic ────────────────────────────────────────────────────────────


async def _get_active_streak(db: AsyncSession, user_uid: str) -> Streak | None:
    result = await db.execute(
        select(Streak).where(Streak.user_uid == user_uid, Streak.is_active == True)
    )
    return result.scalar_one_or_none()


async def _start_new_streak(db: AsyncSession, user: User, now: datetime) -> Streak:
    today = _get_today()
    streak = Streak(
        user_uid=user.uid,
        semester=_get_current_semester(),
        streak_start=today,
        last_tap_at=now,
        last_tap_day=today,
        streak_days=1,
        streak_points=1,
        is_active=True,
    )
    db.add(streak)
    return streak


async def _end_streak(streak: Streak) -> None:
    streak.is_active = False


async def _process_streak(db: AsyncSession, user: User, now: datetime) -> Streak:
    """Handle all streak logic for a tap. Returns the active streak."""
    today = _get_today()
    streak = await _get_active_streak(db, user.uid)

    if streak is None:
        return await _start_new_streak(db, user, now)

    # Same day — no change
    if streak.last_tap_day == today:
        return streak

    # Consecutive day — extend
    if (today - streak.last_tap_day).days == 1:
        streak.streak_days += 1
        streak.streak_points += _get_multiplier(streak.streak_days)
        streak.last_tap_at = now
        streak.last_tap_day = today
        return streak

    # Streak broken — archive and start fresh
    await _end_streak(streak)
    return await _start_new_streak(db, user, now)


# ─── Tap Response Builder ────────────────────────────────────────────────────


def _build_response(
    pico_id: str,
    user: User,
    streak: Streak | None,
    message: str = "0",
) -> RfidServerTapPayload:
    return RfidServerTapPayload(
        pico_id=pico_id,
        tag_id=user.uid,
        user_pref_name=user.name,
        points=user.total_taps,
        streak_score=streak.streak_days if streak else 0,
        special_message=message,
    )


# ─── Handlers ────────────────────────────────────────────────────────────────


async def handle_register(
    client: aiomqtt.Client, payload: str, db: AsyncSession
) -> None:
    payload_arr = payload.strip().split("|")
    device_id = payload_arr[0]
    direction = bool(payload_arr[1])

    print(f"[REGISTER] Device ID: {device_id}")

    existing = await db.get(MQTTClient, device_id)
    if existing:
        await client.publish("event/register_response", "device_ID already in use")
        return

    db.add(MQTTClient(id=device_id, direction=direction))
    await db.commit()
    await client.publish("event/register_response", "success")


async def handle_tap(client: aiomqtt.Client, payload: str, db: AsyncSession) -> None:
    parsed = parse_tap_response(payload.strip().split("|"))
    if not parsed:
        return

    device = await db.get(MQTTClient, parsed.pico_id)
    if device is None:
        return

    user = await db.get(User, parsed.tag_id)
    now = datetime.now(EASTERN)

    # ─── Tap OUT ─────────────────────────────────────────────────────────
    if not device.direction:
        if user:
            user.inside = False
            await db.commit()
        return

    # ─── Tap IN ──────────────────────────────────────────────────────────

    # New user — register and start their first streak
    if not user:
        user = User(
            uid=parsed.tag_id,
            name=_random_name(),
            inside=True,
            total_taps=1,
            semester_taps=1,
        )
        db.add(user)
        streak = await _start_new_streak(db, user, now)

        db.add(
            TapEvent(
                user_uid=user.uid,
                mqtt_reader_uid=parsed.pico_id,
                direction=True,
                tapped_at=now,
            )
        )
        await db.commit()

        response = _build_response(
            parsed.pico_id,
            user,
            streak,
            message="Register your keyfob with Niranjan when he is available.",
        )
        await client.publish("event/tapResponse", str(response))
        return

    # Existing user — process streak
    streak = await _process_streak(db, user, now)
    today = _get_today()

    # Same day duplicate — just acknowledge
    if user.last_tap_day == today:
        # last_tap_day already matches, streak wasn't modified (same-day path)
        # But _process_streak already handled the same-day case, so we check
        # if taps were already counted today
        pass
    else:
        # New day tap — increment counters
        user.total_taps += 1
        user.semester_taps += 1

    # Always update state
    user.inside = True

    db.add(
        TapEvent(
            user_uid=user.uid,
            mqtt_reader_uid=parsed.pico_id,
            direction=True,
            tapped_at=now,
        )
    )
    await db.commit()

    response = _build_response(parsed.pico_id, user, streak)
    await client.publish("event/tapResponse", str(response))


TOPIC_HANDLERS = {
    "event/register": handle_register,
    "event/tapIn": handle_tap,
}
