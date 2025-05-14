-- NBA Games Summary Model
-- This model summarizes NBA games by aggregating scores and counting games played
-- It serves as a daily dashboard of NBA activity

{{
  config(
    materialized='table',
    sort='date',
    dist='date'
  )
}}

WITH games AS (
    SELECT
        date,
        home_team,
        away_team,
        score_home,
        score_away,
        CASE
            WHEN score_home > score_away THEN home_team
            WHEN score_away > score_home THEN away_team
            ELSE 'Tie'
        END AS winner,
        ABS(score_home - score_away) AS point_difference
    FROM {{ source('postgres', 'nba_games') }}
    WHERE score_home IS NOT NULL AND score_away IS NOT NULL
),

daily_summary AS (
    SELECT
        date,
        COUNT(*) AS games_played,
        AVG(score_home + score_away) AS avg_total_score,
        MAX(score_home + score_away) AS max_total_score,
        MIN(score_home + score_away) AS min_total_score,
        AVG(point_difference) AS avg_point_difference
    FROM games
    GROUP BY date
),

team_summary AS (
    SELECT
        date,
        home_team AS team,
        CASE WHEN score_home > score_away THEN 1 ELSE 0 END AS wins,
        CASE WHEN score_home < score_away THEN 1 ELSE 0 END AS losses,
        CASE WHEN score_home = score_away THEN 1 ELSE 0 END AS draws,
        score_home AS points_scored
    FROM games
    
    UNION ALL
    
    SELECT
        date,
        away_team AS team,
        CASE WHEN score_away > score_home THEN 1 ELSE 0 END AS wins,
        CASE WHEN score_away < score_home THEN 1 ELSE 0 END AS losses,
        CASE WHEN score_home = score_away THEN 1 ELSE 0 END AS draws,
        score_away AS points_scored
    FROM games
),

team_daily_stats AS (
    SELECT
        date,
        team,
        SUM(wins) AS wins,
        SUM(losses) AS losses,
        SUM(draws) AS draws,
        SUM(points_scored) AS total_points,
        COUNT(*) AS games_played,
        SUM(points_scored) / COUNT(*) AS avg_points_per_game
    FROM team_summary
    GROUP BY date, team
)

-- Final combined summary
SELECT
    d.date,
    d.games_played,
    d.avg_total_score,
    d.max_total_score,
    d.min_total_score,
    d.avg_point_difference,
    t.team,
    t.wins,
    t.losses,
    t.total_points,
    t.avg_points_per_game
FROM daily_summary d
JOIN team_daily_stats t ON d.date = t.date
ORDER BY d.date DESC, t.wins DESC, t.avg_points_per_game DESC 