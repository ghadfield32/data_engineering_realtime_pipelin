-- Weather Daily Summary Model
-- This model aggregates weather observations by day and location 
-- to provide daily weather statistics

{{
  config(
    materialized='table',
    sort='date',
    dist='location'
  )
}}

WITH weather_observations AS (
    SELECT
        location,
        latitude,
        longitude,
        obs_time,
        DATE(obs_time) AS date,
        temperature,
        humidity,
        pressure,
        wind_speed,
        wind_direction,
        conditions
    FROM {{ source('postgres', 'weather_observations') }}
    WHERE obs_time IS NOT NULL
),

daily_stats AS (
    SELECT
        date,
        location,
        ROUND(AVG(latitude), 6) AS latitude,
        ROUND(AVG(longitude), 6) AS longitude,
        COUNT(*) AS observation_count,
        ROUND(AVG(temperature), 2) AS avg_temp,
        ROUND(MIN(temperature), 2) AS min_temp,
        ROUND(MAX(temperature), 2) AS max_temp,
        ROUND(AVG(humidity), 2) AS avg_humidity,
        ROUND(AVG(pressure), 2) AS avg_pressure,
        ROUND(AVG(wind_speed), 2) AS avg_wind_speed,
        -- Most common conditions by count
        MODE() WITHIN GROUP (ORDER BY conditions) AS most_common_conditions
    FROM weather_observations
    GROUP BY date, location
),

-- Join with NBA data if available
nba_games AS (
    SELECT 
        date,
        COUNT(*) AS num_games_played
    FROM {{ ref('nba_games_summary') }}
    GROUP BY date
)

SELECT
    ds.date,
    ds.location,
    ds.latitude,
    ds.longitude,
    ds.observation_count,
    ds.avg_temp,
    ds.min_temp,
    ds.max_temp,
    ds.avg_humidity,
    ds.avg_pressure,
    ds.avg_wind_speed,
    ds.most_common_conditions,
    -- Join with NBA games if available, else NULL
    CASE 
        WHEN ng.num_games_played IS NOT NULL THEN ng.num_games_played
        ELSE 0
    END AS nba_games_played,
    -- Calculate a "weather score" (example metric)
    CASE
        WHEN ds.avg_temp BETWEEN 15 AND 25 AND ds.avg_humidity BETWEEN 40 AND 60
            THEN 'Optimal'
        WHEN ds.avg_temp > 30 OR ds.avg_humidity > 80
            THEN 'Uncomfortable'
        WHEN ds.avg_temp < 5
            THEN 'Cold'
        ELSE 'Normal'
    END AS weather_comfort_level
FROM daily_stats ds
LEFT JOIN nba_games ng ON ds.date = ng.date
ORDER BY ds.date DESC, ds.location 