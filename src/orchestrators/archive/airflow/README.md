# Airflow Configuration

This directory contains the Airflow configuration for the data engineering realtime pipeline project.

## Structure

- `config/` - Contains the Airflow configuration file (airflow.cfg)
- `dags/` - Your Airflow DAG files
- `plugins/` - Any Airflow plugins
- `logs/` - Airflow logs (mounted as a volume)
- `simple_auth_manager_passwords.json.generated` - Generated passwords file for Airflow auth

## Path Change Notice

The Airflow home directory has been moved from `airflow_home/` to `src/orchestrators/airflow/` to better align with the project structure.

## Container Configuration

- The Airflow configuration file is explicitly set with `AIRFLOW_CONFIG=/opt/airflow/airflow.cfg`
- DAGs are mounted from `./src/orchestrators/airflow/dags:/opt/airflow/dags`
- The configuration is applied to all Airflow containers (webserver, scheduler, worker, triggerer)

## Authentication

- Airflow 3.0 uses SimpleAuthManager
- Default credentials are set in the docker-compose environment variables
- Generated passwords are stored in `simple_auth_manager_passwords.json.generated` 