FROM apache/airflow:3.0.1-python3.10


USER root

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        libpq-dev \
    && apt-get autoremove -yqq --purge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install provider packages as root to make them available system-wide
RUN pip install --no-cache-dir \
    apache-airflow-providers-postgres>=5.0.0 \
    apache-airflow-providers-apache-kafka>=1.1.0 \
    apache-airflow-providers-standard>=1.0.0 \
    apache-airflow-providers-http>=4.5.0 \
    confluent-kafka>=2.1.0 \
    gtfs-realtime-bindings>=1.0.0

USER airflow

# Set environment variables explicitly to avoid SQLAlchemy conflicts
ENV AIRFLOW__DATABASE__EXECUTEMANY_MODE=batch 
ENV AIRFLOW_CONFIG=/opt/airflow/airflow.cfg

WORKDIR /app
COPY pyproject.toml /app/

# Install the main package
RUN pip install --no-cache-dir /app/

# Copy configuration files
COPY src/orchestrators/airflow/config/airflow.cfg /opt/airflow/airflow.cfg

# Only copy your DAGs and plugins when they change
COPY src/orchestrators/airflow/dags /opt/airflow/dags
COPY src/orchestrators/airflow/plugins /opt/airflow/plugins

# Initialize Airflow
WORKDIR /opt/airflow


