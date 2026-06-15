{{ config(materialized='table') }}

SELECT
    event_id,
    event_timestamp,
    event_type,
    user_type,
    is_registered,
    user_id,
    cookie_id,
    fingerprint_id,
    session_id,
    category,
    listing_id,
    device_type,
    os,
    region
FROM {{ source('farpost', 'raw_events') }}
WHERE section = 'realty'