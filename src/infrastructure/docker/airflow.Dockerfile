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

USER airflow

# Set environment variables explicitly to avoid SQLAlchemy conflicts
ENV AIRFLOW__DATABASE__EXECUTEMANY_MODE=batch 

WORKDIR /app
COPY pyproject.toml /app/
RUN pip install --no-cache-dir /app/

# Only copy your DAGs and plugins when they change
COPY src/orchestrators/airflow/dags /opt/airflow/dags
COPY src/orchestrators/airflow/plugins /opt/airflow/plugins

# Initialize Airflow
WORKDIR /opt/airflow 
