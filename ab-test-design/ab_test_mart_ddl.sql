-- Витрина для анализа A/B теста: одна строка на пользователя
-- Источник: stg_autoparts_events (уже содержит experiment_group из джойна с assignments)
--
-- Важно: фильтруем события только в пределах окна теста (event_timestamp).
-- experiment_group в stg_autoparts_events проставлен на ВСЕ события пользователя
-- (джойн идёт по user_id/cookie_id без учёта времени), но реальный эффект
-- лифта CTR заложен в данные только внутри тестового периода. Без этого фильтра
-- в выборку попадут события до/после теста, где различия между группами
-- не было - это размыло бы результат.
--
-- Даты совпадают с AB_TEST_START / AB_TEST_END в generate_data.py

DROP TABLE IF EXISTS farpost.mart_ab_test;

CREATE TABLE farpost.mart_ab_test (
    analysis_id      FixedString(36)         COMMENT 'Унифицированный ID: user_id для зарегов, cookie_id для остальных',
    experiment_group LowCardinality(String)  COMMENT 'Группа эксперимента: control, treatment',
    is_registered    UInt8                   COMMENT '1 если пользователь зарегистрирован',
    user_type        LowCardinality(String)  COMMENT 'Тип пользователя: registered, cookie',
    device_type      LowCardinality(String)  COMMENT 'Тип устройства: desktop, mobile',
    os               LowCardinality(String)  COMMENT 'Операционная система',
    region           LowCardinality(String)  COMMENT 'Регион пользователя',
    had_click        UInt8                   COMMENT 'Первичная метрика: 1 если был клик по объявлению в период теста',
    had_contact      UInt8                   COMMENT 'Гардрейл метрика: 1 если был контакт с продавцом в период теста',
    n_page_views     UInt32                  COMMENT 'Количество просмотров страниц в период теста',
    n_clicks         UInt32                  COMMENT 'Количество кликов по объявлениям в период теста',
    n_contacts       UInt32                  COMMENT 'Количество контактов с продавцом в период теста'
) ENGINE = MergeTree()
ORDER BY (analysis_id)
COMMENT 'Витрина A/B теста: одна строка на пользователя, участвовавшего в эксперименте';

INSERT INTO farpost.mart_ab_test
WITH base AS (
    SELECT
        -- Унифицированный идентификатор: user_id для зарегов, cookie_id для остальных
        CASE
            WHEN user_id != '00000000-0000-0000-0000-000000000000' THEN user_id
            ELSE cookie_id
        END AS analysis_id,
        experiment_group,
        is_registered,
        user_type,
        device_type,
        os,
        region,
        event_type
    FROM farpost.stg_autoparts_events
    WHERE experiment_group IN ('control', 'treatment')
      AND event_timestamp BETWEEN '2026-03-30' AND '2026-04-27'
)
SELECT
    analysis_id,
    any(experiment_group) AS experiment_group,
    any(is_registered)    AS is_registered,
    any(user_type)        AS user_type,
    any(device_type)      AS device_type,
    any(os)               AS os,
    any(region)           AS region,
    toUInt8(countIf(event_type = 'listing_click') > 0)  AS had_click,
    toUInt8(countIf(event_type = 'contact_seller') > 0) AS had_contact,
    countIf(event_type = 'page_view')      AS n_page_views,
    countIf(event_type = 'listing_click')  AS n_clicks,
    countIf(event_type = 'contact_seller') AS n_contacts
FROM base
GROUP BY analysis_id;