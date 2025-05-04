# Data Engineering Realtime Pipeline

A modern real-time data engineering pipeline using MTA Bus Time GTFS-Realtime feed. This project demonstrates ingestion, processing, storage, querying, and visualization of bus data.

## What We've Built

- **GTFS-Realtime Data Ingestion**: Set up a resilient Python producer that fetches MTA Bus Time data and publishes it to Kafka topics, with proper error handling and dead-letter queues.
- **Stream Processing Infrastructure**: Configured a complete streaming infrastructure with Kafka, Flink, and Trino using Docker Compose.
- **Storage Layer**: Implemented Iceberg tables via MinIO (S3-compatible storage) for efficient time-series data storage.
- **Query Engine**: Set up Trino for SQL analytics on the processed data.
- **Local Development**: Enabled DuckDB-based local development for rapid prototyping and data exploration.
- **Documentation**: Created comprehensive documentation and setup instructions for easy onboarding.

## Architecture

The pipeline follows this architecture:

1. **Ingestion**: MTA GTFS-Realtime API → Python Producer → Kafka
2. **Processing**: Kafka → Apache Flink (stream processing)
3. **Storage**: Flink → Apache Iceberg (data lake)
4. **Query**: Trino SQL (analytics queries on Iceberg tables)
5. **Visualization**: Superset (dashboards) or Jupyter (exploration)

## Technology Stack

- **Apache Kafka**: Message streaming platform
- **Apache Flink**: Stream processing framework
- **Apache Iceberg**: Table format for data lakes
- **Trino**: Distributed SQL query engine
- **Apache Superset**: Data visualization and dashboarding
- **MinIO**: S3-compatible object storage
- **DuckDB**: Local analytical database
- **Python**: For data processing and pipeline components
- **Docker**: Containerization of all components

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.10+
- MTA API Key (register at https://api.mta.info/)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/data-engineering-realtime-pipeline.git
cd data-engineering-realtime-pipeline
```

2. Create a `.env.engineering` file with the following variables:
```
MTA_API_KEY=your_api_key_here
MTA_FEED_URL=https://gtfsrt.prod.obanyc.com/vehiclePositions?key=${MTA_API_KEY}
KAFKA_BROKER=localhost:29092
KAFKA_TOPIC=vehicle_positions
DLQ_TOPIC=vehicle_positions_dlq
POLL_INTERVAL=15
BACKOFF_BASE=1
BACKOFF_MAX=300
```

3. Install the required packages:
```bash
pip install -e .
```

4. Start the services using Docker Compose:
```bash
docker-compose up -d
```

### Running the Pipeline

1. Start the GTFS-Realtime producer:
```bash
python scripts/stream_gtfs.py
```

2. Access the various components:
   - Kafka Control Center: http://localhost:9021
   - Flink Dashboard: http://localhost:8081
   - MinIO Console: http://localhost:9001 (login with minio/minio123)
   - Trino UI: http://localhost:8080

## Project Structure

```
data_engineering_realtime_pipeline/
├── README.md                    # Project overview, setup guide, findings
├── pyproject.toml               # Dependencies and project configuration
├── docker-compose.yml           # Local infrastructure setup
├── mta_gtfs_realtime_prediction.ipynb  # GTFS-RT pipeline notebook
├── .env.example                 # Template for environment variables
├── scripts/                     # Utility scripts
│   └── stream_gtfs.py           # GTFS data producer for Kafka
├── src/                         # Source code
│   └── real_time_pipeline/      # Main pipeline module
├── trino/                       # Trino configuration
│   └── catalog/                 # Catalog definitions
```

## Local Development with DuckDB

The project also supports a local-first development workflow using DuckDB:

1. Load data for analysis:
```python
import duckdb
con = duckdb.connect('nyc_taxi.duckdb')
con.execute("CREATE TABLE vehicle_positions AS SELECT * FROM read_parquet('data/vehicle_positions.parquet')")
```

2. Run analytics queries:
```python
results = con.execute("""
SELECT 
    route_id,
    DATE_TRUNC('hour', timestamp) as hour,
    COUNT(*) as position_count,
    AVG(speed) as avg_speed
FROM vehicle_positions
GROUP BY 1, 2
ORDER BY 1, 2
""").fetchdf()
```

## Security Notes

- Never commit `.env*` files containing API keys or credentials to Git
- Rotate MinIO credentials in production environments
- Use proper IAM roles when deploying to cloud environments

## Future Enhancements

- Add Flink SQL examples for real-time analytics
- Implement dbt for transformations
- Deploy to cloud using Terraform
- Add CI/CD pipeline
- Enhance with machine learning predictions

## License

This project is licensed under the MIT License - see the LICENSE file for details. 