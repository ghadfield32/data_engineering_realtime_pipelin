#!/usr/bin/env python3

# This script is used to stream GTFS-RT data to a Kafka topic.
# It is used to stream the data to a Kafka topic for the realtime pipeline.

#location: data_engineering_realtime_pipelin\scripts\stream_gtfs.py

import os
import time
import json
import logging
import socket
import requests
from google.protobuf import json_format
from google.transit import gtfs_realtime_pb2
from confluent_kafka import Producer
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s %(levelname)s: %(message)s"
)

def delivery_report(err, msg, record, dlq_topic, producer):
    """
    Kafka delivery callback.
    If there's an error, reroute the original record + error message to the DLQ.
    """
    if err is not None:
        logging.error(
            f"Delivery failed for record {record.get('id', '<no-id>')}: {err}"
        )
        # send to dead-letter queue
        try:
            dlq_payload = {
                "failed_record": record,
                "error": str(err),
                "failed_at": int(time.time())
            }
            producer.produce(
                dlq_topic,
                key=record.get("id", ""),
                value=json.dumps(dlq_payload).encode("utf-8")
            )
            producer.flush()  # ensure it actually goes out
            logging.info(f"Sent failed record to DLQ topic '{dlq_topic}'")
        except Exception as dlq_err:
            logging.critical(f"Unable to send to DLQ: {dlq_err}")
    else:
        logging.debug(f"Message delivered to {msg.topic()} [{msg.partition()}]")

def test_kafka_connection(broker: str, timeout: float = 1.0) -> bool:
    """
    Try opening a TCP socket to the broker. 
    Returns True if CONNECT succeeds, False otherwise.
    """
    host, port_str = broker.split(":")
    port = int(port_str)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception as e:
        logging.error(f"Cannot connect to Kafka broker at {host}:{port} — {e}")
        return False

def main():
    load_dotenv('.env.engineering')
    api_url = os.getenv("MTA_FEED_URL")
    broker = os.getenv("KAFKA_BROKER")
    topic = os.getenv("KAFKA_TOPIC", "vehicle_positions")
    dlq_topic = os.getenv("DLQ_TOPIC", "vehicle_positions_dlq")
    interval = int(os.getenv("POLL_INTERVAL", "15"))
    backoff = int(os.getenv("BACKOFF_BASE", "1"))
    max_backoff = int(os.getenv("BACKOFF_MAX", "300"))

    logging.info(
        f"Environment → MTA_FEED_URL={api_url}, "
        f"KAFKA_BROKER={broker}, TOPIC={topic}"
    )

    if not api_url or not broker:
        logging.error("Missing MTA_FEED_URL or KAFKA_BROKER in environment.")
        return

    # Check connectivity before even creating the Producer
    if not test_kafka_connection(broker):
        logging.critical(
            "Aborting: Kafka broker not reachable. "
            "Please verify docker-compose port mappings."
        )
        return

    # Configure Kafka producer
    producer = Producer({"bootstrap.servers": broker})
    logging.info(
        f"Starting GTFS-RT streamer → Kafka {broker} topic '{topic}'"
    )

    while True:
        try:
            resp = requests.get(api_url, timeout=10)
            resp.raise_for_status()
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(resp.content)

            batch = []
            for entity in feed.entity:
                # Convert each protobuf entity to a JSONable dict
                obj = json_format.MessageToDict(entity)
                batch.append(obj)

            if batch:
                logging.info(f"Fetched {len(batch)} records; publishing...")
                for record in batch:
                    producer.produce(
                        topic,
                        key=record.get("id", ""),
                        value=json.dumps(record).encode("utf-8"),
                        callback=lambda err, msg, rec=record: delivery_report(
                            err, msg, rec, dlq_topic, producer
                        )
                    )
                producer.flush()
                # reset backoff after a clean publish
                backoff = int(os.getenv("BACKOFF_BASE", "1"))
                logging.info(f"Published {len(batch)} records to '{topic}'")
            else:
                logging.info("No entities in feed this cycle")

            time.sleep(interval)

        except Exception as e:
            logging.error(f"Fetch/publish error: {e}")
            logging.info(f"Retrying in {backoff} seconds...")
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

if __name__ == "__main__":
    main()
