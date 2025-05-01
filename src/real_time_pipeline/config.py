"""Configuration management for the real-time pipeline."""

import os
from dotenv import load_dotenv

load_dotenv()  # automatically picks up `.env`

class Settings:
    MTA_FEED_URL   = os.getenv("MTA_FEED_URL")
    POLL_INTERVAL  = int(os.getenv("POLL_INTERVAL", "15"))
    KAFKA_BROKER   = os.getenv("KAFKA_BROKER")
    KAFKA_TOPIC    = os.getenv("KAFKA_TOPIC", "vehicle_positions")

    @classmethod
    def validate(cls):
        missing = [k for k,v in cls.__dict__.items()
                   if k.isupper() and (v is None or v=="")]
        if missing:
            raise RuntimeError(f"Missing env vars: {', '.join(missing)}")

settings = Settings