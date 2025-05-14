#!/usr/bin/env python3
"""
GTFS-Realtime Fetcher

This module can be used in multiple environments:
- Standalone script to fetch GTFS-RT data and output as JSON/Parquet
- AWS Lambda handler to fetch and store to S3
- GCP Cloud Function to fetch and store to BigQuery/GCS
- Azure Function to fetch and store to Blob Storage/Cosmos DB
- Component in an Airflow DAG

Requirements: 
- requests
- gtfs-realtime-bindings
- google-protobuf
"""

import os
import time
import json
import logging
import requests
from typing import Dict, List, Optional, Union, Any

# Optional imports based on environment
try:
    from google.transit import gtfs_realtime_pb2
    from google.protobuf import json_format
    GTFS_PB_AVAILABLE = True
except ImportError:
    GTFS_PB_AVAILABLE = False
    logging.warning("GTFS Protobuf libraries not available. Install with: pip install gtfs-realtime-bindings")

# Cloud-specific imports - only attempt if needed
def get_s3_client():
    """Get boto3 S3 client if available"""
    try:
        import boto3
        return boto3.client('s3')
    except ImportError:
        logging.warning("boto3 not available. Install with: pip install boto3")
        return None

def get_gcp_storage():
    """Get Google Cloud Storage client if available"""
    try:
        from google.cloud import storage
        return storage.Client()
    except ImportError:
        logging.warning("google-cloud-storage not available. Install with: pip install google-cloud-storage")
        return None

def get_bigquery():
    """Get BigQuery client if available"""
    try:
        from google.cloud import bigquery
        return bigquery.Client()
    except ImportError:
        logging.warning("google-cloud-bigquery not available. Install with: pip install google-cloud-bigquery")
        return None

def get_azure_blob():
    """Get Azure Blob client if available"""
    try:
        from azure.storage.blob import BlobServiceClient
        conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        if conn_str:
            return BlobServiceClient.from_connection_string(conn_str)
        return None
    except ImportError:
        logging.warning("azure-storage-blob not available. Install with: pip install azure-storage-blob")
        return None

def get_duckdb():
    """Get DuckDB client if available"""
    try:
        import duckdb
        return duckdb.connect(os.environ.get("DUCKDB_PATH", "gtfs_data.duckdb"))
    except ImportError:
        logging.warning("duckdb not available. Install with: pip install duckdb")
        return None

class GTFSFetcher:
    """Fetch GTFS-Realtime data from any compatible feed"""
    
    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        """Initialize the fetcher with API details
        
        Args:
            api_url: The URL of the GTFS-RT feed
            api_key: API key if required by the feed
        
        If not provided, will check environment variables:
            GTFS_API_URL, GTFS_API_KEY
        """
        self.api_url = api_url or os.environ.get("GTFS_API_URL")
        self.api_key = api_key or os.environ.get("GTFS_API_KEY")
        
        if not self.api_url:
            logging.error("No API URL provided. Set api_url or GTFS_API_URL environment variable.")
            raise ValueError("No GTFS API URL provided")
        
        # Construct full URL with API key if provided
        if self.api_key and '?' not in self.api_url:
            self.full_url = f"{self.api_url}?key={self.api_key}"
        elif self.api_key:
            self.full_url = f"{self.api_url}&key={self.api_key}"
        else:
            self.full_url = self.api_url
    
    def fetch(self) -> bytes:
        """Fetch raw protobuf data from feed
        
        Returns:
            Raw binary protobuf data
        """
        try:
            response = requests.get(self.full_url, timeout=30)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            logging.error(f"Error fetching GTFS data: {e}")
            raise
    
    def fetch_and_parse(self) -> List[Dict]:
        """Fetch and parse GTFS-RT feed into Python dictionaries
        
        Returns:
            List of dictionaries representing GTFS entities
        """
        if not GTFS_PB_AVAILABLE:
            raise RuntimeError("GTFS Protobuf libraries not available")
        
        content = self.fetch()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(content)
        
        # Convert to Python dictionaries
        results = []
        timestamp = int(time.time())
        
        for entity in feed.entity:
            # Use protobuf's built-in JSON conversion
            entity_dict = json_format.MessageToDict(entity)
            
            # Add metadata
            entity_dict['_fetched_at'] = timestamp
            entity_dict['_source'] = self.api_url
            
            results.append(entity_dict)
            
        return results
    
    def save_to_s3(self, bucket: str, prefix: str = "", fmt: str = "json") -> str:
        """Save fetched data to AWS S3
        
        Args:
            bucket: S3 bucket name
            prefix: Optional prefix (folder) in bucket
            fmt: Format ('json' or 'parquet')
            
        Returns:
            S3 URI of saved file
        """
        s3 = get_s3_client()
        if not s3:
            raise RuntimeError("boto3 S3 client not available")
        
        data = self.fetch_and_parse()
        timestamp = int(time.time())
        
        if fmt == "json":
            # Save as JSONL with each entity on a line
            key = f"{prefix}/gtfs_{timestamp}.json"
            body = "\n".join(json.dumps(entity) for entity in data)
            s3.put_object(Bucket=bucket, Key=key, Body=body)
            return f"s3://{bucket}/{key}"
        
        elif fmt == "parquet":
            # Save as Parquet - requires pyarrow/pandas
            try:
                import pandas as pd
                key = f"{prefix}/gtfs_{timestamp}.parquet"
                
                # Convert to pandas DataFrame
                df = pd.DataFrame(data)
                
                # Save to a temp file then upload
                temp_file = f"/tmp/gtfs_{timestamp}.parquet"
                df.to_parquet(temp_file)
                
                with open(temp_file, 'rb') as f:
                    s3.put_object(Bucket=bucket, Key=key, Body=f)
                
                # Clean up temp file
                os.remove(temp_file)
                return f"s3://{bucket}/{key}"
            except ImportError:
                logging.error("pandas and pyarrow are required for parquet format")
                raise
        else:
            raise ValueError(f"Unsupported format: {fmt}")
    
    def save_to_gcs(self, bucket: str, prefix: str = "", fmt: str = "json") -> str:
        """Save fetched data to Google Cloud Storage
        
        Args:
            bucket: GCS bucket name
            prefix: Optional prefix (folder) in bucket
            fmt: Format ('json' or 'parquet')
            
        Returns:
            GCS URI of saved file
        """
        gcs = get_gcp_storage()
        if not gcs:
            raise RuntimeError("GCS client not available")
        
        data = self.fetch_and_parse()
        timestamp = int(time.time())
        
        bucket_obj = gcs.bucket(bucket)
        
        if fmt == "json":
            # Save as JSONL with each entity on a line
            blob_name = f"{prefix}/gtfs_{timestamp}.json"
            blob = bucket_obj.blob(blob_name)
            body = "\n".join(json.dumps(entity) for entity in data)
            blob.upload_from_string(body)
            return f"gs://{bucket}/{blob_name}"
        
        elif fmt == "parquet":
            try:
                import pandas as pd
                blob_name = f"{prefix}/gtfs_{timestamp}.parquet"
                blob = bucket_obj.blob(blob_name)
                
                # Convert to pandas DataFrame
                df = pd.DataFrame(data)
                
                # Save to a temp file then upload
                temp_file = f"/tmp/gtfs_{timestamp}.parquet"
                df.to_parquet(temp_file)
                
                blob.upload_from_filename(temp_file)
                
                # Clean up temp file
                os.remove(temp_file)
                return f"gs://{bucket}/{blob_name}"
            except ImportError:
                logging.error("pandas and pyarrow are required for parquet format")
                raise
        else:
            raise ValueError(f"Unsupported format: {fmt}")
    
    def save_to_bigquery(self, dataset: str, table: str) -> int:
        """Save fetched data directly to BigQuery
        
        Args:
            dataset: BigQuery dataset ID
            table: BigQuery table name
            
        Returns:
            Number of rows inserted
        """
        bq = get_bigquery()
        if not bq:
            raise RuntimeError("BigQuery client not available")
        
        data = self.fetch_and_parse()
        
        # Convert nested dictionaries to JSON strings for compatible insertion
        rows_to_insert = []
        for entity in data:
            row = {}
            for key, value in entity.items():
                if isinstance(value, dict):
                    row[key] = json.dumps(value)
                else:
                    row[key] = value
            rows_to_insert.append(row)
        
        table_ref = f"{dataset}.{table}"
        errors = bq.insert_rows_json(table_ref, rows_to_insert)
        
        if errors:
            logging.error(f"Errors inserting rows: {errors}")
            raise RuntimeError(f"Error inserting rows: {errors}")
        
        return len(rows_to_insert)
    
    def save_to_duckdb(self, table: str, db_path: Optional[str] = None) -> int:
        """Save fetched data to DuckDB (local or MotherDuck)
        
        Args:
            table: Table name to insert into
            db_path: Path to DuckDB file or MotherDuck URI
                     (e.g., "md:my_database")
            
        Returns:
            Number of rows inserted
        """
        conn = get_duckdb()
        if not conn:
            raise RuntimeError("DuckDB not available")
        
        # Reconnect to specified path if provided
        if db_path:
            conn.close()
            conn = duckdb.connect(db_path)
        
        data = self.fetch_and_parse()
        
        # Convert to a format DuckDB can ingest
        import pandas as pd
        df = pd.DataFrame(data)
        
        # Create table if it doesn't exist
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} AS 
            SELECT * FROM df WHERE 1=0
        """)
        
        # Insert data
        conn.execute(f"""
            INSERT INTO {table} 
            SELECT * FROM df
        """)
        
        # Optionally attach to MotherDuck
        if db_path and db_path.startswith("md:"):
            conn.execute("CALL sys.sync()")
        
        row_count = len(data)
        conn.close()
        return row_count

# AWS Lambda handler
def lambda_handler(event: Dict, context: Any) -> Dict:
    """AWS Lambda handler for GTFS fetcher
    
    Environment variables:
        GTFS_API_URL: The GTFS-RT feed URL
        GTFS_API_KEY: API key for the feed
        S3_BUCKET: Bucket to store results
        S3_PREFIX: Optional prefix in bucket
    
    Returns:
        Dict with execution info
    """
    # Configure from environment and event
    api_url = os.environ.get("GTFS_API_URL")
    api_key = os.environ.get("GTFS_API_KEY")
    
    bucket = os.environ.get("S3_BUCKET")
    prefix = os.environ.get("S3_PREFIX", "gtfs")
    fmt = os.environ.get("OUTPUT_FORMAT", "json")
    
    if not bucket:
        raise ValueError("S3_BUCKET environment variable must be set")
    
    # Initialize and run
    start_time = time.time()
    fetcher = GTFSFetcher(api_url, api_key)
    
    try:
        location = fetcher.save_to_s3(bucket, prefix, fmt)
        
        # Return execution summary
        return {
            "statusCode": 200,
            "executionTime": time.time() - start_time,
            "location": location,
            "message": "GTFS data saved successfully"
        }
    except Exception as e:
        logging.exception("Error in Lambda execution")
        return {
            "statusCode": 500,
            "executionTime": time.time() - start_time,
            "error": str(e),
            "message": "Error saving GTFS data"
        }

# GCP Cloud Function handler
def gcp_function(request):
    """GCP Cloud Function handler for GTFS fetcher
    
    Environment variables:
        GTFS_API_URL: The GTFS-RT feed URL
        GTFS_API_KEY: API key for the feed
        GCS_BUCKET: GCS bucket name for storage
        GCS_PREFIX: Optional prefix in bucket
    
    Returns:
        JSON response with execution info
    """
    # Configure from environment
    api_url = os.environ.get("GTFS_API_URL")
    api_key = os.environ.get("GTFS_API_KEY")
    
    bucket = os.environ.get("GCS_BUCKET")
    prefix = os.environ.get("GCS_PREFIX", "gtfs")
    fmt = os.environ.get("OUTPUT_FORMAT", "json")
    
    # Option to save directly to BigQuery
    dataset = os.environ.get("BQ_DATASET")
    table = os.environ.get("BQ_TABLE")
    
    if not bucket and not (dataset and table):
        return {"error": "Either GCS_BUCKET or BQ_DATASET and BQ_TABLE must be set"}, 400
    
    # Initialize and run
    start_time = time.time()
    fetcher = GTFSFetcher(api_url, api_key)
    
    try:
        # Save to GCS if bucket is configured
        location = None
        if bucket:
            location = fetcher.save_to_gcs(bucket, prefix, fmt)
        
        # Save to BigQuery if configured
        rows_inserted = 0
        if dataset and table:
            rows_inserted = fetcher.save_to_bigquery(dataset, table)
        
        # Return execution summary
        return {
            "status": "success",
            "executionTime": time.time() - start_time,
            "location": location,
            "rowsInserted": rows_inserted,
            "message": "GTFS data saved successfully"
        }
    except Exception as e:
        logging.exception("Error in Cloud Function execution")
        return {
            "status": "error",
            "executionTime": time.time() - start_time,
            "error": str(e),
            "message": "Error saving GTFS data"
        }, 500

# Azure Function handler
def azure_function(req):
    """Azure Function handler for GTFS fetcher
    
    Environment variables:
        GTFS_API_URL: The GTFS-RT feed URL
        GTFS_API_KEY: API key for the feed
        AZURE_STORAGE_CONNECTION_STRING: Connection string for Azure Storage
        AZURE_CONTAINER: Blob container name
        AZURE_PREFIX: Optional prefix in container
    
    Returns:
        JSON response with execution info
    """
    import azure.functions as func
    
    # Configure from environment
    api_url = os.environ.get("GTFS_API_URL")
    api_key = os.environ.get("GTFS_API_KEY")
    
    container = os.environ.get("AZURE_CONTAINER")
    prefix = os.environ.get("AZURE_PREFIX", "gtfs")
    
    if not container:
        return func.HttpResponse(
            json.dumps({"error": "AZURE_CONTAINER environment variable must be set"}),
            status_code=400,
            mimetype="application/json"
        )
    
    # Initialize blob client
    blob_client = get_azure_blob()
    if not blob_client:
        return func.HttpResponse(
            json.dumps({"error": "Azure Blob client not available or not configured"}),
            status_code=500,
            mimetype="application/json"
        )
    
    # Initialize and run
    start_time = time.time()
    fetcher = GTFSFetcher(api_url, api_key)
    
    try:
        data = fetcher.fetch_and_parse()
        timestamp = int(time.time())
        
        # Save as JSONL
        blob_name = f"{prefix}/gtfs_{timestamp}.json"
        container_client = blob_client.get_container_client(container)
        blob_client = container_client.get_blob_client(blob_name)
        
        body = "\n".join(json.dumps(entity) for entity in data)
        blob_client.upload_blob(body)
        
        # Return execution summary
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "executionTime": time.time() - start_time,
                "location": f"https://{blob_client.account_name}.blob.core.windows.net/{container}/{blob_name}",
                "message": "GTFS data saved successfully"
            }),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.exception("Error in Azure Function execution")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "executionTime": time.time() - start_time,
                "error": str(e),
                "message": "Error saving GTFS data"
            }),
            status_code=500,
            mimetype="application/json"
        )

# Main entrypoint for local execution
if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    parser = argparse.ArgumentParser(description="GTFS-RT Data Fetcher")
    parser.add_argument("--url", help="GTFS-RT feed URL")
    parser.add_argument("--key", help="API key for the feed")
    parser.add_argument("--output", help="Output file path or location URI")
    parser.add_argument("--format", choices=["json", "parquet"], default="json", help="Output format")
    parser.add_argument("--cloud", choices=["aws", "gcp", "azure", "duckdb"], help="Cloud provider")
    parser.add_argument("--bucket", help="S3 or GCS bucket name")
    parser.add_argument("--prefix", default="gtfs", help="Prefix in bucket/container")
    parser.add_argument("--dataset", help="BigQuery dataset (GCP only)")
    parser.add_argument("--table", help="BigQuery or DuckDB table name")
    parser.add_argument("--db-path", help="DuckDB database path or MotherDuck URI (e.g., md:my_db)")
    
    args = parser.parse_args()
    
    # Use args or fall back to environment variables
    api_url = args.url or os.environ.get("GTFS_API_URL")
    api_key = args.key or os.environ.get("GTFS_API_KEY")
    
    if not api_url:
        parser.error("GTFS-RT feed URL is required (--url or GTFS_API_URL env var)")
    
    fetcher = GTFSFetcher(api_url, api_key)
    
    try:
        # Determine output destination
        if args.cloud == "aws":
            bucket = args.bucket or os.environ.get("S3_BUCKET")
            if not bucket:
                parser.error("S3 bucket is required (--bucket or S3_BUCKET env var)")
                
            location = fetcher.save_to_s3(bucket, args.prefix, args.format)
            logging.info(f"GTFS data saved to {location}")
            
        elif args.cloud == "gcp":
            bucket = args.bucket or os.environ.get("GCS_BUCKET")
            dataset = args.dataset or os.environ.get("BQ_DATASET")
            table = args.table or os.environ.get("BQ_TABLE")
            
            if bucket:
                location = fetcher.save_to_gcs(bucket, args.prefix, args.format)
                logging.info(f"GTFS data saved to {location}")
                
            if dataset and table:
                rows = fetcher.save_to_bigquery(dataset, table)
                logging.info(f"GTFS data saved to BigQuery {dataset}.{table} ({rows} rows)")
                
            if not bucket and not (dataset and table):
                parser.error("Either GCS bucket or BigQuery dataset+table is required")
                
        elif args.cloud == "azure":
            container = args.bucket or os.environ.get("AZURE_CONTAINER")
            if not container:
                parser.error("Azure container is required (--bucket or AZURE_CONTAINER env var)")
                
            # This would use the azure_function handler but adapted for CLI
            # Simplified implementation for now
            logging.info("Azure blob implementation via CLI not yet supported")
            data = fetcher.fetch_and_parse()
            logging.info(f"Fetched {len(data)} GTFS entities")
                
        elif args.cloud == "duckdb":
            table = args.table
            if not table:
                parser.error("Table name is required for DuckDB (--table)")
                
            rows = fetcher.save_to_duckdb(table, args.db_path)
            db_path = args.db_path or os.environ.get("DUCKDB_PATH", "gtfs_data.duckdb")
            logging.info(f"GTFS data saved to DuckDB table {table} in {db_path} ({rows} rows)")
                
        else:
            # Just fetch and output to file or stdout
            data = fetcher.fetch_and_parse()
            
            if args.output:
                # Save to file
                if args.format == "json":
                    with open(args.output, "w") as f:
                        json.dump(data, f)
                elif args.format == "parquet":
                    try:
                        import pandas as pd
                        df = pd.DataFrame(data)
                        df.to_parquet(args.output)
                    except ImportError:
                        logging.error("pandas and pyarrow are required for parquet format")
                        raise
                logging.info(f"GTFS data saved to {args.output}")
            else:
                # Output to stdout
                print(json.dumps(data, indent=2))
                
    except Exception as e:
        logging.exception("Error fetching or saving GTFS data")
        exit(1) 