"""GTFS-Realtime client for fetching and parsing vehicle positions."""

import requests
from google.protobuf import json_format
from google.transit import gtfs_realtime_pb2
import logging

logger = logging.getLogger(__name__)

def fetch_vehicle_positions(url: str):
    """
    Fetch the GTFS-RT vehiclePositions feed and return list of dicts.
    """
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)

    records = [json_format.MessageToDict(e) for e in feed.entity]
    logger.debug(f"Parsed {len(records)} GTFS entities")
    return records