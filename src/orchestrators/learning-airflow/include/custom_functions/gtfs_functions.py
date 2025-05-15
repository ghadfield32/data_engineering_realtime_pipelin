
#!/usr/bin/env python3
"""GTFS helper functions for Airflow DAGs"""

import os
import logging
import json
from datetime import datetime

class GTFSProcessor:
    """Class to process GTFS Realtime data"""

    @staticmethod
    def process_data(data):
        """Process the GTFS data before storing"""
        # Add processing timestamp
        processed_data = []
        processing_time = datetime.now().isoformat()

        for entity in data:
            # Add processing metadata
            entity['_processing_time'] = processing_time
            processed_data.append(entity)

        logging.info(f"Processed {len(processed_data)} GTFS entities")
        return processed_data

    @staticmethod
    def transform_for_sql(data):
        """Transform data into a format suitable for SQL insertion"""
        if not data:
            return []

        sql_ready_data = []
        for entity in data:
            if 'vehicle' in entity and 'position' in entity['vehicle']:
                try:
                    vehicle_id = entity.get('id', '') or entity['vehicle'].get('vehicle', {}).get('id', 'unknown')
                    position = entity['vehicle']['position']
                    timestamp = entity['vehicle'].get('timestamp', '')

                    record = (
                        vehicle_id,
                        position.get('latitude', 0),
                        position.get('longitude', 0),
                        position.get('bearing', 0),
                        position.get('speed', 0),
                        timestamp,
                        entity.get('_processing_time', '')
                    )
                    sql_ready_data.append(record)
                except (KeyError, TypeError) as e:
                    logging.warning(f"Could not extract position data from entity: {e}")

        logging.info(f"Transformed {len(sql_ready_data)} entities for SQL insertion")
        # Return as a list of tuples for SQL insertion
        return sql_ready_data

    @staticmethod
    def prepare_sql_values(sql_data):
        """Convert data to SQL VALUES format for PostgresOperator"""
        if not sql_data:
            return "''"  # Empty string if no data

        # Convert list of tuples to SQL VALUES syntax
        values_strings = []
        for record in sql_data:
            values_str = f"('{record[0]}', {record[1]}, {record[2]}, {record[3]}, {record[4]}, '{record[5]}', '{record[6]}')"
            values_strings.append(values_str)

        return ", ".join(values_strings)

    @staticmethod
    def cleanup_flag_file(flag_file_path):
        """Clean up the flag file that triggered a DAG"""
        try:
            if os.path.exists(flag_file_path):
                os.remove(flag_file_path)
                logging.info(f"Removed flag file: {flag_file_path}")
            else:
                logging.warning(f"Flag file not found: {flag_file_path}")
        except Exception as e:
            logging.error(f"Error removing flag file: {e}") 
