import random
import string
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiomqtt
from db.models import MQTTClient, TapEvent, User
from sqlalchemy.ext.asyncio import AsyncSession
from utils.utils import (
    RfidServerTapPayload,
    parse_tap_response,
)

EASTERN = ZoneInfo("America/New_York")


def _random_name() -> str:
    return "-".join(random.choices(string.ascii_uppercase, k=4))


async def handle_register(
    client: aiomqtt.Client, payload: str, db: AsyncSession
) -> None:
    payload_arr = payload.strip().split("|")
    print(f"[REGISTER] Device ID: {payload_arr[0]}")

    existing = await db.get(MQTTClient, payload_arr[0])
    if existing:
        await client.publish("event/register_response", "device_ID already in use")
        return

    new_client = MQTTClient(id=payload_arr[0], direction=bool(payload_arr[1]))
    db.add(new_client)
    await db.commit()
    await client.publish("event/register_response", "success")


async def handle_tapIn(client: aiomqtt.Client, payload, db: AsyncSession) -> None:
    payload = payload.strip().split("|")
    payload_parsed = parse_tap_response(payload)
    if payload_parsed:
        user = await db.get(User, payload_parsed.tag_id)
        device_id = await db.get(MQTTClient, payload_parsed.pico_id)
        now = datetime.now(EASTERN)
        today = (now - timedelta(hours=3)).date()  # 3am cutoff

        if device_id is not None and device_id.direction:
            if not user:
                # First time we've seen this RFID uid — create them with a random name
                user = User(
                    uid=payload_parsed.tag_id,
                    name=_random_name(),
                    inside=True,
                    total_taps=1,
                    streak_start=today,
                    last_tap_at=now,
                    last_tap_day=today,
                    past_streaks=[],
                )
                db.add(user)
                db.add(
                    TapEvent(
                        user_uid=payload_parsed.tag_id,
                        mqtt_client_id=payload_parsed.pico_id,
                        tapped_at=now,
                    )
                )
                await db.commit()

                server_data = RfidServerTapPayload(
                    pico_id=payload_parsed.pico_id,
                    tag_id=payload.parsed.tag_id,
                    user_pref_name=user.name,
                    points=user.total_taps,
                    streak_score=user.current_streak,
                    special_message="Register your keyfob with Niranjan when he is available.",
                )

                await client.publish("event/tapResponse", str(server_data))
                return

            # disgard same day tap
            server_data = RfidServerTapPayload(
                pico_id=payload_parsed.pico_id,
                tag_id=payload.parsed.tag_id,
                user_pref_name=user.name,
                points=user.total_taps,
                streak_score=user.current_streak,
                special_message="0",
            )
            if user.last_tap_day == today:
                await client.publish("event/tapResponse", str(server_data))
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

            db.add(
                TapEvent(
                    user_uid=payload_parsed.tag_id,
                    mqtt_client_id=payload_parsed.pico_id,
                    tapped_at=now,
                )
            )
            await db.commit()
            server_data = RfidServerTapPayload(
                pico_id=payload_parsed.pico_id,
                tag_id=payload.parsed.tag_id,
                user_pref_name=user.name,
                points=user.total_taps,
                streak_score=user.current_streak,
                special_message="0",
            )

            await client.publish("event/tapResponse", str(server_data))

        if device_id is not None and not device_id.direction and user is not None:
            user.inside = False


TOPIC_HANDLERS = {
    "event/register": handle_register,
    "event/tapIn": handle_tapIn,
}
