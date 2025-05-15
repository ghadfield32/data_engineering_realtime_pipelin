
#!/usr/bin/env python3
"""NBA data processing helper functions for Airflow DAGs"""

import logging
import os
from datetime import datetime
import requests
from typing import Dict, List, Any, Optional, Union


class NBAProcessor:
    """Class to process NBA game data"""

    @staticmethod
    def fetch_nba_games() -> list[dict]:
        """
        Fetch today's NBA games live from stats.nba.com via nba_api.
        No API key required.
        """
        from datetime import datetime
        from nba_api.stats.endpoints import ScoreboardV2

        # NBA expects dates as MM/DD/YYYY
        game_date = datetime.utcnow().strftime("%m/%d/%Y")
        sb = ScoreboardV2(game_date=game_date)
        payload = sb.get_dict()
        rows = payload["resultSets"][0]["rowSet"]

        games = []
        for row in rows:
            games.append({
                "game_id":       row[2],            # GAME_ID
                "date":          row[0],            # GAME_DATE
                "home_team":     row[6],            # HOME_TEAM_ABBREVIATION
                "away_team":     row[7],            # VISITOR_TEAM_ABBREVIATION
                "score_home":    row[21] or 0,      # PTS_HOME; if None, 0
                "score_away":    row[22] or 0,      # PTS_AWAY; if None, 0
            })
        return games

    @staticmethod
    def process_games(games_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process the NBA games data

        Args:
            games_data: Raw NBA game data

        Returns:
            Processed NBA game data with added timestamps
        """
        # Add processing metadata
        processed_data = []
        processing_time = datetime.now().isoformat()

        for game in games_data:
            # Add processing timestamp
            game['processing_time'] = processing_time
            processed_data.append(game)

        logging.info(f"Processed {len(processed_data)} NBA games")
        return processed_data

    @staticmethod
    def prepare_sql_values(games: List[Dict[str, Any]]) -> str:
        """
        Prepare SQL VALUES for insertion

        Args:
            games: List of processed game data

        Returns:
            SQL VALUES string for insertion
        """
        if not games:
            return "''"

        values_strings = []
        for game in games:
            # Format values for SQL INSERT
            values_str = f"('{game['id']}', '{game['date']}', '{game['home_team']}', '{game['away_team']}', {game['score_home']}, {game['score_away']}, CURRENT_TIMESTAMP)"
            values_strings.append(values_str)

        return ", ".join(values_strings)

    @staticmethod
    def cleanup_flag_file(flag_file_path: str) -> Dict[str, str]:
        """
        Clean up the flag file that triggered a DAG

        Args:
            flag_file_path: Path to the flag file

        Returns:
            Status dictionary
        """
        try:
            if os.path.exists(flag_file_path):
                os.remove(flag_file_path)
                logging.info(f"Removed flag file: {flag_file_path}")
            else:
                logging.warning(f"Flag file not found: {flag_file_path}")
        except Exception as e:
            logging.error(f"Error removing flag file: {e}")

        return {"status": "success"} 
