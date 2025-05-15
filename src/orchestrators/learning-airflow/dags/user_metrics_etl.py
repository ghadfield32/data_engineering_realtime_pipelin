# src/orchestrators/learning-airflow/dags/user_metrics_etl.py

from airflow.decorators import dag, task
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from pendulum import datetime  # use pendulum directly

from include.custom_functions.user_metrics_functions import UserMetricsProcessor

@dag(
    start_date=datetime(2025, 5, 1),      # use pendulum directly here
    schedule="@daily",
    dag_display_name="User Metrics ETL 📊",
    catchup=False,
    tags=["metrics", "sql"]
)
def user_metrics_etl():
    @task()
    def extract():
        return UserMetricsProcessor.extract()

    @task()
    def transform(data):
        return UserMetricsProcessor.transform(data)

    create_table = SQLExecuteQueryOperator(
        task_id="create_user_metrics_table",
        conn_id="postgres_default",
        sql="""
        CREATE TABLE IF NOT EXISTS user_metrics (
            user_id INTEGER PRIMARY KEY,
            session_count INTEGER,
            total_duration_mins INTEGER,
            conversion_rate DOUBLE PRECISION,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    load = SQLExecuteQueryOperator(
        task_id="load_user_metrics",
        conn_id="postgres_default",
        sql="""
        INSERT INTO user_metrics (user_id, session_count, total_duration_mins, conversion_rate)
        VALUES {{ ti.xcom_pull('transform') }}
        ON CONFLICT (user_id) DO UPDATE
          SET session_count       = EXCLUDED.session_count,
              total_duration_mins = EXCLUDED.total_duration_mins,
              conversion_rate     = EXCLUDED.conversion_rate,
              updated_at          = CURRENT_TIMESTAMP;
        """
    )

    data = extract()
    vals = transform(data)
    create_table >> load

user_metrics_etl_dag = user_metrics_etl()


