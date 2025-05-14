#!/usr/bin/env python
# tasks.py


from invoke import task
import os
import sys
import time
import json
import pathlib
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Base docker-compose command with env-file
COMPOSE_CMD = "docker-compose -f docker-compose.yml --env-file .env"

# Check if we're on Windows
IS_WINDOWS = sys.platform.startswith("win")


def _print_airflow_credentials():
    """
    Print the Airflow UI URL and the actual password from
    simple_auth_manager_passwords.json.generated.
    """
    user = os.getenv("AIRFLOW_ADMIN_USERNAME", "admin")
    port = os.getenv("AIRFLOW_WEB_PORT", "8080")
    pw_file = os.path.join("airflow_home", "simple_auth_manager_passwords.json.generated")

    print(f"\n🚀 Airflow UI: http://localhost:{port}")
    print(f"   Username: {user}")
    
    # Try to read the generated password from JSON file
    try:
        if os.path.exists(pw_file):
            with open(pw_file) as f:
                pw_data = json.load(f)
            pwd = pw_data.get(user)
            if pwd:
                print(f"   Password: {pwd}\n")
            else:
                print(f"   Password not found for user '{user}' in the JSON file.")
                print(f"   Using configured password instead.\n")
                pwd = os.getenv("AIRFLOW_ADMIN_PASSWORD", "")
                print(f"   Password: {pwd} (from .env file)\n")
        else:
            # Fall back to the configured password
            pwd = os.getenv("AIRFLOW_ADMIN_PASSWORD", "")
            print(f"   Password: {pwd} (from .env file)\n")
            print("   Note: Password file not found, this might be a configuration issue.")
            print("   Check if the volume mount for ./airflow_home is working properly.\n")
    except Exception as e:
        # Fall back to the configured password
        pwd = os.getenv("AIRFLOW_ADMIN_PASSWORD", "")
        print(f"   Password: {pwd} (from .env file)\n")
        print(f"   Error reading password file: {e}\n")


@task
def airflow(ctx):
    """
    Start all services needed for the Airflow orchestrator and display UI credentials.
    """
    services = [
        "zookeeper", "kafka", "kafka-ui",
        "flink-jobmanager", "flink-taskmanager",
        "minio", "minio-setup",
        "duckdb", "trino-coordinator",
        "postgres", "redis",
        "airflow-webserver", "airflow-scheduler", "airflow-worker", "airflow-triggerer"
    ]
    ctx.run(f"{COMPOSE_CMD} up -d " + " ".join(services))
    # Wait a moment for services to stabilize
    time.sleep(5)
    _print_airflow_credentials()


@task(help={'cmd': "dbt command to run, e.g. 'run', 'test'"})
def dbt(ctx, cmd="run"):
    """
    Execute a dbt command inside the Airflow container, after starting dependencies.
    """
    # Ensure Postgres is available for dbt
    ctx.run(f"{COMPOSE_CMD} up -d postgres")
    # Run the specified dbt command
    ctx.run(
        f"{COMPOSE_CMD} run --rm airflow-webserver dbt {cmd} --project-dir /opt/airflow/dbt"
    )


@task
def kestra(ctx):
    """
    Start all services needed for the Kestra orchestrator.
    """
    services = [
        "postgres", "redis",
        "zookeeper", "kafka", "kafka-ui",
        "flink-jobmanager", "flink-taskmanager",
        "minio", "minio-setup",
        "duckdb", "trino-coordinator",
        "kestra"
    ]
    ctx.run(f"{COMPOSE_CMD} up -d " + " ".join(services))
    port = os.getenv("KESTRA_PORT", "8080")
    print(f"\n🚀 Kestra UI: http://localhost:{port}\n")


@task
def all(ctx):
    """
    Start all services (both Airflow and Kestra).
    """
    services = [
        "postgres", "redis", 
        "zookeeper", "kafka", "kafka-ui",
        "flink-jobmanager", "flink-taskmanager",
        "minio", "minio-setup",
        "duckdb", "trino-coordinator",
        "airflow-webserver", "airflow-scheduler", "airflow-worker", "airflow-triggerer",
        "kestra"
    ]
    ctx.run(f"{COMPOSE_CMD} up -d " + " ".join(services))
    # Wait a moment for services to stabilize
    time.sleep(5)
    _print_airflow_credentials()
    kestra_port = os.getenv("KESTRA_PORT", "8080")
    print(f"🚀 Kestra UI: http://localhost:{kestra_port}\n")
