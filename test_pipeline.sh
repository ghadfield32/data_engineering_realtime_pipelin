#!/bin/bash

# Setup environment file if it doesn't exist
if [ ! -f .env.engineering ]; then
    echo "Creating .env.engineering file..."
    cat > .env.engineering << EOL
# Environment variables for real-time engineering pipeline
# Replace these placeholders with actual values

# MTA GTFS-RT API settings
MTA_API_KEY=your_api_key_here
MTA_FEED_URL=http://gtfsrt.prod.obanyc.com/vehiclePositions?key=\${MTA_API_KEY}

# Kafka settings
KAFKA_BROKER=localhost:29092
KAFKA_TOPIC=vehicle_positions
DLQ_TOPIC=vehicle_positions_dlq

# Polling interval (seconds)
POLL_INTERVAL=15

# Backoff settings (seconds)
BACKOFF_BASE=1
BACKOFF_MAX=300

# Cloud provider config (aws, gcp, azure, motherduck)
CLOUD_PROVIDER=local
EOL
    echo "Created .env.engineering - please edit it to add your MTA API key"
    exit 1
fi

# Test if Docker is running
echo "Checking if Docker is running..."
docker ps > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Error: Docker is not running. Please start Docker and try again."
    exit 1
fi

echo "Docker is running!"

# Check if the required docker containers are running
echo "Checking if Kafka and Zookeeper are running..."
RUNNING_CONTAINERS=$(docker ps --format "{{.Names}}" | grep -E "kafka|zookeeper" | wc -l)
if [ $RUNNING_CONTAINERS -lt 2 ]; then
    echo "Starting Kafka and Zookeeper..."
    docker-compose up -d zookeeper kafka
else
    echo "Kafka and Zookeeper are already running."
fi

# Create Kafka topics if they don't exist
echo "Creating Kafka topics if they don't exist..."
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic vehicle_positions --partitions 1 --replication-factor 1
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic vehicle_positions_dlq --partitions 1 --replication-factor 1

# Install dependencies using uv
echo "Installing dependencies with uv..."
uv pip install -e ".[kafka]"

# Run the GTFS-RT stream
echo "Starting the GTFS-RT stream..."
python scripts/stream_gtfs.py 