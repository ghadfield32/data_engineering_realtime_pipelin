#!/usr/bin/env python3
"""
Weather API Fetcher

This module provides a reusable fetcher for weather data from free public APIs.
It supports multiple environments:
- Standalone script to fetch weather data and output as JSON/Parquet
- AWS Lambda handler to fetch and store to S3
- GCP Cloud Function to fetch and store to BigQuery/GCS
- Azure Function to fetch and store to Blob Storage/Cosmos DB
- Component in an Airflow DAG

Available APIs:
- Open-Meteo: Free weather API with no API key required
- OpenWeatherMap: Free tier available with API key

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
        return duckdb.connect(os.environ.get("DUCKDB_PATH", "weather_data.duckdb"))
    except ImportError:
        logging.warning("duckdb not available. Install with: pip install duckdb")
        return None


class WeatherFetcher:
    """Fetch weather data from public APIs"""
    
    # API endpoints
    OPEN_METEO_API = "https://api.open-meteo.com/v1"
    OPENWEATHERMAP_API = "https://api.openweathermap.org/data/2.5"
    
    def __init__(self, api_key: Optional[str] = None, api_type: str = "open-meteo"):
        """Initialize the weather fetcher
        
        Args:
            api_key: API key for services that require it (OpenWeatherMap)
            api_type: 'open-meteo' or 'openweathermap'
        
        Note: 
            Will fall back to environment variable OPENWEATHERMAP_API_KEY if not provided
            and api_type is 'openweathermap'
        """
        self.api_type = api_type.lower()
        
        # Only OpenWeatherMap requires API key
        if self.api_type == "openweathermap":
            self.api_key = api_key or os.environ.get("OPENWEATHERMAP_API_KEY")
            if not self.api_key:
                logging.warning("OpenWeatherMap API key not provided. Set OPENWEATHERMAP_API_KEY environment variable.")
    
    def fetch_forecast(self, 
                      latitude: float, 
                      longitude: float, 
                      hourly: Optional[List[str]] = None,
                      daily: Optional[List[str]] = None,
                      forecast_days: int = 7) -> Dict:
        """Fetch weather forecast from Open-Meteo API
        
        Args:
            latitude: Location latitude
            longitude: Location longitude
            hourly: List of hourly variables to include (e.g., ['temperature_2m', 'precipitation'])
            daily: List of daily variables to include (e.g., ['temperature_2m_max', 'sunrise'])
            forecast_days: Number of days to forecast (max 16)
            
        Returns:
            Dict with weather forecast data
        """
        if self.api_type != "open-meteo":
            logging.warning("Switching to Open-Meteo for forecast endpoint")
        
        # Default hourly and daily variables if not specified
        if hourly is None:
            hourly = ["temperature_2m", "relative_humidity_2m", "precipitation", "weather_code"]
            
        if daily is None:
            daily = ["temperature_2m_max", "temperature_2m_min", "sunrise", "sunset", "precipitation_sum"]
        
        params = {
            'latitude': latitude,
            'longitude': longitude,
            'hourly': ','.join(hourly),
            'daily': ','.join(daily),
            'forecast_days': min(forecast_days, 16),  # Max 16 days
            'timezone': 'auto'
        }
        
        url = f"{self.OPEN_METEO_API}/forecast"
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        # Add metadata
        result = response.json()
        result['_fetched_at'] = int(time.time())
        result['_source'] = 'open-meteo'
        
        return result
    
    def fetch_historical(self,
                        latitude: float,
                        longitude: float,
                        start_date: str,
                        end_date: str,
                        hourly: Optional[List[str]] = None) -> Dict:
        """Fetch historical weather data from Open-Meteo API
        
        Args:
            latitude: Location latitude
            longitude: Location longitude
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            hourly: List of hourly variables to include
            
        Returns:
            Dict with historical weather data
        """
        if self.api_type != "open-meteo":
            logging.warning("Switching to Open-Meteo for historical endpoint")
            
        # Default hourly variables if not specified
        if hourly is None:
            hourly = ["temperature_2m", "relative_humidity_2m", "precipitation"]
        
        params = {
            'latitude': latitude,
            'longitude': longitude,
            'start_date': start_date,
            'end_date': end_date,
            'hourly': ','.join(hourly),
            'timezone': 'auto'
        }
        
        url = f"{self.OPEN_METEO_API}/archive"
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        # Add metadata
        result = response.json()
        result['_fetched_at'] = int(time.time())
        result['_source'] = 'open-meteo'
        
        return result
    
    def fetch_current(self, latitude: float, longitude: float, units: str = "metric") -> Dict:
        """Fetch current weather from OpenWeatherMap API
        
        Args:
            latitude: Location latitude
            longitude: Location longitude
            units: Units format ('metric', 'imperial', or 'standard')
            
        Returns:
            Dict with current weather data
            
        Raises:
            ValueError: If OpenWeatherMap API key is not provided
        """
        if self.api_type == "openweathermap":
            if not hasattr(self, 'api_key') or not self.api_key:
                raise ValueError("OpenWeatherMap API key is required. Use api_key parameter or set OPENWEATHERMAP_API_KEY.")
                
            params = {
                'lat': latitude,
                'lon': longitude,
                'appid': self.api_key,
                'units': units
            }
            
            url = f"{self.OPENWEATHERMAP_API}/weather"
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            # Add metadata
            result = response.json()
            result['_fetched_at'] = int(time.time())
            result['_source'] = 'openweathermap'
            
            return result
        else:
            # Fallback to Open-Meteo for current weather
            params = {
                'latitude': latitude,
                'longitude': longitude,
                'current': 'temperature_2m,relative_humidity_2m,wind_speed_10m',
                'timezone': 'auto'
            }
            
            url = f"{self.OPEN_METEO_API}/forecast"
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            # Add metadata
            result = response.json()
            result['_fetched_at'] = int(time.time())
            result['_source'] = 'open-meteo'
            
            return result
    
    def get_locations(self, city_name: str) -> List[Dict]:
        """Search for locations by name using Open-Meteo Geocoding API
        
        Args:
            city_name: City name to search for
            
        Returns:
            List of location dictionaries with coordinates
        """
        params = {
            'name': city_name,
            'count': 10,
            'language': 'en',
            'format': 'json'
        }
        
        url = "https://geocoding-api.open-meteo.com/v1/search"
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json().get('results', [])
    
    # Storage methods similar to GTFS and NBA fetchers
    def save_to_s3(self, data: Dict, bucket: str, prefix: str = "", 
                 dataset_name: str = "weather", fmt: str = "json") -> str:
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
                
                # Weather data often has nested structure with arrays
                # Flatten the hourly forecast for easier analysis
                flattened_data = self._flatten_weather_data(data)
                
                df = pd.DataFrame(flattened_data)
                
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
                  dataset_name: str = "weather", fmt: str = "json") -> str:
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
                
                # Flatten the weather data for easier analysis
                flattened_data = self._flatten_weather_data(data)
                df = pd.DataFrame(flattened_data)
                
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
    
    def save_to_bigquery(self, data: Dict, dataset: str, table: str) -> int:
        """Save fetched weather data directly to BigQuery
        
        Args:
            data: Weather data to save
            dataset: BigQuery dataset ID
            table: BigQuery table name
            
        Returns:
            Number of rows inserted
        """
        bq = get_bigquery()
        if not bq:
            raise RuntimeError("BigQuery client not available")
        
        # Weather data requires special handling due to nested structure
        flattened_data = self._flatten_weather_data(data)
        
        # Build rows to insert
        rows_to_insert = []
        for record in flattened_data:
            # Process any nested fields
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
    
    def save_to_duckdb(self, data: Dict, table: str, db_path: Optional[str] = None) -> int:
        """Save fetched weather data to DuckDB (local or MotherDuck)
        
        Args:
            data: Weather data to save
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
        
        # Flatten weather data for easier querying
        flattened_data = self._flatten_weather_data(data)
        
        # Create DataFrame
        df = pd.DataFrame(flattened_data)
        
        # Connect to DuckDB
        conn = duckdb.connect(db_path or os.environ.get("DUCKDB_PATH", "weather_data.duckdb"))
        
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
        
        row_count = len(flattened_data)
        conn.close()
        
        return row_count

    def _flatten_weather_data(self, data: Dict) -> List[Dict]:
        """Helper to convert nested weather data to flattened records
        
        This converts Open-Meteo's nested array structure into rows for databases
        
        Args:
            data: Weather data from API
            
        Returns:
            List of flattened records
        """
        flattened = []
        
        # Extract location information
        location = {
            'latitude': data.get('latitude'),
            'longitude': data.get('longitude'),
            'elevation': data.get('elevation'),
            'timezone': data.get('timezone'),
            'fetched_at': data.get('_fetched_at', int(time.time())),
            'source': data.get('_source', 'unknown')
        }
        
        # Handle Open-Meteo forecast/historical
        if 'hourly' in data and 'hourly_units' in data:
            hourly_data = data['hourly']
            hourly_units = data['hourly_units']
            
            timestamps = hourly_data.get('time', [])
            for i, ts in enumerate(timestamps):
                record = dict(location)
                record['time'] = ts
                
                # Add all hourly variables
                for key in hourly_data:
                    if key != 'time' and i < len(hourly_data[key]):
                        record[key] = hourly_data[key][i]
                        if key in hourly_units:
                            record[f"{key}_unit"] = hourly_units[key]
                
                flattened.append(record)
        
        # Handle daily data if present
        elif 'daily' in data and 'daily_units' in data:
            daily_data = data['daily']
            daily_units = data['daily_units']
            
            timestamps = daily_data.get('time', [])
            for i, ts in enumerate(timestamps):
                record = dict(location)
                record['date'] = ts
                
                # Add all daily variables
                for key in daily_data:
                    if key != 'time' and i < len(daily_data[key]):
                        record[key] = daily_data[key][i]
                        if key in daily_units:
                            record[f"{key}_unit"] = daily_units[key]
                
                flattened.append(record)
                
        # Handle current weather (OpenWeatherMap or Open-Meteo)
        elif 'current' in data or 'main' in data:
            record = dict(location)
            
            # Handle Open-Meteo current
            if 'current' in data:
                current = data['current']
                units = data.get('current_units', {})
                
                for key, value in current.items():
                    record[key] = value
                    if key in units:
                        record[f"{key}_unit"] = units[key]
                        
            # Handle OpenWeatherMap 
            else:
                record['time'] = datetime.fromtimestamp(
                    data.get('dt', int(time.time()))).strftime('%Y-%m-%dT%H:%M')
                    
                # Main weather data
                if 'main' in data:
                    for key, value in data['main'].items():
                        record[f"main_{key}"] = value
                
                # Wind data
                if 'wind' in data:
                    for key, value in data['wind'].items():
                        record[f"wind_{key}"] = value
                
                # Weather description
                if 'weather' in data and len(data['weather']) > 0:
                    weather = data['weather'][0]
                    record['weather_id'] = weather.get('id')
                    record['weather_main'] = weather.get('main')
                    record['weather_description'] = weather.get('description')
                    record['weather_icon'] = weather.get('icon')
            
            flattened.append(record)
                
        # Fallback: just return the original data as a single record
        if not flattened:
            record = dict(location)
            for key, value in data.items():
                # Skip metadata fields already in location
                if key not in ['latitude', 'longitude', 'elevation', 'timezone', '_fetched_at', '_source']:
                    # Avoid nested structures
                    if not isinstance(value, (dict, list)):
                        record[key] = value
            
            flattened.append(record)
        
        return flattened


# AWS Lambda handler
def lambda_handler(event: Dict, context: Any) -> Dict:
    """AWS Lambda handler for Weather fetcher
    
    Environment variables:
        OPENWEATHERMAP_API_KEY: API key if using OpenWeatherMap
        S3_BUCKET: Bucket to store results
        S3_PREFIX: Optional prefix in bucket
        API_TYPE: Weather API to use ('open-meteo' or 'openweathermap')
        
    Event params (examples):
        {'endpoint': 'forecast', 'latitude': 40.7128, 'longitude': -74.0060}
        {'endpoint': 'historical', 'latitude': 40.7128, 'longitude': -74.0060, 
         'start_date': '2023-01-01', 'end_date': '2023-01-07'}
        {'endpoint': 'current', 'latitude': 40.7128, 'longitude': -74.0060}
        
    Returns:
        Dict with execution info
    """
    # Configure from environment and event
    api_key = os.environ.get("OPENWEATHERMAP_API_KEY")
    api_type = os.environ.get("API_TYPE", "open-meteo")
    
    bucket = os.environ.get("S3_BUCKET")
    prefix = os.environ.get("S3_PREFIX", "weather")
    fmt = os.environ.get("OUTPUT_FORMAT", "json")
    
    # Parameters from event
    endpoint = event.get('endpoint', 'forecast')
    latitude = event.get('latitude')
    longitude = event.get('longitude')
    
    if not latitude or not longitude:
        raise ValueError("Latitude and longitude are required")
    
    if not bucket:
        raise ValueError("S3_BUCKET environment variable must be set")
    
    # Initialize fetcher
    start_time = time.time()
    fetcher = WeatherFetcher(api_key, api_type)
    
    try:
        # Fetch data based on endpoint
        data = None
        dataset_name = f"weather_{endpoint}"
        
        if endpoint == "forecast":
            forecast_days = event.get('forecast_days', 7)
            hourly = event.get('hourly')
            daily = event.get('daily')
            
            data = fetcher.fetch_forecast(
                latitude=latitude,
                longitude=longitude,
                hourly=hourly,
                daily=daily,
                forecast_days=forecast_days
            )
        
        elif endpoint == "historical":
            start_date = event.get('start_date')
            end_date = event.get('end_date')
            hourly = event.get('hourly')
            
            if not start_date or not end_date:
                raise ValueError("start_date and end_date are required for historical data")
                
            data = fetcher.fetch_historical(
                latitude=latitude,
                longitude=longitude,
                start_date=start_date,
                end_date=end_date,
                hourly=hourly
            )
        
        elif endpoint == "current":
            units = event.get('units', 'metric')
            data = fetcher.fetch_current(
                latitude=latitude,
                longitude=longitude,
                units=units
            )
        
        else:
            raise ValueError(f"Unsupported endpoint: {endpoint}")
        
        # Save to S3
        location = fetcher.save_to_s3(data, bucket, prefix, dataset_name, fmt)
        
        # Return execution summary
        return {
            "statusCode": 200,
            "executionTime": time.time() - start_time,
            "endpoint": endpoint,
            "location": location,
            "message": "Weather data saved successfully"
        }
    except Exception as e:
        logging.exception("Error in Lambda execution")
        return {
            "statusCode": 500,
            "executionTime": time.time() - start_time,
            "error": str(e),
            "message": "Error fetching or saving weather data"
        }

# GCP Cloud Function handler
def gcp_function(request):
    """GCP Cloud Function handler for Weather fetcher
    
    Environment variables:
        OPENWEATHERMAP_API_KEY: API key if using OpenWeatherMap
        GCS_BUCKET: GCS bucket name (optional)
        GCS_PREFIX: Optional prefix in bucket
        BQ_DATASET: BigQuery dataset ID (optional)
        BQ_TABLE: BigQuery table name (optional)
        API_TYPE: Weather API to use ('open-meteo' or 'openweathermap')
        
    Request JSON params (examples):
        {'endpoint': 'forecast', 'latitude': 40.7128, 'longitude': -74.0060}
        {'endpoint': 'historical', 'latitude': 40.7128, 'longitude': -74.0060, 
         'start_date': '2023-01-01', 'end_date': '2023-01-07'}
        
    Either GCS_BUCKET or both BQ_DATASET and BQ_TABLE must be set
        
    Returns:
        JSON response with execution info
    """
    # Configure from environment
    api_key = os.environ.get("OPENWEATHERMAP_API_KEY")
    api_type = os.environ.get("API_TYPE", "open-meteo")
    
    # Storage options
    bucket = os.environ.get("GCS_BUCKET")
    prefix = os.environ.get("GCS_PREFIX", "weather")
    fmt = os.environ.get("OUTPUT_FORMAT", "json")
    
    dataset = os.environ.get("BQ_DATASET")
    table = os.environ.get("BQ_TABLE")
    
    if not bucket and not (dataset and table):
        return {"error": "Either GCS_BUCKET or BQ_DATASET and BQ_TABLE must be set"}, 400
    
    # Parse request
    try:
        request_json = request.get_json(silent=True)
        if not request_json:
            return {"error": "Request body must contain valid JSON"}, 400
            
        endpoint = request_json.get('endpoint', 'forecast')
        latitude = request_json.get('latitude')
        longitude = request_json.get('longitude')
        
        if not latitude or not longitude:
            return {"error": "Latitude and longitude are required"}, 400
    except Exception:
        return {"error": "Invalid JSON in request body"}, 400
    
    # Initialize fetcher
    start_time = time.time()
    fetcher = WeatherFetcher(api_key, api_type)
    
    try:
        # Fetch data based on endpoint
        data = None
        dataset_name = f"weather_{endpoint}"
        
        if endpoint == "forecast":
            forecast_days = request_json.get('forecast_days', 7)
            hourly = request_json.get('hourly')
            daily = request_json.get('daily')
            
            data = fetcher.fetch_forecast(
                latitude=latitude,
                longitude=longitude,
                hourly=hourly,
                daily=daily,
                forecast_days=forecast_days
            )
        
        elif endpoint == "historical":
            start_date = request_json.get('start_date')
            end_date = request_json.get('end_date')
            hourly = request_json.get('hourly')
            
            if not start_date or not end_date:
                return {"error": "start_date and end_date are required for historical data"}, 400
                
            data = fetcher.fetch_historical(
                latitude=latitude,
                longitude=longitude,
                start_date=start_date,
                end_date=end_date,
                hourly=hourly
            )
        
        elif endpoint == "current":
            units = request_json.get('units', 'metric')
            data = fetcher.fetch_current(
                latitude=latitude,
                longitude=longitude,
                units=units
            )
        
        else:
            return {"error": f"Unsupported endpoint: {endpoint}"}, 400
        
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
            "endpoint": endpoint,
            "location": location,
            "rowsInserted": rows_inserted,
            "message": "Weather data saved successfully"
        }
    except Exception as e:
        logging.exception("Error in Cloud Function execution")
        return {
            "status": "error",
            "executionTime": time.time() - start_time,
            "error": str(e),
            "message": "Error fetching or saving weather data"
        }, 500

# Main entrypoint for local execution
if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    parser = argparse.ArgumentParser(description="Weather Data Fetcher")
    parser.add_argument("--endpoint", choices=["forecast", "historical", "current"], 
                      default="forecast", help="API endpoint to use")
    parser.add_argument("--latitude", type=float, required=True, help="Location latitude")
    parser.add_argument("--longitude", type=float, required=True, help="Location longitude")
    parser.add_argument("--api-key", help="API key (required for OpenWeatherMap)")
    parser.add_argument("--api-type", choices=["open-meteo", "openweathermap"],
                     default="open-meteo", help="Weather API to use")
    
    # Forecast params
    parser.add_argument("--forecast-days", type=int, default=7, help="Number of days to forecast (max 16)")
    parser.add_argument("--hourly", nargs="+", help="Hourly variables to include")
    parser.add_argument("--daily", nargs="+", help="Daily variables to include")
    
    # Historical params
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD) for historical data")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD) for historical data")
    
    # Current weather params
    parser.add_argument("--units", choices=["metric", "imperial"], default="metric",
                     help="Units for OpenWeatherMap API")
    
    # Output options
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--format", choices=["json", "parquet"], default="json", help="Output format")
    parser.add_argument("--cloud", choices=["aws", "gcp", "azure", "duckdb"], help="Cloud provider")
    parser.add_argument("--bucket", help="S3 or GCS bucket name")
    parser.add_argument("--prefix", default="weather", help="Prefix in bucket")
    parser.add_argument("--dataset", help="BigQuery dataset (GCP only)")
    parser.add_argument("--table", help="Table name (BigQuery or DuckDB)")
    parser.add_argument("--db-path", help="DuckDB path or MotherDuck URI")
    
    args = parser.parse_args()
    
    # Initialize fetcher
    fetcher = WeatherFetcher(args.api_key, args.api_type)
    
    try:
        # Fetch data based on endpoint
        data = None
        dataset_name = f"weather_{args.endpoint}"
        
        if args.endpoint == "forecast":
            data = fetcher.fetch_forecast(
                latitude=args.latitude,
                longitude=args.longitude,
                hourly=args.hourly,
                daily=args.daily,
                forecast_days=args.forecast_days
            )
            logging.info(f"Fetched forecast data for lat={args.latitude}, lon={args.longitude}")
        
        elif args.endpoint == "historical":
            if not args.start_date or not args.end_date:
                parser.error("--start-date and --end-date are required for historical data")
                
            data = fetcher.fetch_historical(
                latitude=args.latitude,
                longitude=args.longitude,
                start_date=args.start_date,
                end_date=args.end_date,
                hourly=args.hourly
            )
            logging.info(f"Fetched historical data for lat={args.latitude}, lon={args.longitude} "
                       f"from {args.start_date} to {args.end_date}")
        
        elif args.endpoint == "current":
            data = fetcher.fetch_current(
                latitude=args.latitude,
                longitude=args.longitude,
                units=args.units
            )
            logging.info(f"Fetched current weather for lat={args.latitude}, lon={args.longitude}")
        
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
            db_path = args.db_path or os.environ.get("DUCKDB_PATH", "weather_data.duckdb")
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
                        # Flatten weather data for Parquet
                        flattened_data = fetcher._flatten_weather_data(data)
                        df = pd.DataFrame(flattened_data)
                        df.to_parquet(args.output)
                    except ImportError:
                        logging.error("pandas and pyarrow are required for parquet format")
                        raise
                
                logging.info(f"Data saved to {args.output}")
            else:
                print(json.dumps(data, indent=2))
    
    except Exception as e:
        logging.exception("Error fetching or saving weather data")
        exit(1) 