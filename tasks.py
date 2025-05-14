#!/usr/bin/env python
# tasks.py


from invoke import task
import os
import sys
import time
import json
import pathlib
from dotenv import load_dotenv
import secrets
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
    host_pw_file = os.path.join(
        "src", "orchestrators", "airflow", "simple_auth_manager_passwords.json.generated"
    )
    container_pw_file = "/opt/airflow/simple_auth_manager_passwords.json.generated"

    print(f"\n🚀 Airflow UI: http://localhost:{port}")
    print(f"   Username: {user}")
    
    # First, try to read from the container
    password_found = False
    import subprocess
    
    try:
        # Check if the airflow-webserver container is running
        if IS_WINDOWS:
            ps_cmd = f"{COMPOSE_CMD} ps airflow-webserver"
            result = subprocess.run(ps_cmd, shell=True, capture_output=True, text=True)
            is_running = "Up" in result.stdout
        else:
            result = os.system(f"{COMPOSE_CMD} ps airflow-webserver | grep -q 'Up'")
            is_running = result == 0
            
        if is_running:
            # Try to read the password file from inside the container
            cmd = f"{COMPOSE_CMD} exec -T airflow-webserver cat {container_pw_file}"
            try:
                output = subprocess.check_output(
                    cmd, shell=True, text=True, stderr=subprocess.PIPE
                )
                pw_data = json.loads(output)
                pwd = pw_data.get(user)
                if pwd:
                    print(f"   Password: {pwd}\n")
                    password_found = True
            except subprocess.CalledProcessError:
                # File doesn't exist in container, we'll handle this below
                pass
            except Exception as e:
                print(f"   Error reading password from container: {e}")
    except Exception as e:
        print(f"   Error checking container status: {e}")
    
    # If we couldn't get the password from the container, try the host file
    if not password_found:
        try:
            if os.path.exists(host_pw_file) and os.access(host_pw_file, os.R_OK):
                with open(host_pw_file) as f:
                    pw_data = json.loads(f.read())
                pwd = pw_data.get(user)
                if pwd:
                    print(f"   Password: {pwd}\n")
                    password_found = True
        except Exception as e:
            print(f"   Error reading host password file: {e}")
    
    # If we still don't have a password, create a password file
    if not password_found:
        # Get the configured password from .env
        pwd = os.getenv("AIRFLOW_ADMIN_PASSWORD", "")
        print(f"   Password: {pwd} (from .env file)\n")
        
        # Try to create a password file for future use
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(host_pw_file), exist_ok=True)
            
            # Create password file with the same format Airflow would use
            pw_data = {user: pwd}
            with open(host_pw_file, 'w') as f:
                json.dump(pw_data, f, indent=2)
            
            print("   Created password file for future use.")
            print(f"   File location: {host_pw_file}\n")
        except Exception as e:
            print(f"   Note: Could not create password file: {e}")
            print("   Will continue using password from .env file.\n")


@task
def airflow(ctx):
    """
    Start all services needed for the Airflow orchestrator, generate a fresh
    random admin password, and display UI credentials.
    """
    # 1) generate a secure random password
    user = os.getenv("AIRFLOW_ADMIN_USERNAME", "admin")
    pwd = secrets.token_urlsafe(12)

    # 2) inject/update it into .env
    env_lines = []
    env_file = pathlib.Path(".env")
    if env_file.exists():
        env_lines = env_file.read_text().splitlines()
        # replace any existing AIRFLOW_ADMIN_PASSWORD
        for i, line in enumerate(env_lines):
            if line.startswith("AIRFLOW_ADMIN_PASSWORD="):
                env_lines[i] = f"AIRFLOW_ADMIN_PASSWORD={pwd}"
                break
        else:
            env_lines.append(f"AIRFLOW_ADMIN_PASSWORD={pwd}")
    else:
        env_lines = [f"AIRFLOW_ADMIN_PASSWORD={pwd}"]
    env_file.write_text("\n".join(env_lines) + "\n")

    # 3) seed the simple_auth_manager file on the host so container starts with it
    host_pw_path = pathlib.Path("src/orchestrators/airflow/simple_auth_manager_passwords.json.generated")
    host_pw_path.parent.mkdir(parents=True, exist_ok=True)
    host_pw_path.write_text(json.dumps({user: pwd}, indent=2))

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
