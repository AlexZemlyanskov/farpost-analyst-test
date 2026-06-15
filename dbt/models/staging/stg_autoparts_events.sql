{{ config(materialized='table') }}

WITH events AS (
    SELECT *
    FROM {{ source('farpost', 'raw_events') }}
    WHERE section = 'autoparts'
),

assignments AS (
    SELECT *
    FROM {{ source('farpost', 'experiment_assignments') }}
)

SELECT
    e.event_id,
    e.event_timestamp,
    e.event_type,
    e.user_type,
    e.is_registered,
    e.user_id,
    e.cookie_id,
    e.fingerprint_id,
    e.session_id,
    e.category,
    e.listing_id,
    e.device_type,
    e.os,
    e.region,
    -- Джойним группу из assignments: сначала по user_id для зарегов,
    -- потом по cookie_id для незарегов
    COALESCE(
        a_reg.experiment_group,
        a_cookie.experiment_group,
        'none'
    ) AS experiment_group,
    COALESCE(
        a_reg.experiment_id,
        a_cookie.experiment_id,
        '00000000-0000-0000-0000-000000000000'
    ) AS experiment_id
FROM events e
LEFT JOIN assignments a_reg
    ON e.user_id = a_reg.user_id
    AND e.user_id != '00000000-0000-0000-0000-000000000000'
LEFT JOIN assignments a_cookie
    ON e.cookie_id = a_cookie.cookie_id
    AND e.cookie_id != '00000000-0000-0000-0000-000000000000'