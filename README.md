# Data Engineering Real-Time Pipeline

A modular, end-to-end data pipeline framework supporting multiple orchestrators (Airflow 3.0, Airflow 2.x, Kestra) and data sources. This framework integrates with a variety of tools including dbt, Kafka, MinIO, Trino, and DuckDB to provide a flexible and comprehensive data engineering solution.

## Features

- **Multiple Orchestrators**: 
  - Apache Airflow 3.0 with AssetWatcher (event-driven triggers)
  - Apache Airflow 2.x compatibility
  - Kestra workflow engine (declarative YAML-based pipeline definition)

- **Streaming Capabilities**:
  - Kafka integration for real-time data processing
  - Flink for stream processing

- **Data Storage**:
  - PostgreSQL for relational data
  - DuckDB for analytics
  - MinIO (S3-compatible) for object storage
  - Trino for federated queries

- **Transformation**:
  - dbt models for data transformations
  - SQL-based data modeling

- **Infrastructure as Code**:
  - Docker Compose for local development
  - Terraform for cloud deployment
  - GitHub Actions for CI/CD

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.10+
- Git

### Setup Options

Choose the environment that matches your needs:

#### General Development Environment
```bash
# On Linux/macOS
./scripts/setup_dev_environment.sh

# On Windows PowerShell
.\scripts\setup_dev_environment.ps1
```

#### Airflow 3.0 Environment
```bash
# On Linux/macOS
./scripts/setup_airflow3_environment.sh

# On Windows PowerShell
# Use equivalent PowerShell script
```

#### Kestra Environment
```bash
# On Linux/macOS
./scripts/setup_kestra_environment.sh

# On Windows PowerShell
# Use equivalent PowerShell script
```

### Run with Docker Compose

Start all services:

```bash
docker-compose up -d
```

Access the different services:
- Airflow UI: http://localhost:8081
- Kestra UI: http://localhost:8083
- Trino UI: http://localhost:8080
- MinIO Console: http://localhost:9001
- Kafka UI: http://localhost:8089

## Architecture

The pipeline supports multiple data sources and destinations through a common framework:

```
Data Sources                Orchestration               Data Destination
┌───────────┐               ┌───────────┐               ┌───────────┐
│  GTFS RT  │──┐            │           │            ┌──│PostgreSQL │
└───────────┘  │            │           │            │  └───────────┘
               │            │           │            │
┌───────────┐  │            │  Airflow  │            │  ┌───────────┐
│  NBA API  │──┼────────────┤    or     ├────────────┼──│  DuckDB   │
└───────────┘  │            │  Kestra   │            │  └───────────┘
               │            │           │            │
┌───────────┐  │            │           │            │  ┌───────────┐
│  Weather  │──┘            │           │            └──│   MinIO   │
└───────────┘               └───────────┘               └───────────┘
```

## Project Structure

```
data_engineering_realtime_pipelin/
├── src/
│   ├── orchestrators/
│   │   ├── airflow/           # Airflow DAGs and config
│   │   ├── dbt/               # dbt models 
│   │   └── kestra/            # Kestra flows
│   ├── infrastructure/
│   │   └── docker/            # Docker files and configs
├── terraform/                 # IaC for cloud deployment
├── scripts/                   # Setup and utility scripts
├── docker-compose.yml         # Local development services
└── pyproject.toml             # Project dependencies
```

## Environments and Dependencies

This project uses `pyproject.toml` to manage dependencies for different environments:

- **Development**: `pip install -e ".[development]"`
- **Airflow 3.0**: `pip install -e ".[airflow3_dev]"`
- **Airflow 2.x**: `pip install -e ".[airflow2_dev]"`
- **Kestra**: `pip install -e ".[kestra_dev]"`

Each environment has its own setup script in the `scripts/` directory.

## Running Pipelines

### Airflow Pipelines

The project includes several example DAGs:

- `nba_ingest_pipeline.py`: Processes NBA data with AssetWatcher
- `weather_kafka_pipeline.py`: Processes weather data from Kafka
- `gtfs_data_pipeline.py`: Processes transit data

To trigger a pipeline, either:
1. Wait for the scheduled execution
2. Trigger manually from the Airflow UI
3. Create the appropriate event file (for AssetWatcher DAGs)

#### Triggering DAGs from the Airflow UI

Once your Airflow webserver and scheduler are running (e.g., via Docker Compose), triggering a DAG is entirely handled through the **Airflow UI**:

##### 1. Accessing the Airflow UI

1. Ensure your `airflow-webserver` and `airflow-scheduler` containers are **healthy** and **running**:

   ```bash
   docker-compose up -d airflow-webserver airflow-scheduler
   ```

   Confirm via:

   ```bash
   docker ps
   ```

2. Open your browser to **[http://localhost:8080/](http://localhost:8080/)** (or the port specified in your configuration).
   The default login is `admin`/`admin` for most Docker setups.

##### 2. Navigating to the DAGs List

* Click **DAGs** in the left sidebar to open the **DAG List View**.
* You'll see a list of available DAGs with their status, schedule, and actions.
* Use the **Pause/Play toggle** to pause or unpause a DAG. Paused DAGs won't execute on schedule but can still be triggered manually.

##### 3. Triggering a DAG Manually

###### Simple Trigger:
1. In the **Links** column of your DAG row, click the **▶** (Trigger DAG) icon.
2. A confirmation modal appears; click **Trigger**.
3. This enqueues an immediate **DAG run** outside of its schedule.

###### Trigger with Configuration:
If your DAG accepts parameters:

1. Ensure `core.dag_run_conf_overrides_params = True` in `airflow.cfg` to allow UI overrides.
2. Click the **•••** menu and select **Trigger DAG w/ config**.
3. Fill out the JSON configuration form that appears—e.g.,:

   ```json
   {
     "run_date": "2025-05-01T00:00:00",
     "batch_size": 500
   }
   ```
4. Click **Trigger** to start a parameterized run.

##### 4. Monitoring the Triggered Run

After triggering, you can track your run via:

1. **Runs Tab**
   * Click on your DAG name to open the **DAG Details Page**.
   * Select the **Runs** tab to see your newly created run, its **Run Type** (Manual), **Logical Date**, and **State**.

2. **Grid View**
   * In **Grid** or **Graph** view, click the column corresponding to your run.
   * Colored cells indicate task status (Success, Running, Failed). Hover to see logs or clear retries.

##### 5. Tips and CLI Alternatives

* If you need to use the CLI inside Docker:

  ```bash
  docker exec -it airflow-webserver airflow dags list
  docker exec -it airflow-webserver airflow dags trigger <DAG_ID>
  ```

* **Asset-Triggered DAGs**: Asset-driven DAGs show a **dataset icon** instead of ▶; clicking the icon surfaces asset runs.
* **Auditability**: Manual runs are tagged as `manual__<timestamp>` in the **Run ID** column.

### Kestra Pipelines

Kestra flows are defined in YAML and are located in `src/orchestrators/kestra/flows/`.

To run a Kestra flow:
1. Access the Kestra UI at http://localhost:8083
2. Navigate to the flow you want to run
3. Click "Execute"

### dbt Transformations

dbt models are run either:
1. As part of a pipeline (Airflow or Kestra)
2. Directly using the dbt command line:

```bash
cd src/orchestrators/dbt
dbt run --profiles-dir .
```

## Contributing

1. Set up the development environment
2. Use pre-commit hooks to maintain code quality
3. Follow the single-responsibility principle for files
4. Add tests for new functionality

## License

MIT 