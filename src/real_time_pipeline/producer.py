"""Kafka producer for publishing GTFS-Realtime data."""

import logging
import json
from confluent_kafka import Producer as KafkaProducer

logger = logging.getLogger(__name__)

class Producer:
    def __init__(self, broker: str, topic: str):
        self.topic = topic
        self.producer = KafkaProducer({"bootstrap.servers": broker})
        logger.info(f"Kafka producer configured for {broker} → topic '{topic}'")

    def publish_batch(self, batch):
        for rec in batch:
            # you may want to pick a better key
            key = rec.get("id", "")
            self.producer.produce(self.topic, key=key, value=self._serialize(rec))
        self.producer.flush()
        logger.info(f"Published {len(batch)} messages to '{self.topic}'")

    @staticmethod
    def _serialize(obj: dict) -> bytes:
        return json.dumps(obj).encode("utf-8")