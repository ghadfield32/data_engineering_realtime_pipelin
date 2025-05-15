
# src/orchestrators/airflow/dags/user_metrics_etl.py
from airflow.decorators import dag, task
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.utils.dates import days_ago

@dag(start_date=days_ago(1), schedule_interval="@daily", tags=["metrics", "sql"])
def user_metrics_etl():
    @task()
    def extract():
        # …
        return data

    @task()
    def transform(data):
        # …
        return sql_values

    create_table = PostgresOperator(
        task_id="create_user_metrics_table",
        postgres_conn_id="postgres_default",
        sql="""
        CREATE TABLE IF NOT EXISTS user_metrics (…);
        """
    )

    load = PostgresOperator(
        task_id="load_user_metrics",
        postgres_conn_id="postgres_default",
        sql="INSERT INTO user_metrics VALUES {{ params.values }};",
        parameters={"values": "{{ ti.xcom_pull('transform') }}"}
    )

    data = extract()
    vals = transform(data)
    create_table >> load

user_metrics_etl_dag = user_metrics_etl()
