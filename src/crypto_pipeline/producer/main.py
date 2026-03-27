from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from importlib.resources import files
from uuid import uuid4

import orjson
import structlog
import websockets
from jsonschema import validate

from crypto_pipeline.config import load_settings
from crypto_pipeline.logging import setup_logging
from crypto_pipeline.producer.publisher import KafkaPublisher

log = structlog.get_logger()

SCHEMA_VERSION = 1
SOURCE = "binance_ws"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_trade_schema() -> dict:
    # Use importlib.resources so this works both from source and when installed
    schema_file = files("crypto_pipeline.schemas").joinpath("trade_v1.json")
    return json.loads(schema_file.read_text(encoding="utf-8"))


def transform_binance_trade(msg: dict) -> dict:
    # Binance trade payload fields (example):
    # e: 'trade', E: eventTime, s: symbol, t: tradeId, p: price(str), q: qty(str), T: tradeTime, m: buyerIsMaker
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid4()),
        "source": SOURCE,
        "ingested_at": utc_now_iso(),
        "symbol": msg["s"],
        "trade_id": int(msg["t"]),
        "trade_ts": int(msg["T"]),
        "price": float(msg["p"]),
        "qty": float(msg["q"]),
        "is_buyer_maker": bool(msg["m"]),
    }


async def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    schema = load_trade_schema()
    publisher = KafkaPublisher(
        bootstrap=settings.kafka_bootstrap,
        client_id=settings.kafka_client_id,
        acks=settings.kafka_acks,
    )

    sent = 0
    log.info("producer_starting", ws_url=settings.binance_ws_url, topic=settings.kafka_topic_trades)

    while True:
        try:
            async with websockets.connect(settings.binance_ws_url, ping_interval=20, ping_timeout=20) as ws:
                log.info("ws_connected")
                async for raw in ws:
                    msg = orjson.loads(raw)
                    event = transform_binance_trade(msg)

                    # validate (fast enough for single stream; can be toggled later)
                    validate(instance=event, schema=schema)

                    publisher.publish(
                        topic=settings.kafka_topic_trades,
                        key=event["symbol"],
                        value=orjson.dumps(event),
                    )
                    sent += 1
                    if sent % 200 == 0:
                        log.info("producer_progress", sent=sent, last_trade_id=event["trade_id"])
        except Exception as e:
            log.error("producer_error", error=str(e))
            await asyncio.sleep(3)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()