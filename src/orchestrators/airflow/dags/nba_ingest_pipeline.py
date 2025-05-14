#!/usr/bin/env python3
"""
NBA Data Ingestion Pipeline DAG with AssetWatcher

This DAG fetches NBA game data from an API, processes it, and loads it into PostgreSQL.
It utilizes Airflow 3.0's AssetWatcher for event-driven runs and explicit SQL operations.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import requests

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.models.connection import Connection
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.sdk import Asset, AssetWatcher
from airflow.providers.standard.triggers.file import FileSensorTrigger
from ingestion.fetch_gtfs import GTFSFetcher

# Default settings applied to all tasks
default_args = {
    'owner': 'data-engineering',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(minutes=10),
}

# Define an asset that watches for new NBA data files in MinIO
nba_file_sensor_trigger = FileSensorTrigger(filepath="/data/nba/new_data.flag")
nba_data_asset = Asset(
    "nba_data_asset", 
    watchers=[AssetWatcher(name="nba_data_watcher", trigger=nba_file_sensor_trigger)]
)

# Define the DAG using Airflow 3.0's @dag decorator and AssetWatcher
@dag(
    default_args=default_args,
    schedule=[nba_data_asset],  # Schedule based on asset availability
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['nba', 'event-driven', 'assetwatcher', 'sql'],
)
def nba_ingest_pipeline():
    """
    ### NBA Data Ingestion Pipeline with AssetWatcher

    This DAG demonstrates how to use Airflow 3.0's AssetWatcher for event-driven processing.
    It watches for a flag file indicating new NBA data is available, then processes
    and loads the data into PostgreSQL using explicit SQL operations.

    #### Triggers:
    - File sensor watching for "/data/nba/new_data.flag"
    """

    @task()
    def fetch_nba_games():
        """Fetch NBA game data from the API"""
        # Get API key from Airflow connection or environment variable
        try:
            conn = Connection.get_connection_from_secrets("nba_api")
            api_key = conn.password
            api_url = conn.host
        except:
            api_key = os.getenv("NBA_API_KEY")
            api_url = "https://api.example.com/nba/games"

        # Get current date in format YYYY-MM-DD
        today = datetime.now().strftime("%Y-%m-%d")

        # Make API request
        headers = {"API-Key": api_key} if api_key else {}
        params = {"date": today}

        logging.info(f"Fetching NBA games data from {api_url} for date {today}")

        # For demo purposes, using sample data if API call fails
        try:
            response = requests.get(api_url, headers=headers, params=params, timeout=10)
            data = response.json().get("games", [])
        except Exception as e:
            logging.warning(f"Failed to fetch real NBA data: {e}. Using sample data instead.")
            # Sample data for demonstration
            data = [
                {
                    "id": "20240101-LAL-GSW",
                    "date": today,
                    "home_team": "LAL",
                    "away_team": "GSW",
                    "score_home": 120,
                    "score_away": 115,
                },
                {
                    "id": "20240101-BOS-MIA",
                    "date": today,
                    "home_team": "BOS",
                    "away_team": "MIA",
                    "score_home": 105,
                    "score_away": 98,
                }
            ]

        logging.info(f"Retrieved {len(data)} NBA games")
        return data

    @task()
    def process_games(games_data):
        """Process the NBA games data"""
        # Add processing metadata
        processed_data = []
        processing_time = datetime.now().isoformat()

        for game in games_data:
            # Add processing timestamp
            game['processing_time'] = processing_time
            processed_data.append(game)

        logging.info(f"Processed {len(processed_data)} NBA games")
        return processed_data

    @task()
    def prepare_sql_values(games):
        """Prepare SQL VALUES for insertion"""
        if not games:
            return "''"

        values_strings = []
        for game in games:
            # Format values for SQL INSERT
            values_str = f"('{game['id']}', '{game['date']}', '{game['home_team']}', '{game['away_team']}', {game['score_home']}, {game['score_away']}, CURRENT_TIMESTAMP)"
            values_strings.append(values_str)

        return ", ".join(values_strings)

    # Create NBA schema and tables if they don't exist
    create_schema = PostgresOperator(
        task_id="create_nba_schema",
        postgres_conn_id="postgres_default",
        sql="""
        CREATE SCHEMA IF NOT EXISTS nba;
        """
    )

    create_table = PostgresOperator(
        task_id="create_nba_games_table",
        postgres_conn_id="postgres_default",
        sql="""
        CREATE TABLE IF NOT EXISTS nba.games (
            game_id TEXT PRIMARY KEY,
            date DATE,
            home_team TEXT,
            away_team TEXT,
            score_home INTEGER,
            score_away INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # PostgresOperator task that takes values from previous task
    @task()
    def insert_games_to_db(values):
        """Insert games data into database using PostgresOperator"""
        if not values or values == "''":
            logging.warning("No NBA games data to save")
            return {"status": "warning", "message": "No data to save"}

        insert_games = PostgresOperator(
            task_id="insert_nba_games",
            postgres_conn_id="postgres_default",
            sql=f"""
            INSERT INTO nba.games 
            (game_id, date, home_team, away_team, score_home, score_away, updated_at)
            VALUES {values}
            ON CONFLICT (game_id) 
            DO UPDATE SET 
                score_home = EXCLUDED.score_home,
                score_away = EXCLUDED.score_away,
                updated_at = CURRENT_TIMESTAMP;
            """
        )

        insert_games.execute(context={})
        return {"status": "success", "count": values.count('),') + 1 if values else 0}

    # Create summary view for analytics
    create_summary_view = PostgresOperator(
        task_id="create_nba_summary_view",
        postgres_conn_id="postgres_default",
        sql="""
        CREATE OR REPLACE VIEW nba.games_summary AS
        SELECT
            date,
            COUNT(*) AS game_count,
            AVG(score_home + score_away) AS avg_total_score,
            MAX(score_home) AS max_home_score,
            MAX(score_away) AS max_away_score,
            SUM(CASE WHEN score_home > score_away THEN 1 ELSE 0 END) AS home_wins,
            SUM(CASE WHEN score_home < score_away THEN 1 ELSE 0 END) AS away_wins
        FROM nba.games
        GROUP BY date
        ORDER BY date DESC;
        """
    )

    # Run analytics query - this will show up in UI
    run_analytics = PostgresOperator(
        task_id="run_nba_analytics",
        postgres_conn_id="postgres_default",
        sql="""
        -- Calculate team performance metrics
        SELECT 
            home_team AS team,
            COUNT(*) AS games_played,
            SUM(CASE WHEN score_home > score_away THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN score_home < score_away THEN 1 ELSE 0 END) AS losses,
            AVG(score_home) AS avg_points_scored
        FROM nba.games
        GROUP BY home_team

        UNION ALL

        SELECT 
            away_team AS team,
            COUNT(*) AS games_played,
            SUM(CASE WHEN score_away > score_home THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN score_away < score_home THEN 1 ELSE 0 END) AS losses,
            AVG(score_away) AS avg_points_scored
        FROM nba.games
        GROUP BY away_team
        ORDER BY wins DESC, team;
        """
    )

    @task()
    def cleanup():
        """Clean up temporary files after processing"""
        # Remove the flag file that triggered this DAG
        try:
            flag_file = "/data/nba/new_data.flag"
            if os.path.exists(flag_file):
                os.remove(flag_file)
                logging.info(f"Removed flag file: {flag_file}")
            else:
                logging.warning(f"Flag file not found: {flag_file}")
        except Exception as e:
            logging.error(f"Error removing flag file: {e}")

        return {"status": "success"}

    # Define task dependencies
    nba_games = fetch_nba_games()
    processed_games = process_games(nba_games)
    sql_values = prepare_sql_values(processed_games)

    # Database operations
    create_schema >> create_table

    # Execute insert and analytics
    insert_result = insert_games_to_db(sql_values)
    create_table >> insert_result >> create_summary_view >> run_analytics

    # Cleanup at the end
    cleanup_result = cleanup()
    run_analytics >> cleanup_result

    # Set up main flow
    nba_games >> processed_games >> sql_values >> insert_result

# Instantiate the DAG
nba_pipeline = nba_ingest_pipeline() 






