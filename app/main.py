import asyncio
from asyncio.taskgroups import TaskGroup
import os
import time
import traceback

import aiomqtt
from db import models  # import models so Base knows about them
from db.database import Base, SessionLocal, engine
from mqtt.handlers import TOPIC_HANDLERS

MQTT_BROKER = os.environ["MQTT_BROKER"]

async def publish_time(client: aiomqtt.Client):
    while True:
        unix_time = int(time.time())
        await client.publish("event/time", payload=str(unix_time), qos=1, retain=True)
        print(f"[MQTT] Published time: {unix_time}", flush=True)
        await asyncio.sleep(60)

async def handle_messages(client: aiomqtt.Client):
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

                async with asyncio.TaskGroup() as tg:
                    tg.create_task(handle_messages(client))
                    tg.create_task(publish_time(client))

        except* aiomqtt.MqttError as e:
            print(f"[MQTT] MqttError: {e}", flush=True)
            await asyncio.sleep(3)

asyncio.run(main())
