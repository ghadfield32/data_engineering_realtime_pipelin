#!/usr/bin/env python3
"""Main entry point for the real-time pipeline."""

import time
import logging

from .config import settings
from .gtfs import fetch_vehicle_positions
from .producer import Producer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def run():
    settings.validate()
    prod = Producer(settings.KAFKA_BROKER, settings.KAFKA_TOPIC)
    logger.info(f"Starting stream every {settings.POLL_INTERVAL}s from {settings.MTA_FEED_URL}")

    while True:
        try:
            batch = fetch_vehicle_positions(settings.MTA_FEED_URL)
            if batch:
                prod.publish_batch(batch)
            else:
                logger.info("No GTFS entities this cycle")
        except Exception as e:
            logger.error("Stream error: %s", e, exc_info=True)

        time.sleep(settings.POLL_INTERVAL)

if __name__ == "__main__":
    run()