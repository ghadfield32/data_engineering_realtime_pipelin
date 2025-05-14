-- Daily vehicle counts by route from GTFS vehicle position data
-- This model aggregates vehicle position data to get a count of unique vehicles per route per day

{{ config(
    materialized='table',
    schema='gtfs',
    tags=['gtfs', 'daily']
) }}

WITH raw_positions AS (
    SELECT 
        -- Extract fields from raw JSON
        id,
        vehicle->>'id' AS vehicle_id,
        vehicle->>'trip' AS trip,
        vehicle->>'vehicle' AS vehicle,
        vehicle->>'position' AS position,
        vehicle->>'current_status' AS current_status,
        vehicle->>'timestamp' AS timestamp,
        vehicle->>'congestion_level' AS congestion_level,
        vehicle->>'occupancy_status' AS occupancy_status,
        _fetched_at,
        _source,
        _processing_time
    FROM 
        {{ source('gtfs', 'raw_vehicle_positions') }}
),

parsed_positions AS (
    SELECT
        id,
        vehicle_id,
        -- Extract trip fields
        JSON_EXTRACT_PATH_TEXT(trip::JSON, 'trip_id') AS trip_id,
        JSON_EXTRACT_PATH_TEXT(trip::JSON, 'route_id') AS route_id,
        JSON_EXTRACT_PATH_TEXT(trip::JSON, 'start_time') AS start_time,
        JSON_EXTRACT_PATH_TEXT(trip::JSON, 'start_date') AS start_date,
        JSON_EXTRACT_PATH_TEXT(trip::JSON, 'schedule_relationship') AS schedule_relationship,
        -- Extract position fields
        CAST(JSON_EXTRACT_PATH_TEXT(position::JSON, 'latitude') AS FLOAT) AS latitude,
        CAST(JSON_EXTRACT_PATH_TEXT(position::JSON, 'longitude') AS FLOAT) AS longitude,
        CAST(JSON_EXTRACT_PATH_TEXT(position::JSON, 'bearing') AS FLOAT) AS bearing,
        CAST(JSON_EXTRACT_PATH_TEXT(position::JSON, 'speed') AS FLOAT) AS speed,
        -- Convert timestamp to datetime
        TO_TIMESTAMP(CAST(timestamp AS INTEGER)) AS timestamp_utc,
        -- Extract date from processing time
        DATE(CAST(_processing_time AS TIMESTAMP)) AS processing_date,
        _fetched_at,
        _source
    FROM
        raw_positions
    WHERE
        vehicle_id IS NOT NULL
),

daily_counts AS (
    SELECT
        processing_date,
        route_id,
        COUNT(DISTINCT vehicle_id) AS unique_vehicle_count,
        COUNT(*) AS position_count,
        MIN(timestamp_utc) AS first_position_time,
        MAX(timestamp_utc) AS last_position_time,
        -- Calculate average metrics
        AVG(speed) AS avg_speed,
        -- Count by status
        SUM(CASE WHEN current_status = '0' THEN 1 ELSE 0 END) AS status_incoming_at,
        SUM(CASE WHEN current_status = '1' THEN 1 ELSE 0 END) AS status_stopped_at,
        SUM(CASE WHEN current_status = '2' THEN 1 ELSE 0 END) AS status_in_transit_to
    FROM
        parsed_positions
    WHERE
        route_id IS NOT NULL
    GROUP BY
        processing_date,
        route_id
)

SELECT
    processing_date,
    route_id,
    unique_vehicle_count,
    position_count,
    first_position_time,
    last_position_time,
    avg_speed,
    status_incoming_at,
    status_stopped_at,
    status_in_transit_to,
    -- Calculate percentage of each status
    status_incoming_at / NULLIF(position_count, 0) * 100 AS pct_incoming_at,
    status_stopped_at / NULLIF(position_count, 0) * 100 AS pct_stopped_at,
    status_in_transit_to / NULLIF(position_count, 0) * 100 AS pct_in_transit_to
FROM
    daily_counts
ORDER BY
    processing_date DESC,
    unique_vehicle_count DESC 