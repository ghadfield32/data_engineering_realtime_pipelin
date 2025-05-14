
import os, sys, logging
from airflow.decorators import dag, task
from airflow.utils.dates import days_ago

# — DEBUG STARTUP —
logging.getLogger().setLevel(logging.INFO)
logging.info(f"STARTUP DEBUG — PYTHONPATH: {os.environ.get('PYTHONPATH')}")
logging.info("STARTUP DEBUG — sys.path:\n    " + "\n    ".join(sys.path))
try:
    logging.info(f"Contents of /src: {os.listdir('/src')}")
except:
    logging.info("Cannot list /src")
logging.info(f"Contents of {os.getcwd()}: {os.listdir(os.getcwd())}")
# — DEBUG END —

from airflow.models import Variable, Connection
from airflow.providers.postgres.operators.postgres import PostgresOperator
from ingestion.fetch_gtfs import GTFSFetcher

@dag(schedule=None, start_date=days_ago(1), catchup=False, tags=["debug"])
def gtfs_data_pipeline_debug():
    @task()
    def debug_env():
        logging.info(f"TASK-RUN DEBUG — sys.path:\n    " + "\n    ".join(sys.path))
        return

    @task()
    def fetch_gtfs():
        pass

    debug_env() >> fetch_gtfs()

gtfs_pipeline_debug = gtfs_data_pipeline_debug()
