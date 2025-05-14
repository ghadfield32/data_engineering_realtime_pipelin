#!/usr/bin/env python3
"""
NBA Stats API Fetcher

This module provides a reusable fetcher for NBA stats data from public APIs.
It supports multiple environments:
- Standalone script to fetch NBA data and output as JSON/Parquet
- AWS Lambda handler to fetch and store to S3
- GCP Cloud Function to fetch and store to BigQuery/GCS
- Azure Function to fetch and store to Blob Storage/Cosmos DB
- Component in an Airflow DAG

Available endpoints from the Balldontlie API:
- games: Game data with scores and basic stats
- players: Player information
- stats: Player stats for specific games
- teams: Team information
- season_averages: Player averages for specific seasons

Requirements: 
- requests
- pandas (optional, for DataFrame operations)
"""

import os
import time
import json
import logging
import requests
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta

# Cloud-specific imports defined on-demand in helper functions
# (Same pattern as in fetch_gtfs.py)

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
        return duckdb.connect(os.environ.get("DUCKDB_PATH", "nba_data.duckdb"))
    except ImportError:
        logging.warning("duckdb not available. Install with: pip install duckdb")
        return None


class NBAStatsFetcher:
    """Fetch NBA stats from public APIs"""
    
    # Balldontlie API base URL
    BALLDONTLIE_API = "https://www.balldontlie.io/api/v1"
    
    # Alternative API (NBA API) - requires separate setup
    NBA_API_ENABLED = False
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the NBA stats fetcher
        
        Args:
            api_key: Optional API key (for rate-limited APIs)
        
        Note: 
            Will fall back to environment variable NBA_API_KEY if not provided
        """
        self.api_key = api_key or os.environ.get("NBA_API_KEY")
        
        # Try to load NBA API if available (optional)
        try:
            from nba_api.stats import endpoints
            self.nba_api_endpoints = endpoints
            self.NBA_API_ENABLED = True
        except ImportError:
            self.NBA_API_ENABLED = False
            logging.info("NBA API package not available. Using Balldontlie API only.")
    
    def fetch_games(self, season: Optional[int] = None, team_ids: Optional[List[int]] = None, 
                   start_date: Optional[str] = None, end_date: Optional[str] = None,
                   page: int = 1, per_page: int = 100) -> Dict:
        """Fetch games data from Balldontlie API
        
        Args:
            season: NBA season year (e.g., 2021 for 2021-2022 season)
            team_ids: List of team IDs to filter
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            page: Page number for pagination
            per_page: Items per page (max 100)
            
        Returns:
            Dict with games data and metadata
        """
        params = {
            'page': page,
            'per_page': min(per_page, 100)  # API max is 100
        }
        
        # Add optional filters
        if season:
            params['seasons[]'] = season
        
        if team_ids:
            for team_id in team_ids:
                params.setdefault('team_ids[]', []).append(team_id)
        
        if start_date:
            params['start_date'] = start_date
            
        if end_date:
            params['end_date'] = end_date
        
        url = f"{self.BALLDONTLIE_API}/games"
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def fetch_players(self, search: Optional[str] = None, 
                     page: int = 1, per_page: int = 100) -> Dict:
        """Fetch players data from Balldontlie API
        
        Args:
            search: Search term for player names
            page: Page number for pagination
            per_page: Items per page (max 100)
            
        Returns:
            Dict with player data and metadata
        """
        params = {
            'page': page,
            'per_page': min(per_page, 100)  # API max is 100
        }
        
        if search:
            params['search'] = search
        
        url = f"{self.BALLDONTLIE_API}/players"
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def fetch_team_stats(self, team_id: int, season: Optional[int] = None) -> Dict:
        """Fetch team stats using NBA API (if available)
        
        Args:
            team_id: Team ID 
            season: Season year (e.g., 2021 for 2021-22 season)
            
        Returns:
            Dict with team stats data
            
        Raises:
            RuntimeError: If NBA API is not available
        """
        if not self.NBA_API_ENABLED:
            raise RuntimeError("NBA API package not installed. Install with: pip install nba_api")
        
        # Default to latest season if not specified
        if not season:
            current_year = datetime.now().year
            current_month = datetime.now().month
            # NBA seasons typically start in October
            season = current_year if current_month >= 10 else current_year - 1
        
        season_str = f"{season}-{str(season + 1)[-2:]}"  # Format: "2021-22"
        
        team_stats = self.nba_api_endpoints.teamdashboardbygeneralsplits.TeamDashboardByGeneralSplits(
            team_id=team_id,
            season=season_str,
            measure_type_detailed_defense="Base"
        )
        
        return team_stats.get_dict()
    
    def fetch_season_averages(self, season: int, player_ids: List[int]) -> Dict:
        """Fetch season averages for specific players
        
        Args:
            season: Season year (e.g., 2021 for 2021-22 season)
            player_ids: List of player IDs to get averages for
            
        Returns:
            Dict with season averages data
        """
        params = {
            'season': season
        }
        
        for player_id in player_ids:
            params.setdefault('player_ids[]', []).append(player_id)
        
        url = f"{self.BALLDONTLIE_API}/season_averages"
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def fetch_all_games_for_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """Fetch all games within a date range, handling pagination
        
        Args:
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            
        Returns:
            List of game data dictionaries
        """
        all_games = []
        page = 1
        per_page = 100
        
        while True:
            response = self.fetch_games(
                start_date=start_date,
                end_date=end_date,
                page=page,
                per_page=per_page
            )
            
            games = response.get('data', [])
            all_games.extend(games)
            
            # Check if we need to fetch more pages
            meta = response.get('meta', {})
            total_pages = meta.get('total_pages', 1)
            
            if page >= total_pages or not games:
                break
                
            page += 1
            # Be nice to the API and avoid rate limits
            time.sleep(1)
        
        return all_games
    
    # Storage methods similar to GTFS fetcher
    def save_to_s3(self, data: Dict, bucket: str, prefix: str = "", 
                 dataset_name: str = "nba_data", fmt: str = "json") -> str:
        """Save fetched data to AWS S3
        
        Args:
            data: Data to save
            bucket: S3 bucket name
            prefix: Optional prefix (folder) in bucket
            dataset_name: Name for the dataset file
            fmt: Format ('json' or 'parquet')
            
        Returns:
            S3 URI of saved file
        """
        s3 = get_s3_client()
        if not s3:
            raise RuntimeError("boto3 S3 client not available")
        
        timestamp = int(time.time())
        
        if fmt == "json":
            key = f"{prefix}/{dataset_name}_{timestamp}.json"
            body = json.dumps(data)
            s3.put_object(Bucket=bucket, Key=key, Body=body)
            return f"s3://{bucket}/{key}"
        
        elif fmt == "parquet":
            try:
                import pandas as pd
                
                # Convert to DataFrame based on the structure of the data
                if isinstance(data, dict) and "data" in data:
                    # Handle API response format
                    df = pd.DataFrame(data["data"])
                elif isinstance(data, list):
                    # Handle list of dicts
                    df = pd.DataFrame(data)
                else:
                    # Try to flatten nested data as a last resort
                    df = pd.json_normalize(data)
                
                key = f"{prefix}/{dataset_name}_{timestamp}.parquet"
                temp_file = f"/tmp/{dataset_name}_{timestamp}.parquet"
                df.to_parquet(temp_file)
                
                with open(temp_file, 'rb') as f:
                    s3.put_object(Bucket=bucket, Key=key, Body=f)
                
                os.remove(temp_file)
                return f"s3://{bucket}/{key}"
            except ImportError:
                logging.error("pandas and pyarrow are required for parquet format")
                raise
            except Exception as e:
                logging.error(f"Error converting to DataFrame: {e}")
                raise
        else:
            raise ValueError(f"Unsupported format: {fmt}")
    
    def save_to_gcs(self, data: Dict, bucket: str, prefix: str = "", 
                  dataset_name: str = "nba_data", fmt: str = "json") -> str:
        """Save fetched data to Google Cloud Storage
        
        Args:
            data: Data to save
            bucket: GCS bucket name
            prefix: Optional prefix (folder) in bucket
            dataset_name: Name for the dataset file
            fmt: Format ('json' or 'parquet')
            
        Returns:
            GCS URI of saved file
        """
        gcs = get_gcp_storage()
        if not gcs:
            raise RuntimeError("GCS client not available")
        
        timestamp = int(time.time())
        bucket_obj = gcs.bucket(bucket)
        
        if fmt == "json":
            blob_name = f"{prefix}/{dataset_name}_{timestamp}.json"
            blob = bucket_obj.blob(blob_name)
            blob.upload_from_string(json.dumps(data))
            return f"gs://{bucket}/{blob_name}"
        
        elif fmt == "parquet":
            try:
                import pandas as pd
                
                # Convert to DataFrame based on the structure of the data
                if isinstance(data, dict) and "data" in data:
                    # Handle API response format
                    df = pd.DataFrame(data["data"])
                elif isinstance(data, list):
                    # Handle list of dicts
                    df = pd.DataFrame(data)
                else:
                    # Try to flatten nested data as a last resort
                    df = pd.json_normalize(data)
                
                blob_name = f"{prefix}/{dataset_name}_{timestamp}.parquet"
                blob = bucket_obj.blob(blob_name)
                
                temp_file = f"/tmp/{dataset_name}_{timestamp}.parquet"
                df.to_parquet(temp_file)
                
                blob.upload_from_filename(temp_file)
                os.remove(temp_file)
                
                return f"gs://{bucket}/{blob_name}"
            except ImportError:
                logging.error("pandas and pyarrow are required for parquet format")
                raise
            except Exception as e:
                logging.error(f"Error converting to DataFrame: {e}")
                raise
        else:
            raise ValueError(f"Unsupported format: {fmt}")
    
    def save_to_bigquery(self, data: Union[Dict, List], dataset: str, table: str) -> int:
        """Save fetched data directly to BigQuery
        
        Args:
            data: Data to save (dict with "data" key or list of records)
            dataset: BigQuery dataset ID
            table: BigQuery table name
            
        Returns:
            Number of rows inserted
        """
        bq = get_bigquery()
        if not bq:
            raise RuntimeError("BigQuery client not available")
        
        # Extract the actual data records
        if isinstance(data, dict) and "data" in data:
            records = data["data"]
        elif isinstance(data, list):
            records = data
        else:
            raise ValueError("Data must be a dict with 'data' key or a list of records")
        
        # Create records compatible with BigQuery schema
        rows_to_insert = []
        for record in records:
            # Process nested fields if needed
            processed_record = {}
            for key, value in record.items():
                if isinstance(value, (dict, list)):
                    processed_record[key] = json.dumps(value)
                else:
                    processed_record[key] = value
            rows_to_insert.append(processed_record)
        
        table_ref = f"{dataset}.{table}"
        errors = bq.insert_rows_json(table_ref, rows_to_insert)
        
        if errors:
            logging.error(f"Errors inserting rows: {errors}")
            raise RuntimeError(f"Error inserting rows: {errors}")
        
        return len(rows_to_insert)
    
    def save_to_duckdb(self, data: Union[Dict, List], table: str, db_path: Optional[str] = None) -> int:
        """Save fetched data to DuckDB (local or MotherDuck)
        
        Args:
            data: Data to save (dict with "data" key or list of records)
            table: Table name to insert into
            db_path: Path to DuckDB file or MotherDuck URI
                     (e.g., "md:my_database")
            
        Returns:
            Number of rows inserted
        """
        try:
            import duckdb
            import pandas as pd
        except ImportError:
            raise RuntimeError("DuckDB and pandas are required. Install with: pip install duckdb pandas")
        
        # Extract the actual data records
        if isinstance(data, dict) and "data" in data:
            records = data["data"]
        elif isinstance(data, list):
            records = data
        else:
            raise ValueError("Data must be a dict with 'data' key or a list of records")
        
        # Create DataFrame
        df = pd.DataFrame(records)
        
        # Connect to DuckDB
        conn = duckdb.connect(db_path or os.environ.get("DUCKDB_PATH", "nba_data.duckdb"))
        
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
        
        # Optionally sync to MotherDuck
        if db_path and db_path.startswith("md:"):
            conn.execute("CALL sys.sync()")
        
        row_count = len(records)
        conn.close()
        
        return row_count


# AWS Lambda handler
def lambda_handler(event: Dict, context: Any) -> Dict:
    """AWS Lambda handler for NBA stats fetcher
    
    Environment variables:
        NBA_API_KEY: Optional API key if needed
        S3_BUCKET: Bucket to store results
        S3_PREFIX: Optional prefix in bucket
        NBA_DATA_TYPE: Type of data to fetch (games, players, season_averages)
        
    Event params (examples):
        {'data_type': 'games', 'season': 2023}
        {'data_type': 'players', 'search': 'James'}
        {'data_type': 'season_averages', 'season': 2023, 'player_ids': [237673, 249]}
        
    Returns:
        Dict with execution info
    """
    # Configure from environment and event
    api_key = os.environ.get("NBA_API_KEY")
    bucket = os.environ.get("S3_BUCKET")
    prefix = os.environ.get("S3_PREFIX", "nba")
    fmt = os.environ.get("OUTPUT_FORMAT", "json")
    
    # Parameters from event
    data_type = event.get('data_type') or os.environ.get("NBA_DATA_TYPE", "games")
    
    if not bucket:
        raise ValueError("S3_BUCKET environment variable must be set")
    
    # Initialize fetcher
    start_time = time.time()
    fetcher = NBAStatsFetcher(api_key)
    
    try:
        # Fetch data based on type
        data = None
        dataset_name = f"nba_{data_type}"
        
        if data_type == "games":
            season = event.get('season')
            team_ids = event.get('team_ids')
            start_date = event.get('start_date')
            end_date = event.get('end_date')
            
            if start_date and end_date:
                data = fetcher.fetch_all_games_for_date_range(start_date, end_date)
            else:
                data = fetcher.fetch_games(season=season, team_ids=team_ids, 
                                        start_date=start_date, end_date=end_date)
        
        elif data_type == "players":
            search = event.get('search')
            data = fetcher.fetch_players(search=search)
        
        elif data_type == "season_averages":
            season = event.get('season')
            player_ids = event.get('player_ids', [])
            if not season:
                raise ValueError("Season parameter is required for season_averages")
            if not player_ids:
                raise ValueError("player_ids parameter is required for season_averages")
            
            data = fetcher.fetch_season_averages(season=season, player_ids=player_ids)
        
        else:
            raise ValueError(f"Unsupported data_type: {data_type}")
        
        # Save to S3
        location = fetcher.save_to_s3(data, bucket, prefix, dataset_name, fmt)
        
        # Return execution summary
        return {
            "statusCode": 200,
            "executionTime": time.time() - start_time,
            "dataType": data_type,
            "location": location,
            "message": "NBA data saved successfully"
        }
    except Exception as e:
        logging.exception("Error in Lambda execution")
        return {
            "statusCode": 500,
            "executionTime": time.time() - start_time,
            "error": str(e),
            "message": "Error fetching or saving NBA data"
        }

# GCP Cloud Function handler
def gcp_function(request):
    """GCP Cloud Function handler for NBA stats fetcher
    
    Environment variables:
        NBA_API_KEY: Optional API key if needed
        GCS_BUCKET: GCS bucket name (optional)
        GCS_PREFIX: Optional prefix in bucket
        BQ_DATASET: BigQuery dataset ID (optional)
        BQ_TABLE: BigQuery table name (optional)
        
    Request JSON params (examples):
        {'data_type': 'games', 'season': 2023}
        {'data_type': 'players', 'search': 'James'}
        
    Either GCS_BUCKET or both BQ_DATASET and BQ_TABLE must be set
        
    Returns:
        JSON response with execution info
    """
    # Configure from environment
    api_key = os.environ.get("NBA_API_KEY")
    
    # Storage options
    bucket = os.environ.get("GCS_BUCKET")
    prefix = os.environ.get("GCS_PREFIX", "nba")
    fmt = os.environ.get("OUTPUT_FORMAT", "json")
    
    dataset = os.environ.get("BQ_DATASET")
    table = os.environ.get("BQ_TABLE")
    
    if not bucket and not (dataset and table):
        return {"error": "Either GCS_BUCKET or BQ_DATASET and BQ_TABLE must be set"}, 400
    
    # Parse request
    try:
        request_json = request.get_json(silent=True)
        data_type = request_json.get('data_type', 'games')
    except:
        request_json = {}
        data_type = 'games'
    
    # Initialize fetcher
    start_time = time.time()
    fetcher = NBAStatsFetcher(api_key)
    
    try:
        # Fetch data based on type
        data = None
        dataset_name = f"nba_{data_type}"
        
        if data_type == "games":
            season = request_json.get('season')
            team_ids = request_json.get('team_ids')
            start_date = request_json.get('start_date')
            end_date = request_json.get('end_date')
            
            if start_date and end_date:
                data = fetcher.fetch_all_games_for_date_range(start_date, end_date)
            else:
                data = fetcher.fetch_games(season=season, team_ids=team_ids, 
                                       start_date=start_date, end_date=end_date)
        
        elif data_type == "players":
            search = request_json.get('search')
            data = fetcher.fetch_players(search=search)
        
        elif data_type == "season_averages":
            season = request_json.get('season')
            player_ids = request_json.get('player_ids', [])
            if not season:
                return {"error": "Season parameter is required for season_averages"}, 400
            if not player_ids:
                return {"error": "player_ids parameter is required for season_averages"}, 400
            
            data = fetcher.fetch_season_averages(season=season, player_ids=player_ids)
        
        else:
            return {"error": f"Unsupported data_type: {data_type}"}, 400
        
        # Save to storage
        location = None
        rows_inserted = 0
        
        if bucket:
            location = fetcher.save_to_gcs(data, bucket, prefix, dataset_name, fmt)
        
        if dataset and table:
            rows_inserted = fetcher.save_to_bigquery(data, dataset, table)
        
        # Return execution summary
        return {
            "status": "success",
            "executionTime": time.time() - start_time,
            "dataType": data_type,
            "location": location,
            "rowsInserted": rows_inserted,
            "message": "NBA data saved successfully"
        }
    except Exception as e:
        logging.exception("Error in Cloud Function execution")
        return {
            "status": "error",
            "executionTime": time.time() - start_time,
            "error": str(e),
            "message": "Error fetching or saving NBA data"
        }, 500

# Main entrypoint for local execution
if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    parser = argparse.ArgumentParser(description="NBA Stats Fetcher")
    parser.add_argument("--data-type", choices=["games", "players", "season_averages"], 
                     default="games", help="Type of data to fetch")
    parser.add_argument("--api-key", help="API key if needed")
    parser.add_argument("--season", type=int, help="NBA season year (e.g., 2023)")
    parser.add_argument("--team-ids", type=int, nargs="+", help="Team IDs to filter")
    parser.add_argument("--player-ids", type=int, nargs="+", help="Player IDs for season averages")
    parser.add_argument("--search", help="Search term for players")
    parser.add_argument("--start-date", help="Start date in YYYY-MM-DD format")
    parser.add_argument("--end-date", help="End date in YYYY-MM-DD format")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--format", choices=["json", "parquet"], default="json", help="Output format")
    parser.add_argument("--cloud", choices=["aws", "gcp", "azure", "duckdb"], help="Cloud provider")
    parser.add_argument("--bucket", help="S3 or GCS bucket name")
    parser.add_argument("--prefix", default="nba", help="Prefix in bucket")
    parser.add_argument("--dataset", help="BigQuery dataset (GCP only)")
    parser.add_argument("--table", help="Table name (BigQuery or DuckDB)")
    parser.add_argument("--db-path", help="DuckDB path or MotherDuck URI")
    
    args = parser.parse_args()
    
    # Initialize fetcher
    fetcher = NBAStatsFetcher(args.api_key)
    
    try:
        # Fetch data based on type
        data = None
        dataset_name = f"nba_{args.data_type}"
        
        if args.data_type == "games":
            if args.start_date and args.end_date:
                data = fetcher.fetch_all_games_for_date_range(args.start_date, args.end_date)
                logging.info(f"Fetched {len(data)} games from {args.start_date} to {args.end_date}")
            else:
                data = fetcher.fetch_games(season=args.season, team_ids=args.team_ids,
                                     start_date=args.start_date, end_date=args.end_date)
                logging.info(f"Fetched games data: {len(data.get('data', []))} records")
        
        elif args.data_type == "players":
            data = fetcher.fetch_players(search=args.search)
            logging.info(f"Fetched player data: {len(data.get('data', []))} records")
        
        elif args.data_type == "season_averages":
            if not args.season:
                parser.error("--season is required for season_averages")
            if not args.player_ids:
                parser.error("--player-ids is required for season_averages")
            
            data = fetcher.fetch_season_averages(season=args.season, player_ids=args.player_ids)
            logging.info(f"Fetched season averages: {len(data.get('data', []))} records")
        
        # Handle output based on arguments
        if args.cloud == "aws":
            if not args.bucket:
                parser.error("--bucket is required for AWS")
            
            location = fetcher.save_to_s3(data, args.bucket, args.prefix, dataset_name, args.format)
            logging.info(f"Data saved to {location}")
        
        elif args.cloud == "gcp":
            if not args.bucket and not (args.dataset and args.table):
                parser.error("Either --bucket or both --dataset and --table are required for GCP")
            
            if args.bucket:
                location = fetcher.save_to_gcs(data, args.bucket, args.prefix, dataset_name, args.format)
                logging.info(f"Data saved to {location}")
            
            if args.dataset and args.table:
                rows = fetcher.save_to_bigquery(data, args.dataset, args.table)
                logging.info(f"Data saved to BigQuery {args.dataset}.{args.table} ({rows} rows)")
        
        elif args.cloud == "duckdb":
            if not args.table:
                parser.error("--table is required for DuckDB")
            
            rows = fetcher.save_to_duckdb(data, args.table, args.db_path)
            db_path = args.db_path or os.environ.get("DUCKDB_PATH", "nba_data.duckdb")
            logging.info(f"Data saved to DuckDB table {args.table} in {db_path} ({rows} rows)")
        
        else:
            # Save to file or print to stdout
            if args.output:
                if args.format == "json":
                    with open(args.output, "w") as f:
                        json.dump(data, f, indent=2)
                elif args.format == "parquet":
                    try:
                        import pandas as pd
                        # Convert to DataFrame based on the structure
                        if "data" in data:
                            df = pd.DataFrame(data["data"])
                        else:
                            df = pd.DataFrame(data)
                        df.to_parquet(args.output)
                    except ImportError:
                        logging.error("pandas and pyarrow are required for parquet format")
                        raise
                
                logging.info(f"Data saved to {args.output}")
            else:
                print(json.dumps(data, indent=2))
    
    except Exception as e:
        logging.exception("Error fetching or saving NBA data")
        exit(1) 