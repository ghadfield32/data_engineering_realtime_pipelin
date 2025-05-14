#!/usr/bin/env python3
"""
Weather Data Kafka Pipeline DAG with AssetWatcher

This DAG processes weather data from Kafka, transforms it, and loads it into PostgreSQL.
It demonstrates Airflow 3.0's AssetWatcher for Kafka-driven events and explicit SQL operations.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import time

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.sdk import Asset, AssetWatcher
from airflow.providers.standard.triggers.file import FileSensorTrigger
from airflow.providers.kafka.hooks.kafka import KafkaHook
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

# Define an asset that watches for a file indicating new Kafka messages
weather_file_trigger = FileSensorTrigger(filepath="/data/weather/new_data.flag")
weather_data_asset = Asset(
    "weather_data_asset", 
    watchers=[AssetWatcher(name="weather_data_watcher", trigger=weather_file_trigger)]
)

@dag(
    default_args=default_args,
    schedule=[weather_data_asset],  # Event-driven scheduling
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['weather', 'kafka', 'event-driven', 'assetwatcher', 'sql'],
)
def weather_kafka_pipeline():
    """
    ### Weather Data Kafka Pipeline with AssetWatcher

    This DAG demonstrates how to process weather data from Kafka using
    Airflow 3.0's AssetWatcher for event-driven runs. It consumes messages
    from a Kafka topic and stores them in PostgreSQL using explicit SQL operations.

    #### Triggers:
    - File sensor watching for "/data/weather/new_data.flag"
    """

    @task()
    def consume_kafka_messages():
        """Consume weather data from Kafka"""
        topic = Variable.get("WEATHER_KAFKA_TOPIC", default_var="weather-updates")
        max_messages = int(Variable.get("WEATHER_MAX_MESSAGES", default_var="100"))

        kafka_hook = KafkaHook(kafka_conn_id="kafka_default")
        consumer = kafka_hook.get_consumer(
            topics=[topic],
            group_id="weather-pipeline-group",
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            consumer_timeout_ms=10000  # 10 seconds timeout
        )

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
                            logging.warning(f"Skipping non-JSON message: {record.value}")

                # Commit offsets after processing
                consumer.commit()

            logging.info(f"Consumed {message_count} messages in {time.time() - start_time:.2f} seconds")
        finally:
            consumer.close()

        return messages

    @task()
    def process_weather_data(messages):
        """Process and transform the weather data"""
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

    @task()
    def prepare_sql_values(observations):
        """Prepare SQL VALUES for insertion"""
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

    # Create schema and tables with PostgresOperator
    create_schema = PostgresOperator(
        task_id="create_weather_schema",
        postgres_conn_id="postgres_default",
        sql="""
        CREATE SCHEMA IF NOT EXISTS weather;
        """
    )

    create_weather_table = PostgresOperator(
        task_id="create_weather_table",
        postgres_conn_id="postgres_default",
        sql="""
        CREATE TABLE IF NOT EXISTS weather.observations (
            id SERIAL PRIMARY KEY,
            location TEXT NOT NULL,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            obs_time TIMESTAMP,
            temperature DOUBLE PRECISION,
            humidity DOUBLE PRECISION,
            pressure DOUBLE PRECISION,
            wind_speed DOUBLE PRECISION,
            wind_direction TEXT,
            conditions TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # PostgresOperator task that takes values from previous task
    @task()
    def insert_weather_data(values):
        """Insert weather data using PostgresOperator"""
        if not values or values == "''":
            logging.warning("No weather data to insert")
            return {"status": "warning", "message": "No data to insert"}

        insert_data = PostgresOperator(
            task_id="insert_weather_data",
            postgres_conn_id="postgres_default",
            sql=f"""
            INSERT INTO weather.observations
            (location, latitude, longitude, obs_time, temperature, humidity,
             pressure, wind_speed, wind_direction, conditions)
            VALUES {values};
            """
        )

        insert_data.execute(context={})
        return {"status": "success", "count": values.count('),') + 1 if values else 0}

    # Create summary tables and views
    create_daily_summary = PostgresOperator(
        task_id="create_weather_daily_summary",
        postgres_conn_id="postgres_default",
        sql="""
        CREATE TABLE IF NOT EXISTS weather.daily_summary (
            summary_date DATE PRIMARY KEY,
            location_count INTEGER,
            avg_temperature DOUBLE PRECISION,
            min_temperature DOUBLE PRECISION,
            max_temperature DOUBLE PRECISION,
            avg_humidity DOUBLE PRECISION,
            avg_pressure DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # Run analytics to summarize weather data
    run_analytics = PostgresOperator(
        task_id="run_weather_analytics",
        postgres_conn_id="postgres_default",
        sql="""
        -- Insert into daily summary table
        INSERT INTO weather.daily_summary
        (summary_date, location_count, avg_temperature, min_temperature, 
         max_temperature, avg_humidity, avg_pressure)
        SELECT 
            DATE(obs_time) AS summary_date,
            COUNT(DISTINCT location) AS location_count,
            AVG(temperature) AS avg_temperature,
            MIN(temperature) AS min_temperature,
            MAX(temperature) AS max_temperature,
            AVG(humidity) AS avg_humidity,
            AVG(pressure) AS avg_pressure
        FROM weather.observations
        WHERE obs_time >= CURRENT_DATE - INTERVAL '1 day'
        GROUP BY DATE(obs_time)
        ON CONFLICT (summary_date) 
        DO UPDATE SET
            location_count = EXCLUDED.location_count,
            avg_temperature = EXCLUDED.avg_temperature,
            min_temperature = EXCLUDED.min_temperature,
            max_temperature = EXCLUDED.max_temperature,
            avg_humidity = EXCLUDED.avg_humidity,
            avg_pressure = EXCLUDED.avg_pressure,
            created_at = CURRENT_TIMESTAMP;

        -- Calculate location-level statistics
        SELECT 
            location,
            COUNT(*) AS observation_count,
            AVG(temperature) AS avg_temp,
            AVG(humidity) AS avg_humidity,
            MIN(temperature) AS min_temp,
            MAX(temperature) AS max_temp
        FROM weather.observations
        WHERE obs_time >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY location
        ORDER BY observation_count DESC;
        """
    )

    @task()
    def cleanup():
        """Clean up temporary files after processing"""
        try:
            flag_file = "/data/weather/new_data.flag"
            if os.path.exists(flag_file):
                os.remove(flag_file)
                logging.info(f"Removed flag file: {flag_file}")
            else:
                logging.warning(f"Flag file not found: {flag_file}")
        except Exception as e:
            logging.error(f"Error removing flag file: {e}")

        return {"status": "success"}

    # Define task dependencies
    kafka_messages = consume_kafka_messages()
    processed_data = process_weather_data(kafka_messages)
    sql_values = prepare_sql_values(processed_data)

    # Database tasks
    create_schema >> create_weather_table
    create_weather_table >> create_daily_summary

    # Insert and analyze
    insert_result = insert_weather_data(sql_values)
    create_daily_summary >> insert_result >> run_analytics

    # Cleanup
    cleanup_result = cleanup()
    run_analytics >> cleanup_result

    # Set up main flow
    kafka_messages >> processed_data >> sql_values >> insert_result

# Instantiate the DAG
weather_pipeline = weather_kafka_pipeline() 



