

#!/usr/bin/env python3
"""Weather data processing helper functions for Airflow DAGs"""

import os
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

class WeatherProcessor:
    """Class to process weather data from Kafka"""

    @staticmethod
    def consume_kafka_messages(
        consumer,
        topic: str = "weather-updates",
        max_messages: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Consume weather data from Kafka

        Args:
            consumer: Kafka consumer instance
            topic: Kafka topic to consume from
            max_messages: Maximum number of messages to consume

        Returns:
            List of consumed messages
        """
        messages = []
        message_count = 0

        logging.info(f"Starting to consume messages from Kafka topic: {topic}")
        start_time = time.time()

        # Use poll to get better control over consumption
        try:
            while message_count < max_messages:
                poll_result = consumer.poll(timeout_ms=5000, max_records=max_messages)
                if not poll_result:
                    break

                # Process all partitions and messages
                for tp, records in poll_result.items():
                    for record in records:
                        try:
                            message = json.loads(record.value.decode('utf-8'))
                            message['_metadata'] = {
                                'topic': record.topic,
                                'partition': record.partition,
                                'offset': record.offset,
                                'timestamp': record.timestamp
                            }
                            messages.append(message)
                            message_count += 1
                        except json.JSONDecodeError:
                            logging.warning(
                                f"Skipping non-JSON message: {record.value}"
                            )

                # Commit offsets after processing
                consumer.commit()

            logging.info(
                f"Consumed {message_count} messages in "
                f"{time.time() - start_time:.2f} seconds"
            )
        finally:
            consumer.close()

        return messages

    @staticmethod
    def process_weather_data(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process and transform the weather data

        Args:
            messages: Raw Kafka messages

        Returns:
            Processed weather data
        """
        if not messages:
            logging.warning("No weather messages to process")
            return []

        processed_data = []
        processing_time = datetime.now().isoformat()

        for message in messages:
            try:
                # Extract weather observation data
                observation = {
                    'location': message.get('location', 'unknown'),
                    'latitude': message.get('lat'),
                    'longitude': message.get('lon'),
                    'obs_time': message.get('observation_time'),
                    'temperature': message.get('temp_c'),
                    'humidity': message.get('humidity'),
                    'pressure': message.get('pressure_mb'),
                    'wind_speed': message.get('wind_kph'),
                    'wind_direction': message.get('wind_dir'),
                    'conditions': message.get('condition', {}).get('text'),
                    '_processing_time': processing_time
                }
                processed_data.append(observation)
            except Exception as e:
                logging.error(f"Error processing weather message: {e}")

        logging.info(f"Processed {len(processed_data)} weather observations")
        return processed_data

    @staticmethod
    def prepare_sql_values(observations: List[Dict[str, Any]]) -> str:
        """
        Prepare SQL VALUES for insertion

        Args:
            observations: List of processed weather observations

        Returns:
            SQL VALUES string for insertion
        """
        if not observations:
            return "''"

        values_strings = []
        for obs in observations:
            # Format values for SQL INSERT
            values_str = f"""(
                '{obs['location']}', 
                {obs['latitude'] if obs['latitude'] is not None else 'NULL'}, 
                {obs['longitude'] if obs['longitude'] is not None else 'NULL'}, 
                '{obs['obs_time']}', 
                {obs['temperature'] if obs['temperature'] is not None else 'NULL'}, 
                {obs['humidity'] if obs['humidity'] is not None else 'NULL'}, 
                {obs['pressure'] if obs['pressure'] is not None else 'NULL'}, 
                {obs['wind_speed'] if obs['wind_speed'] is not None else 'NULL'}, 
                '{obs['wind_direction']}', 
                '{obs['conditions'] if obs['conditions'] else ''}'
            )"""
            values_strings.append(values_str)

        return ", ".join(values_strings)

    @staticmethod
    def cleanup_flag_file(flag_file_path: str) -> Dict[str, str]:
        """
        Clean up the flag file that triggered a DAG

        Args:
            flag_file_path: Path to the flag file

        Returns:
            Status dictionary
        """
        try:
            if os.path.exists(flag_file_path):
                os.remove(flag_file_path)
                logging.info(f"Removed flag file: {flag_file_path}")
            else:
                logging.warning(f"Flag file not found: {flag_file_path}")
        except Exception as e:
            logging.error(f"Error removing flag file: {e}")

        return {"status": "success"} 
