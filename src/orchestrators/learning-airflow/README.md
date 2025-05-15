

# Airflow Learning Project

This project demonstrates best practices for creating modular, maintainable Airflow DAGs using Airflow 3.0's TaskFlow API and AssetWatcher for event-driven scheduling.

## Project Structure

```
learning-airflow/
├── dags/                     # DAG definition files 
│   ├── example_etl_galaxies.py     # Example ETL DAG that processes galaxy data
│   ├── gtfs_data_pipeline.py       # DAG that processes GTFS realtime transit data
│   ├── nba_ingest_pipeline.py      # DAG that processes NBA game data
│   ├── user_metrics_etl.py         # Simple ETL DAG example for user metrics
│   └── weather_kafka_pipeline.py   # DAG that processes weather data from Kafka
├── include/                  # Shared code and resources
│   ├── custom_functions/          # Modularized DAG functions
│   │   ├── galaxy_functions.py     # Functions for galaxy data processing
│   │   ├── gtfs_functions.py       # Functions for GTFS data processing
│   │   ├── nba_functions.py        # Functions for NBA data processing
│   │   ├── user_metrics_functions.py # Functions for user metrics processing
│   │   └── weather_functions.py    # Functions for weather data processing
│   ├── data/                      # Sample data files
│   └── astronomy.db               # DuckDB database for the example DAG
├── tests/                    # Test files
├── .astro/                   # Astro CLI configuration
├── Dockerfile                # Custom Dockerfile for this project
├── packages.txt              # System-level dependencies
├── README.md                 # This file
└── requirements.txt          # Python dependencies
```

## DAG Modularization

Each DAG in this project follows best practices for code organization:

1. **Separation of concerns**: Core data processing logic is separated from DAG flow definition
2. **Modular functions**: Each DAG has corresponding helper functions in `include/custom_functions/`
3. **Reusable components**: Common patterns are extracted into helper classes
4. **Well-documented**: DAGs and functions include descriptive docstrings

## Example DAGs

### Galaxy ETL Example

A simple ETL pipeline that extracts galaxy data, filters based on distance, and loads into a DuckDB database.

```python
# Use like this:
from include.custom_functions.galaxy_functions import get_galaxy_data
```

### GTFS Data Pipeline

Processes GTFS Realtime transit data with different storage backends (S3, BigQuery, Azure, DuckDB).

```python
# Use like this:
from include.custom_functions.gtfs_functions import GTFSProcessor
```

### NBA Ingest Pipeline

Demonstrates event-driven processing with AssetWatcher, fetching NBA game data and loading into PostgreSQL.

```python
# Use like this:
from include.custom_functions.nba_functions import NBAProcessor
```

### User Metrics ETL

Simple ETL example for processing user metrics.

```python
# Use like this:
from include.custom_functions.user_metrics_functions import UserMetricsProcessor
```

### Weather Kafka Pipeline

Shows how to consume Kafka messages, process weather data, and save to PostgreSQL with analytics.

```python
# Use like this:
from include.custom_functions.weather_functions import WeatherProcessor
```

## Running the DAGs

### Using Astro CLI

This project is configured for the Astro CLI, making it easy to run locally:

```bash
# Start the project
astro dev start

# Access the Airflow UI
# Open http://localhost:8080 in your browser
# Default credentials: admin/admin
```

### Using Docker

You can also run the project using Docker directly:

```bash
docker-compose up -d
```

### Environment Variables

Environment variables can be set in a `.env` file at the project root or passed to the Airflow containers.

## Testing

Execute tests using the following commands:

```bash
# Run all tests
astro dev pytest

# Run a specific test
astro dev pytest tests/dags/test_dag_example.py
```

## Contributing

When adding a new DAG:

1. Create a new DAG file in the `dags/` directory
2. Create a module with helper functions in `include/custom_functions/`
3. Add tests in the `tests/` directory
4. Update this README with relevant information

## License

This project is licensed under the MIT License.
