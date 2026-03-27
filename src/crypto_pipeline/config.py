from __future__ import annotations

from pydantic import BaseModel
from dotenv import load_dotenv
import os


class Settings(BaseModel):
    kafka_bootstrap: str = "localhost:9092"
    kafka_topic_trades: str = "crypto.trades.v1"
    kafka_client_id: str = "crypto-producer"
    kafka_acks: str = "all"
    kafka_topic_dlq: str = "crypto.trades.dlq.v1"
    binance_ws_url: str = "wss://stream.binance.com:9443/ws/btcusdt@trade"

    log_level: str = "INFO"

    # MinIO / S3-compatible object store
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "crypto-trades"


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        kafka_bootstrap=os.getenv("KAFKA_BOOTSTRAP", "localhost:9092"),
        kafka_topic_trades=os.getenv("KAFKA_TOPIC_TRADES", "crypto.trades.v1"),
        kafka_client_id=os.getenv("KAFKA_CLIENT_ID", "crypto-producer"),
        kafka_acks=os.getenv("KAFKA_ACKS", "all"),
        kafka_topic_dlq=os.getenv("KAFKA_TOPIC_DLQ", "crypto.trades.dlq.v1"),
        binance_ws_url=os.getenv("BINANCE_WS_URL", "wss://stream.binance.com:9443/ws/btcusdt@trade"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        minio_bucket=os.getenv("MINIO_BUCKET", "crypto-trades"),
    )
