import asyncio
import os
import traceback

import aiomqtt
from db import models  # import models so Base knows about them
from db.database import Base, SessionLocal, engine
from mqtt.handlers import TOPIC_HANDLERS

MQTT_BROKER = os.environ["MQTT_BROKER"]


async def main():
    # Create all tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[DB] Tables created", flush=True)

    print("[MQTT] Starting...", flush=True)
    while True:
        try:
            print(f"[MQTT] Connecting to {MQTT_BROKER}...", flush=True)
            async with aiomqtt.Client(MQTT_BROKER) as client:
                await client.subscribe("event/#")
                print("[MQTT] Subscribed, listening...", flush=True)
                async for message in client.messages:
                    topic_str = str(message.topic)
                    payload = message.payload.decode()
                    print(f"[MQTT] Received: {topic_str} -> {payload}", flush=True)

                    handler = TOPIC_HANDLERS.get(topic_str)
                    if not handler:
                        print(f"[MQTT] No handler for topic: {topic_str}", flush=True)
                        continue

                    async with SessionLocal() as db:
                        await handler(client, payload, db)

        except aiomqtt.MqttError as e:
            print(f"[MQTT] MqttError: {e}", flush=True)
            await asyncio.sleep(3)
        except Exception as e:
            print(f"[MQTT] Unexpected error: {traceback.format_exc()}", flush=True)
            await asyncio.sleep(3)


asyncio.run(main())
