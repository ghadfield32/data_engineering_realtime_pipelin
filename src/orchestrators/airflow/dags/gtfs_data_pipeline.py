#!/usr/bin/env python3
"""
GTFS Realtime Data Pipeline DAG 

This DAG fetches GTFS-RT data from the MTA Bus Time API, processes it,
and loads it into the storage backend of choice: S3, BigQuery, Azure Blob, or DuckDB.
It also demonstrates SQL operations by loading data into PostgreSQL.

The DAG demonstrates the Airflow TaskFlow API (Python functions as tasks)
and parameterization for different cloud environments.
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.models import Variable, Connection
from airflow.operators.python import get_current_context
from airflow.utils.dates import days_ago
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.operators.empty import EmptyOperator

# Add the ingestion module to Python path
# Adjust this path based on your deployment
from ingestion.fetch_gtfs import GTFSFetcher

# Default settings applied to all tasks
default_args = {
    'owner': 'data-engineering',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(minutes=10),
}

# Configurable parameters with defaults
# These can be overridden by setting Airflow Variables
CLOUD_PROVIDER = Variable.get("CLOUD_PROVIDER", default_var="local")  # aws, gcp, azure, or local
STORAGE_TYPE = Variable.get("STORAGE_TYPE", default_var="duckdb")  # s3, gcs, azure_blob, bigquery, duckdb
API_URL = Variable.get("GTFS_API_URL", default_var="https://gtfsrt.prod.obanyc.com/vehiclePositions")
OUTPUT_FORMAT = Variable.get("OUTPUT_FORMAT", default_var="json")
USE_SQL_DB = Variable.get("USE_SQL_DB", default_var="true").lower() == "true"  # Whether to also load data into PostgreSQL

# Cloud-specific settings with defaults
if CLOUD_PROVIDER == "aws":
    S3_BUCKET = Variable.get("S3_BUCKET", default_var="gtfs-data")
    S3_PREFIX = Variable.get("S3_PREFIX", default_var="vehicle_positions")
elif CLOUD_PROVIDER == "gcp":
    GCS_BUCKET = Variable.get("GCS_BUCKET", default_var="gtfs-data")
    GCS_PREFIX = Variable.get("GCS_PREFIX", default_var="vehicle_positions")
    BQ_DATASET = Variable.get("BQ_DATASET", default_var="gtfs_data")
    BQ_TABLE = Variable.get("BQ_TABLE", default_var="vehicle_positions")
elif CLOUD_PROVIDER == "azure":
    AZURE_CONTAINER = Variable.get("AZURE_CONTAINER", default_var="gtfs-data")
    AZURE_PREFIX = Variable.get("AZURE_PREFIX", default_var="vehicle_positions")
else:  # local
    DUCKDB_PATH = Variable.get("DUCKDB_PATH", default_var="/tmp/gtfs.duckdb")
    DUCKDB_TABLE = Variable.get("DUCKDB_TABLE", default_var="vehicle_positions")

# Define an asset for asset-driven scheduling
from airflow.sdk import Asset, AssetWatcher
from airflow.providers.standard.triggers.file import FileSensorTrigger

# Create a file sensor trigger for the GTFS asset
gtfs_file_trigger = FileSensorTrigger(filepath="/data/gtfs/new_data.flag")
gtfs_asset = Asset(
    "gtfs_data_asset", 
    watchers=[AssetWatcher(name="gtfs_data_watcher", trigger=gtfs_file_trigger)]
)

@dag(
    default_args=default_args,
    schedule=[gtfs_asset],  # asset-driven scheduling
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=['gtfs', 'realtime', 'sql', CLOUD_PROVIDER],
    doc_md=__doc__
)
def gtfs_data_pipeline():
    """
    ### GTFS-RT Data Pipeline

    This DAG demonstrates how to fetch and process GTFS-RT data with Airflow,
    using different cloud providers and storage backends.

    #### Environment configuration
    * Cloud Provider: {cloud_provider}
    * Storage Type: {storage_type}
    * Data Format: {format}
    * Also Load to SQL DB: {use_sql_db}
    * Schedule: Asset-driven (file trigger)
    """.format(
        cloud_provider=CLOUD_PROVIDER,
        storage_type=STORAGE_TYPE,
        format=OUTPUT_FORMAT,
        use_sql_db=USE_SQL_DB
    )

    @task()
    def fetch_gtfs():
        """Fetch GTFS-RT data from the configured API"""
        # Get API key from connection if configured
        try:
            conn = Connection.get_connection_from_secrets("gtfs_api")
            api_key = conn.password if conn else os.getenv("MTA_API_KEY")
        except:
            api_key = os.getenv("MTA_API_KEY")

        # Initialize fetcher
        fetcher = GTFSFetcher(api_url=API_URL, api_key=api_key)

        # Get the data
        logging.info(f"Fetching GTFS data from {API_URL}")
        try:
            data = fetcher.fetch_and_parse()
            logging.info(f"Successfully fetched {len(data)} GTFS entities")
            return data
        except Exception as e:
            logging.error(f"Error fetching GTFS data: {e}")
            raise

    @task()
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

    @task()
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

    @task()
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

    @task()
    def store_data(data):
        """Store the data in the configured backend"""
        if not data:
            logging.warning("No data to store")
            return {"status": "warning", "message": "No data to store"}

        # Get the fetcher for storage methods
        try:
            conn = Connection.get_connection_from_secrets("gtfs_api")
            api_key = conn.password if conn else os.getenv("MTA_API_KEY")
        except:
            api_key = os.getenv("MTA_API_KEY")

        fetcher = GTFSFetcher(api_url=API_URL, api_key=api_key)

        # Store based on the configured backend
        try:
            if CLOUD_PROVIDER == "aws":
                location = fetcher.save_to_s3(
                    data, 
                    bucket=S3_BUCKET, 
                    prefix=S3_PREFIX, 
                    fmt=OUTPUT_FORMAT
                )
                logging.info(f"Data saved to S3: {location}")
                return {"status": "success", "location": location}

            elif CLOUD_PROVIDER == "gcp":
                if STORAGE_TYPE == "bigquery":
                    rows = fetcher.save_to_bigquery(data, BQ_DATASET, BQ_TABLE)
                    logging.info(f"Data saved to BigQuery: {rows} rows")
                    return {"status": "success", "rows": rows}
                else:
                    location = fetcher.save_to_gcs(
                        data, 
                        bucket=GCS_BUCKET, 
                        prefix=GCS_PREFIX, 
                        fmt=OUTPUT_FORMAT
                    )
                    logging.info(f"Data saved to GCS: {location}")
                    return {"status": "success", "location": location}

            elif CLOUD_PROVIDER == "azure":
                # Azure implementation would go here
                # This would use the Azure blob storage client
                logging.info("Azure storage not yet implemented")
                return {"status": "not_implemented", "message": "Azure storage not yet implemented"}

            else:  # local/duckdb
                rows = fetcher.save_to_duckdb(data, table=DUCKDB_TABLE, db_path=DUCKDB_PATH)
                logging.info(f"Data saved to DuckDB: {DUCKDB_PATH}, table: {DUCKDB_TABLE}, {rows} rows")
                return {"status": "success", "rows": rows, "database": DUCKDB_PATH}

        except Exception as e:
            logging.error(f"Error storing data: {e}")
            raise

    # Create PostgreSQL tables
    create_pg_table = PostgresOperator(
        task_id="create_gtfs_table",
        postgres_conn_id="postgres_default",
        sql="""
        CREATE TABLE IF NOT EXISTS public.gtfs_vehicle_positions (
            vehicle_id TEXT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            bearing DOUBLE PRECISION,
            speed DOUBLE PRECISION,
            timestamp TIMESTAMP,
            processing_time TIMESTAMP,
            PRIMARY KEY (vehicle_id, processing_time)
        );
        """
    )

    # Insert task with dynamic SQL
    @task()
    def insert_to_postgres(values):
        """Insert the values into PostgreSQL using PostgresOperator"""
        if not values or values == "''":
            logging.warning("No values to insert into PostgreSQL")
            return {"rows_inserted": 0}

        pg_insert = PostgresOperator(
            task_id="insert_gtfs_data",
            postgres_conn_id="postgres_default",
            sql=f"""
            INSERT INTO public.gtfs_vehicle_positions
            (vehicle_id, latitude, longitude, bearing, speed, timestamp, processing_time)
            VALUES {values}
            ON CONFLICT (vehicle_id, processing_time) 
            DO UPDATE SET
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                bearing = EXCLUDED.bearing,
                speed = EXCLUDED.speed;
            """
        )

        pg_insert.execute(context={})
        return {"rows_inserted": values.count('),') + 1 if values else 0}

    # Task to clean up the flag file that triggered this DAG
    @task()
    def cleanup():
        """Clean up the flag file that triggered this DAG"""
        try:
            flag_file = "/data/gtfs/new_data.flag"
            if os.path.exists(flag_file):
                os.remove(flag_file)
                logging.info(f"Removed flag file: {flag_file}")
            else:
                logging.warning(f"Flag file not found: {flag_file}")
        except Exception as e:
            logging.error(f"Error removing flag file: {e}")

    # Define SQL branch based on configuration
    sql_branch = EmptyOperator(task_id="skip_sql_branch") if not USE_SQL_DB else EmptyOperator(task_id="use_sql_branch")

    # Define the task dependencies
    raw_data = fetch_gtfs()
    processed_data = process_data(raw_data)
    storage_result = store_data(processed_data)

    # SQL branch
    if USE_SQL_DB:
        sql_data = transform_for_sql(processed_data)
        sql_values = prepare_sql_values(sql_data)
        create_pg_table >> insert_to_postgres(sql_values) >> cleanup()

    # Main flow
    raw_data >> processed_data >> storage_result

    # Return the DAG result
    return {"result": storage_result}

# Instantiate the DAG
gtfs_pipeline = gtfs_data_pipeline() 
