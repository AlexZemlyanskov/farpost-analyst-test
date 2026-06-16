-- Витрина метрик раздела Недвижимость для дашборда в Superset.
-- Гранулярность: день,  категория, регион, устройство, тип пользователя.

DROP TABLE IF EXISTS farpost.mart_realty_dashboard;

CREATE TABLE farpost.mart_realty_dashboard (
    event_date       Date                    COMMENT 'Дата (день)',
    day_of_week      UInt8                   COMMENT 'День недели: 1=понедельник ... 7=воскресенье',
    is_weekend       UInt8                   COMMENT '1 если суббота или воскресенье',
    category         LowCardinality(String)  COMMENT 'Категория объявления',
    region           LowCardinality(String)  COMMENT 'Регион пользователя',
    device_type      LowCardinality(String)  COMMENT 'Тип устройства: desktop, mobile',
    user_type        LowCardinality(String)  COMMENT 'Тип пользователя: registered, cookie, anonymous',
    n_unique_users   UInt64                  COMMENT 'Уникальные пользователи в этом срезе',
    n_page_views     UInt64                  COMMENT 'Просмотры страниц',
    n_listing_clicks UInt64                  COMMENT 'Клики по объявлениям',
    n_contacts       UInt64                  COMMENT 'Контакты с продавцом',
    n_favorites      UInt64                  COMMENT 'Добавления в избранное',
    n_searches       UInt64                  COMMENT 'Использования текстового поиска',
    n_filters        UInt64                  COMMENT 'Применения фильтров',
    n_publishes      UInt64                  COMMENT 'Опубликованные объявления'
) ENGINE = MergeTree()
ORDER BY (event_date, category, region, device_type, user_type)
COMMENT 'Витрина метрик раздела Недвижимость для дашборда в Superset';

INSERT INTO farpost.mart_realty_dashboard
SELECT
    toDate(event_timestamp) AS event_date,
    toDayOfWeek(event_timestamp) AS day_of_week,
    if(toDayOfWeek(event_timestamp) IN (6, 7), 1, 0) AS is_weekend,
    category,
    region,
    device_type,
    user_type,
    uniqExact(
        multiIf(user_id != '00000000-0000-0000-0000-000000000000', user_id, cookie_id)
    ) AS n_unique_users,
    countIf(event_type = 'page_view')       AS n_page_views,
    countIf(event_type = 'listing_click')   AS n_listing_clicks,
    countIf(event_type = 'contact_seller')  AS n_contacts,
    countIf(event_type = 'favorite_add')    AS n_favorites,
    countIf(event_type = 'search')          AS n_searches,
    countIf(event_type = 'filter_apply')    AS n_filters,
    countIf(event_type = 'listing_publish') AS n_publishes
FROM farpost.stg_realty_events
GROUP BY event_date, day_of_week, is_weekend, category, region, device_type, user_type;