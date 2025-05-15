from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.apache.kafka.hooks.consume import KafkaConsumerHook  # fixed import
from pendulum import datetime

from include.custom_functions.weather_functions import WeatherProcessor

@dag(
    start_date=datetime(2025, 5, 1),
    catchup=False,
    dag_display_name="Weather Kafka Pipeline ☁️",
    tags=['weather', 'kafka', 'event-driven', 'sql']
)
def weather_kafka_pipeline():
    @task()
    def consume_kafka_messages():
        topic = Variable.get("WEATHER_KAFKA_TOPIC", default_var="weather-updates")
        max_messages = int(Variable.get("WEATHER_MAX_MESSAGES", default_var="100"))

        kafka_hook = KafkaConsumerHook(
            topics=[topic],
            kafka_config_id="kafka_default",
        )
        consumer = kafka_hook.get_consumer()
        return WeatherProcessor.consume_kafka_messages(consumer, topic, max_messages)

    @task()
    def process_weather_data(messages):
        return WeatherProcessor.process_weather_data(messages)

    @task()
    def prepare_sql_values(observations):
        return WeatherProcessor.prepare_sql_values(observations)

    create_table = SQLExecuteQueryOperator(
        task_id="create_weather_observations_table",
        conn_id="postgres_default",
        sql="""
        CREATE TABLE IF NOT EXISTS weather.observations (
          id SERIAL PRIMARY KEY,
          location TEXT,
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

    insert = SQLExecuteQueryOperator(
        task_id="insert_weather_data",
        conn_id="postgres_default",
        sql="""
        INSERT INTO weather.observations
        (location, latitude, longitude, obs_time, temperature, humidity, pressure, wind_speed, wind_direction, conditions)
        VALUES {{ ti.xcom_pull('prepare_sql_values') }};
        """
    )

    msgs = consume_kafka_messages()
    proc = process_weather_data(msgs)
    vals = prepare_sql_values(proc)
    create_table >> insert

weather_kafka_pipeline_dag = weather_kafka_pipeline()
