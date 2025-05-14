# Docker Infrastructure Guide

## Docker Setup Overview

Our project has a comprehensive Docker Compose setup to support the multi-cloud data engineering pipeline:

- **Core infrastructure**: Kafka, Zookeeper, Flink, MinIO, Trino
- **Orchestration tools**: Airflow, Kestra
- **Database services**: DuckDB, PostgreSQL

All of these components are defined in a single `docker-compose.yml` file.

## Service Configuration Highlights

1. **Port assignments**:
   - Kafka UI: 8089
   - Flink JobManager: 8082
   - Airflow Webserver: 8081
   - Trino: 8080
   - Kestra: 8083
   - MinIO: 9000, 9001 (UI)

2. **Integration**:
   - Services reference each other with proper dependencies
   - Health checks ensure services wait for dependencies
   - Shared volumes for data persistence

3. **Optimized for local development**:
   - All volumes are local
   - Minimal configuration required to run

## Running the Infrastructure

### Prerequisites

1. Docker and Docker Compose installed
2. At least 8GB RAM available for Docker
3. Python 3.10+ for running client scripts

### Starting the Services

For running the complete data engineering pipeline with all components:

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps
```

For running just the core streaming components (Kafka, Zookeeper):

```bash
# Start only Kafka components
docker-compose up -d zookeeper kafka

# Create required topics
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic vehicle_positions --partitions 1 --replication-factor 1
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic vehicle_positions_dlq --partitions 1 --replication-factor 1
```

### Accessing Services

- **Kafka UI**: http://localhost:8089
- **Airflow**: http://localhost:8081 (user: admin, password: admin)
- **Flink JobManager**: http://localhost:8082
- **Trino**: http://localhost:8080
- **MinIO**: http://localhost:9001 (user: minio, password: minio123)
- **Kestra**: http://localhost:8083

## Troubleshooting

If you encounter issues with the Docker setup:

1. Check Docker logs: `docker-compose logs [service_name]`
2. Verify port availability: `netstat -ano | findstr [port]` (Windows) or `lsof -i :[port]` (Linux/Mac)
3. Increase Docker memory allocation if containers crash
4. Ensure health checks pass before accessing services

## Testing the Pipeline

We've successfully tested the real-time data pipeline with the following steps:

1. **Dependency Management**:
   - Consolidated all dependencies in `pyproject.toml`
   - Used `uv` for Python package management
   - Removed separate requirements files for better maintainability

2. **Environment Configuration**:
   - Created a properly encoded `.env.engineering` file
   - Set up environment variables for API keys, Kafka settings, and polling intervals

3. **Infrastructure Setup**:
   - Started Kafka and Zookeeper containers
   - Created necessary Kafka topics (`vehicle_positions` and `vehicle_positions_dlq`)
   - Verified connectivity to Kafka broker

4. **Data Streaming**:
   - Successfully ran the GTFS streaming script (`scripts/stream_gtfs.py`)
   - Verified data publication to Kafka topics
   - Confirmed message delivery with Kafka consumer

### Key Improvements

1. **Unified Dependency Management**:
   - All dependencies are now in `pyproject.toml`
   - Added missing dependencies for Kafka, GTFS, and cloud providers
   - Organized dependencies into logical groups (core, cloud-specific, orchestrators)

2. **Robust Error Handling**:
   - Added dead letter queue (DLQ) for failed messages
   - Implemented exponential backoff for retries
   - Added connection testing before attempting to publish

3. **Streamlined Testing Process**:
   - Updated `test_pipeline.sh` to check for running containers
   - Added proper dependency installation with `uv`
   - Improved error reporting and logging

To test the pipeline yourself, run:

```bash
# Start infrastructure
docker-compose up -d zookeeper kafka

# Install dependencies
pip install -e ".[kafka]"

# Run the GTFS streaming script
python scripts/stream_gtfs.py

# In another terminal, verify data is being published
docker exec kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic vehicle_positions --from-beginning --max-messages 5
```

## Environment Configuration

The pipeline requires environment variables. Copy the `.env.engineering` template and add your API key:

```
# Edit the file
nano .env.engineering

# Update the MTA_API_KEY value
MTA_API_KEY=your_actual_api_key_here
``` 