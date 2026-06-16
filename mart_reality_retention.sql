-- Когортная retention-витрина для раздела Недвижимость.

DROP TABLE IF EXISTS farpost.mart_realty_retention;

CREATE TABLE farpost.mart_realty_retention (
    cohort_date       Date    COMMENT 'Дата первого визита пользователя (когорта)',
    days_since_cohort UInt16  COMMENT 'Сколько дней прошло с первого визита когорты',
    n_active_users    UInt64  COMMENT 'Сколько пользователей из этой когорты были активны в этот день',
    cohort_size       UInt64  COMMENT 'Общий размер когорты (число пользователей в день первого визита)',
    retention_rate    Float64 COMMENT 'Возвращаемость'
) ENGINE = MergeTree()
ORDER BY (cohort_date, days_since_cohort)
COMMENT 'Когортная retention-витрина раздела Недвижимость';

INSERT INTO farpost.mart_realty_retention
WITH user_activity AS (
    -- Один пользователь -- один день -- одна строка (не важно сколько событий было)
    SELECT
        multiIf(user_id != '00000000-0000-0000-0000-000000000000', user_id, cookie_id) AS analysis_id,
        toDate(event_timestamp) AS activity_date
    FROM farpost.stg_realty_events
    WHERE user_type IN ('registered', 'cookie')
    GROUP BY analysis_id, activity_date
),

cohorts AS (
    -- Когорта пользователя -- дата его первого визита за весь период наблюдения
    SELECT
        analysis_id,
        MIN(activity_date) AS cohort_date
    FROM user_activity
    GROUP BY analysis_id
),

activity_with_offset AS (
    SELECT
        c.cohort_date,
        a.analysis_id,
        dateDiff('day', c.cohort_date, a.activity_date) AS days_since_cohort
    FROM user_activity a
    JOIN cohorts c ON a.analysis_id = c.analysis_id
),

cohort_sizes AS (
    SELECT cohort_date, count() AS cohort_size
    FROM cohorts
    GROUP BY cohort_date
)

SELECT
    awo.cohort_date,
    awo.days_since_cohort,
    uniqExact(awo.analysis_id) AS n_active_users,
    cs.cohort_size,
    uniqExact(awo.analysis_id) / cs.cohort_size AS retention_rate
FROM activity_with_offset awo
JOIN cohort_sizes cs ON awo.cohort_date = cs.cohort_date
GROUP BY awo.cohort_date, awo.days_since_cohort, cs.cohort_size
ORDER BY awo.cohort_date, awo.days_since_cohort;