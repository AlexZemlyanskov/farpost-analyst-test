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
    e.event_id        AS event_id,
    e.event_timestamp AS event_timestamp,
    e.event_type       AS event_type,
    e.user_type        AS user_type,
    e.is_registered    AS is_registered,
    e.user_id          AS user_id,
    e.cookie_id        AS cookie_id,
    e.fingerprint_id   AS fingerprint_id,
    e.session_id       AS session_id,
    e.category         AS category,
    e.listing_id       AS listing_id,
    e.device_type      AS device_type,
    e.os               AS os,
    e.region           AS region,
    multiIf(
        a_reg.experiment_group != '', a_reg.experiment_group,
        a_cookie.experiment_group != '', a_cookie.experiment_group,
        'none'
    ) AS experiment_group,
    multiIf(
        a_reg.experiment_group != '', a_reg.experiment_id,
        a_cookie.experiment_group != '', a_cookie.experiment_id,
        '00000000-0000-0000-0000-000000000000'
    ) AS experiment_id
FROM events e
LEFT JOIN assignments a_reg
    ON e.user_id = a_reg.user_id
    AND e.user_id != '00000000-0000-0000-0000-000000000000'
LEFT JOIN assignments a_cookie
    ON e.cookie_id = a_cookie.cookie_id
    AND e.cookie_id != '00000000-0000-0000-0000-000000000000'