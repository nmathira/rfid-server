import random
import string
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiomqtt
from db.models import MQTTClient, TapEvent, User
from sqlalchemy.ext.asyncio import AsyncSession

EASTERN = ZoneInfo("America/New_York")


def _random_name() -> str:
    return "-".join(random.choices(string.ascii_uppercase, k=4))


async def handle_register(
    client: aiomqtt.Client, payload: str, db: AsyncSession
) -> None:
    payload_arr = payload.strip().split("|")
    print(f"[REGISTER] Device ID: {payload_arr[0]}", flush=True)

    existing = await db.get(MQTTClient, payload_arr[0])
    if existing:
        await client.publish("event/register_response", "device_ID already in use")
        return

    new_client = MQTTClient(id=payload_arr[0], direction=payload_arr[1])
    db.add(new_client)
    await db.commit()
    await client.publish("event/register_response", "success")


async def handle_tapIn(client: aiomqtt.Client, payload: str, db: AsyncSession) -> None:
    user_id = payload.strip().split("|")
    user = await db.get(User, user_id[1])

    now = datetime.now(EASTERN)
    today = (now - timedelta(hours=3)).date()  # 3am cutoff

    if not user:
        # First time we've seen this RFID uid — create them with a random name
<<<<<<< HEAD
        # user = User(
        #     uid=user_id[1],
        #     name=_random_name(),
        #     inside=True,
        #     total_taps=1,
        #     streak_start=today,
        #     last_tap_at=now,
        #     last_tap_day=today,
        #     past_streaks=[],
        # )
        # db.add(user)
        # db.add(TapEvent(user_uid=user_id[1], mqtt_client_id=user_id[0], tapped_at=now))
        # await db.commit()
=======
        user = User(
            uid=user_id[1],
            name=_random_name(),
            inside=True,
            total_taps=1,
            streak_start=today,
            last_tap_at=now,
            last_tap_day=today,
            past_streaks=[],
        )
        db.add(user)
        db.add(TapEvent(user_uid=user_id, mqtt_client_id=user_id[0], tapped_at=now))
        await db.commit()
>>>>>>> parent of 3fdf6fd (fixed handler)

        await client.publish(
            "event/tapResponse",
            payload
            + "|"
            + "Register your keyfob with Niranjan at his earliest convinience",
        )
        return

    # disgard same day tap
    if user.last_tap_day == today:
        await client.publish("event/tapResponse", payload + "|" + user.name)
        return

    # --- Streak logic ---
    if user.last_tap_day is None:
        # Shouldn't happen since we set it on creation, but just in case
        user.streak_start = today
        user.current_streak = 1
    elif (today - user.last_tap_day).days == 1:
        # Consecutive day — extend streak
        user.current_streak += 1
    else:
        # Streak broken — archive it
        past = user.past_streaks or []
        past.append(
            {
                "streak_start": user.streak_start.isoformat()
                if user.streak_start
                else today.isoformat(),
                "streak_length": user.current_streak,
            }
        )
        user.past_streaks = past
        user.streak_start = today
        user.current_streak = 1

    user.total_taps += 1
    user.last_tap_at = now
    user.last_tap_day = today
    user.inside = True

    db.add(TapEvent(user_uid=user_id, mqtt_client_id=user_id[0], tapped_at=now))
    await db.commit()

    await client.publish("event/tapResponse", payload + "|" + user.name)


TOPIC_HANDLERS = {
    "event/register": handle_register,
    "event/tapIn": handle_tapIn,
}
