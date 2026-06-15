"""
Генерация синтетических данных веб-аналитики для тестового задания Фарпост.
 
Имитирует логи сервиса веб-аналитики для двух разделов:
  - Автозапчасти: A/B тест смены вида отображения (список -> плитка)
  - Недвижимость: данные для дашборда метрик
 
Архитектура данных:
  raw_events             — сырые события без информации об эксперименте
  experiment_assignments — маппинг пользователь -> группа (имитирует GrowthBook)
 
 
Схема рандомизации:
  - Зарегистрированные: рандомизация по user_id
  - Незарегистрированные с cookie+fingerprint: рандомизация по cookie_id
  - Анонимы: исключены из теста, видят дефолтный вид (список)
  - AB группа назначается пользователю один раз и не меняется между сессиями
 
Метрики A/B теста:
  - Первичная: CTR (listing_click / page_view)
  - Гардрейл: contact_seller rate — защита от novelty effect
 
Запуск: python generate_data.py
Результат: таблицы farpost.raw_events и farpost.experiment_assignments в ClickHouse
"""

import uuid
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()

# Нулевой UUID используется вместо NULL для Nullable полей
ZERO_UUID = '00000000-0000-0000-0000-000000000000'

# UUID эксперимента (постоянный, идентифицирует конкретный A/B тест)
AB_EXPERIMENT_UUID = '550e8400-e29b-41d4-a716-446655440001'

# Реальный DAU по данным от команды, генерируем 10% как репрезентативную выборку, чтобы не перегружать ClickHouse и ускорить генерацию
REAL_DAU_PER_SECTION = 300_000 # реальный DAU для каждого раздела (автозапчасти и недвижимость)
SIMULATION_SCALE = 0.10 # скейлинг выборки
DAU = int(REAL_DAU_PER_SECTION * SIMULATION_SCALE) # DAU для симуляции

# Среднее количество сессий на пользователя за весь период
AVG_SESSIONS_PER_USER = 5

N_DAYS = 90 # генерируем 3 месяца данных, чтобы в A/B тесте был достаточный период до и после (31-60 день внутри окна наблюдения) и была видна сезонность (март)
END_DATE = datetime(2026, 5, 31) # определяем крайнюю дату для выборки
START_DATE = END_DATE - timedelta(days=N_DAYS) # определяем начальную дату для выборки 

# A/B тест: 4 полные недели, март-апрель 2026, чтобы захватить разные дни недели и не скашивать выборку.
AB_TEST_START = START_DATE + timedelta(days=28)  # 2026-03-30 (Понедельник)
AB_TEST_END = START_DATE + timedelta(days=56)    # 2026-04-27 (Понедельник)

# Генерируем батчами по 10 дней, чтобы не перегружать память
BATCH_DAYS = 10

np.random.seed(42)

# Доли типов пользователей
SHARE_REGISTERED = 0.35 # зарегистрированные пользователи, идентифицируются по user_id
SHARE_COOKIE = 0.45 # незарегистрированные, идентифицируются по cookie_id + fingerprint_id
SHARE_ANONYMOUS = 0.20 # анонимные без стабильных ID, исключены из A/B теста, видят дефолтный вид

REGIONS = ['Приморский край', 'Хабаровский край'] # сегментация по регионам, 62% и 38% соответственно, для проверки корректности генерации и возможности анализа по регионам в будущем
REGION_WEIGHTS = [0.62, 0.38] # распределение весов, просто предположение

DEVICES = ['desktop', 'mobile'] # распределение по типу устройства, 45% ПК и 55% мобильнео приложение, значение весов - предположение
DEVICE_WEIGHTS = [0.45, 0.55]

# ОС по типу устройства
OS_BY_DEVICE = {
    'desktop': (['Windows', 'macOS', 'Другие'], [0.75, 0.22, 0.03]),
    'mobile': (['Android', 'iOS'], [0.65, 0.35]),
}

# Категории объявлений и их популярность в каждом разделе, категории взяты с сайта и распределены по весам, просто для реалистичности данных и возможности анализа по категориям в будущем
AUTOPARTS_CATEGORIES = [
    'Выхлопная система',
    'Двигатель и элементы двигателя',
    'Детали кузова',
    'Дополнительное оборудование',
    'Запчасти для ТО',
    'Интерьер',
    'Оптика',
    'Расходники и комплектующие',
    'Система отопления и кондиционирования',
    'Система подачи воздуха',
    'Топливная система',
    'Тормозная система',
    'Трансмиссия',
    'Ходовая часть',
    'Электрика',
]
AUTOPARTS_WEIGHTS = [0.05, 0.12, 0.10, 0.05, 0.07, 0.04, 0.06, 0.08,
                     0.04, 0.03, 0.06, 0.07, 0.08, 0.09, 0.06]

REALTY_CATEGORIES = [
    'Аренда квартир',
    'Аренда домов и коттеджей',
    'Квартиры посуточно',
    'Аренда помещений',
    'Аренда земельных участков',
    'Аренда гаражей',
    'Продажа квартир',
    'Продажа домов, коттеджей и дач',
    'Продажа помещений',
    'Продажа земельных участков',
    'Продажа гаражей',
    'Куплю квартиру и недвижимость',
    'Недвижимость за границей',
    'Обмен недвижимости',
    'Сниму квартиру и недвижимость',
]
REALTY_WEIGHTS = [0.22, 0.10, 0.08, 0.06, 0.04, 0.03, 0.20, 0.10,
                  0.05, 0.05, 0.03, 0.02, 0.005, 0.005, 0.01]

# Вероятности событий в воронке Автозапчасти
AP_BASE_CTR = 0.35 # конверсия в клики, базовая для контрольной группы, в реальной жизни зависит от категории, региона, устройства и других факторов, но для простоты модели используем константное значение
AP_TREATMENT_CTR_LIFT = 1.12   # плитка даёт +12% конверсии. 12% это MDE, который мы расчитали экономически
AP_CONTACT_RATE = 0.18 # конверсия из кликов в объявления в контакты, базовая для контрольной группы
AP_TREATMENT_CONTACT_LIFT = 1.03  # закладываем небольшй подъем конверсии в контакты т.к. выдвигаем гипотезу об эффекте новизны


# Вероятности событий в воронке Недвижимость
RE_BASE_CTR = 0.42  # конверсия в клики, базовая для всех пользователей, в реальной жизни зависит от категории, региона, устройства и других факторов, но для простоты модели используем константное значение
RE_CONTACT_RATE = 0.12  # конверсия из кликов в объявления в контакты, базовая для всех пользователей
RE_FAVORITE_RATE = 0.22 # 22% кликнувших добавляют в избранное. Специфика недвижимости — люди сравнивают варианты, сохраняют понравившиеся.
RE_PUBLISH_RATE = 0.05 # 5% зарегистрированных пользователей публикуют объявления. Публикация доступна только зарегистрированным, т.к. требует авторизации + прдавцов меньше
RE_SEARCH_RATE = 0.55 # 55% пользователей используют поиск, чтобы найти объявления. Специфика недвижимости — пользователи ищут конкретные варианты, а не листают ленту.
RE_FILTER_RATE = 0.45  # чуть ниже поиска, не все кто ищет применяют фильтры
RE_MARCH_BOOST = 1.20  # сезонность: в марте активность выше на 20% (предположение)


def gen_uuids(n):
    """Генерирует список из n строк UUID. Рандомные гуиды"""
    return [str(uuid.uuid4()) for _ in range(n)]


def gen_timestamps(n, batch_start_date, batch_n_days):
    """
    Генерирует n временных меток с реалистичным внутрисуточным распределением.

    Пики активности: утром 9-12 и вечером 18-22, минимум ночью.
    """
    hour_weights = np.array(
        [1, 1, 1, 1, 1, 2, 3, 5, 8, 10, 10, 9, 7, 7, 7, 6, 7, 9, 10, 10, 8, 6, 4, 2],
        dtype=float
    ) # веса на каждый час, чтобы имитировать пики активности. Утро и вечер — пиковые часы, ночь — минимум.
    hour_weights /= hour_weights.sum() # трансформируем веса в вероятности

    day_weights = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.3, 1.2])  # пн-вс
    # нормализуем на количество дней в батче
    batch_day_weights = np.array([
        day_weights[((batch_start_date + timedelta(days=i)).weekday())]
        for i in range(batch_n_days)
    ])
    batch_day_weights /= batch_day_weights.sum()

    days = np.random.choice(batch_n_days, n, p=batch_day_weights)
    hours = np.random.choice(24, n, p=hour_weights)
    minutes = np.random.randint(0, 60, n)
    seconds = np.random.randint(0, 60, n)

    start_ts = int(batch_start_date.timestamp())
    offsets = days * 86400 + hours * 3600 + minutes * 60 + seconds

    return pd.to_datetime(start_ts + offsets, unit='s')


def create_user_pool(n_users):
    """
    Создаёт пул уникальных пользователей со стабильными атрибутами.
 
    Атрибуты пользователя (устройство, регион, тип) не меняются между сессиями.
    AB группа назначается один раз и хранится в пуле для использования
    при генерации реалистичного поведения (CTR lift для treatment).
    В raw_events группа не попадает — она хранится в experiment_assignments.
 
    Args:
        n_users: количество уникальных пользователей в пуле
    """
    user_types = np.random.choice(
        ['registered', 'cookie', 'anonymous'],
        size=n_users,
        p=[SHARE_REGISTERED, SHARE_COOKIE, SHARE_ANONYMOUS]
    )
 
    is_registered = (user_types == 'registered').astype(int)
    is_trackable = np.isin(user_types, ['registered', 'cookie'])
 
    all_uuids = np.array(gen_uuids(n_users))
    cookie_uuids = np.array(gen_uuids(n_users))
    fp_uuids = np.array(gen_uuids(n_users))
 
    user_ids = np.where(user_types == 'registered', all_uuids, ZERO_UUID)
    cookie_ids = np.where(is_trackable, cookie_uuids, ZERO_UUID)
    fingerprint_ids = np.where(is_trackable, fp_uuids, ZERO_UUID)
 
    devices = np.random.choice(DEVICES, size=n_users, p=DEVICE_WEIGHTS)
    os_list = [np.random.choice(OS_BY_DEVICE[d][0], p=OS_BY_DEVICE[d][1]) for d in devices]
    regions = np.random.choice(REGIONS, size=n_users, p=REGION_WEIGHTS)
 
    raw_ab_groups = np.random.choice(['control', 'treatment'], size=n_users)
    ab_groups = np.where(is_trackable, raw_ab_groups, 'none')
 
    return pd.DataFrame({
        'user_type': user_types,
        'is_registered': is_registered,
        'user_id': user_ids,
        'cookie_id': cookie_ids,
        'fingerprint_id': fingerprint_ids,
        'device_type': devices,
        'os': os_list,
        'region': regions,
        'ab_group': ab_groups,
    })
 
 
def sample_users(user_pool, n_sessions):
    """
    Сэмплирует n_sessions пользователей из пула с возвращением.
 
    Один и тот же пользователь может быть выбран несколько раз —
    он приходит на сайт в разные дни с разными сессиями.
    """
    indices = np.random.randint(0, len(user_pool), size=n_sessions)
    return user_pool.iloc[indices].reset_index(drop=True)
 
 
def sessions_to_events(sessions, event_masks):
    """
    Разворачивает датафрейм сессий в плоскую таблицу событий.
 
    Каждая сессия порождает page_view + набор downstream событий
    в зависимости от масок в event_masks.
 
    Args:
        sessions: датафрейм сессий
        event_masks: dict {event_type: bool Series или None если событие всегда есть}
 
    Returns:
        датафрейм событий без experiment полей
    """
    base_cols = [
        'session_id', 'event_timestamp', 'section',
        'user_type', 'is_registered', 'user_id', 'cookie_id', 'fingerprint_id',
        'device_type', 'os', 'region', 'category', 'listing_id',
    ]
 
    parts = []
    for event_type, mask in event_masks.items():
        subset = sessions[base_cols].copy() if mask is None else sessions.loc[mask, base_cols].copy()
 
        subset['event_id'] = gen_uuids(len(subset))
        subset['event_type'] = event_type
 
        if event_type != 'page_view':
            offset = pd.to_timedelta(np.random.randint(5, 300, len(subset)), unit='s')
            subset['event_timestamp'] = subset['event_timestamp'] + offset
 
        if event_type in ('page_view', 'search', 'filter_apply'):
            subset['listing_id'] = ZERO_UUID
 
        parts.append(subset)
 
    return pd.concat(parts, ignore_index=True)
 
 
def generate_autoparts_batch(user_pool, batch_start_date, batch_n_days):
    """
    Генерирует батч событий для раздела Автозапчасти.
 
    AB группа берётся из пула пользователей и используется для генерации
    реалистичного поведения (CTR lift), но не записывается в события.
    Привязка события к группе происходит в staging через джойн
    с таблицей experiment_assignments.
    """
    n = DAU * batch_n_days
    users = sample_users(user_pool, n)
    timestamps = gen_timestamps(n, batch_start_date, batch_n_days)
    categories = np.random.choice(AUTOPARTS_CATEGORIES, size=n, p=AUTOPARTS_WEIGHTS)
 
    in_ab_period = (
        (timestamps >= pd.Timestamp(AB_TEST_START)) &
        (timestamps <= pd.Timestamp(AB_TEST_END))
    )
    in_treatment = (
        in_ab_period &
        (users['ab_group'].values == 'treatment')
    )
 
    ctr = np.where(in_treatment, AP_BASE_CTR * AP_TREATMENT_CTR_LIFT, AP_BASE_CTR)
    contact_rate = np.where(in_treatment, AP_CONTACT_RATE * AP_TREATMENT_CONTACT_LIFT, AP_CONTACT_RATE)
 
    had_click = np.random.random(n) < ctr
    had_contact = had_click & (np.random.random(n) < contact_rate)
    listing_ids = np.where(had_click, gen_uuids(n), ZERO_UUID)
 
    sessions = pd.DataFrame({
        'session_id': gen_uuids(n),
        'event_timestamp': timestamps,
        'section': 'autoparts',
        'user_type': users['user_type'].values,
        'is_registered': users['is_registered'].values,
        'user_id': users['user_id'].values,
        'cookie_id': users['cookie_id'].values,
        'fingerprint_id': users['fingerprint_id'].values,
        'device_type': users['device_type'].values,
        'os': users['os'].values,
        'region': users['region'].values,
        'category': categories,
        'listing_id': listing_ids,
        'had_click': had_click,
        'had_contact': had_contact,
    })
 
    event_masks = {
        'page_view': None,
        'listing_click': sessions['had_click'],
        'contact_seller': sessions['had_contact'],
    }
 
    return sessions_to_events(sessions, event_masks)
 
 
def generate_realty_batch(user_pool, batch_start_date, batch_n_days):
    """
    Генерирует батч событий для раздела Недвижимость.
 
    Нет A/B теста — данные используются для дашборда метрик.
    Сезонность: в марте активность выше на 20%.
    """
    n = DAU * batch_n_days
    users = sample_users(user_pool, n)
    timestamps = gen_timestamps(n, batch_start_date, batch_n_days)
    categories = np.random.choice(REALTY_CATEGORIES, size=n, p=REALTY_WEIGHTS)
 
    is_march = pd.DatetimeIndex(timestamps).month == 3
    boost = np.where(is_march, RE_MARCH_BOOST, 1.0)
 
    had_click = np.random.random(n) < RE_BASE_CTR * boost
    had_contact = had_click & (np.random.random(n) < RE_CONTACT_RATE * boost)
    had_favorite = had_click & (np.random.random(n) < RE_FAVORITE_RATE)
    had_search = np.random.random(n) < RE_SEARCH_RATE
    had_filter = np.random.random(n) < RE_FILTER_RATE
    had_publish = (users['is_registered'].values == 1) & (np.random.random(n) < RE_PUBLISH_RATE)
 
    listing_ids = np.where(had_click, gen_uuids(n), ZERO_UUID)
    publish_listing_ids = np.where(had_publish, gen_uuids(n), ZERO_UUID)
 
    sessions = pd.DataFrame({
        'session_id': gen_uuids(n),
        'event_timestamp': timestamps,
        'section': 'realty',
        'user_type': users['user_type'].values,
        'is_registered': users['is_registered'].values,
        'user_id': users['user_id'].values,
        'cookie_id': users['cookie_id'].values,
        'fingerprint_id': users['fingerprint_id'].values,
        'device_type': users['device_type'].values,
        'os': users['os'].values,
        'region': users['region'].values,
        'category': categories,
        'listing_id': listing_ids,
        'had_click': had_click,
        'had_contact': had_contact,
        'had_favorite': had_favorite,
        'had_search': had_search,
        'had_filter': had_filter,
        'had_publish': had_publish,
        'publish_listing_id': publish_listing_ids,
    })
 
    event_masks = {
        'page_view': None,
        'listing_click': sessions['had_click'],
        'contact_seller': sessions['had_contact'],
        'favorite_add': sessions['had_favorite'],
        'search': sessions['had_search'],
        'filter_apply': sessions['had_filter'],
    }
 
    events = sessions_to_events(sessions, event_masks)
 
    pub_sessions = sessions[sessions['had_publish']].copy()
    if len(pub_sessions) > 0:
        pub_events = pub_sessions[[
            'session_id', 'event_timestamp', 'section',
            'user_type', 'is_registered', 'user_id', 'cookie_id', 'fingerprint_id',
            'device_type', 'os', 'region', 'category',
        ]].copy()
        pub_events['listing_id'] = pub_sessions['publish_listing_id'].values
        pub_events['event_id'] = gen_uuids(len(pub_events))
        pub_events['event_type'] = 'listing_publish'
        offset = pd.to_timedelta(np.random.randint(60, 600, len(pub_events)), unit='s')
        pub_events['event_timestamp'] = pub_events['event_timestamp'] + offset
        events = pd.concat([events, pub_events], ignore_index=True)
 
    return events
 
 
def create_raw_events_table(client):
    """Удаляет и создаёт таблицу raw_events без полей эксперимента."""
    client.command("DROP TABLE IF EXISTS farpost.raw_events")
    client.command("""
        CREATE TABLE farpost.raw_events (
            event_id        FixedString(36)         COMMENT 'UUID события',
            event_timestamp DateTime                COMMENT 'Время события (UTC)',
            section         LowCardinality(String)  COMMENT 'Раздел сайта: autoparts, realty',
            event_type      LowCardinality(String)  COMMENT 'Тип события: page_view, listing_click, contact_seller, search, filter_apply, favorite_add, listing_publish',
            user_type       LowCardinality(String)  COMMENT 'Тип пользователя: registered, cookie, anonymous',
            is_registered   UInt8                   COMMENT '1 если пользователь зарегистрирован',
            user_id         FixedString(36)         COMMENT 'UUID зарегистрированного пользователя, нули если не зарегистрирован',
            cookie_id       FixedString(36)         COMMENT 'UUID cookie, нули если отсутствует',
            fingerprint_id  FixedString(36)         COMMENT 'UUID device fingerprint, нули если отсутствует',
            session_id      FixedString(36)         COMMENT 'UUID сессии',
            category        LowCardinality(String)  COMMENT 'Категория объявления',
            listing_id      FixedString(36)         COMMENT 'UUID объявления, нули если событие не связано с объявлением',
            device_type     LowCardinality(String)  COMMENT 'Тип устройства: desktop, mobile',
            os              LowCardinality(String)  COMMENT 'Операционная система',
            region          LowCardinality(String)  COMMENT 'Регион пользователя'
        ) ENGINE = MergeTree()
        ORDER BY (section, event_timestamp, event_type)
        COMMENT 'Сырые события веб-аналитики Фарпост. 10% выборка (реальный DAU: 300k/раздел). Без полей эксперимента — они хранятся в experiment_assignments.'
    """)
    print("Таблица farpost.raw_events создана")
 
 
def create_experiment_assignments_table(client):
    """
    Удаляет и создаёт таблицу назначений пользователей в группы A/B теста.
 
    Имитирует таблицу которую в продакшне создаёт GrowthBook или аналогичный
    фреймворк в момент первого показа варианта пользователю.
    Staging модель джойнит raw_events с этой таблицей для анализа.
    """
    client.command("DROP TABLE IF EXISTS farpost.experiment_assignments")
    client.command("""
        CREATE TABLE farpost.experiment_assignments (
            assignment_id    FixedString(36)         COMMENT 'UUID записи о назначении',
            experiment_id    FixedString(36)         COMMENT 'UUID эксперимента',
            user_id          FixedString(36)         COMMENT 'UUID зарегистрированного пользователя, нули если не зарегистрирован',
            cookie_id        FixedString(36)         COMMENT 'UUID cookie пользователя',
            experiment_group LowCardinality(String)  COMMENT 'Группа: control или treatment',
            assigned_at      DateTime                COMMENT 'Время первого показа варианта пользователю'
        ) ENGINE = MergeTree()
        ORDER BY (experiment_id, assigned_at)
        COMMENT 'Назначения пользователей в группы A/B теста.'
    """)
    print("Таблица farpost.experiment_assignments создана")
 
 
def insert_experiment_assignments(client, user_pool):
    """
    Вставляет назначения в группы для всех trackable пользователей пула.
 
    assigned_at — случайное время в первые 3 дня теста,
    имитирует момент первого показа варианта пользователю.
    """
    trackable = user_pool[user_pool['ab_group'] != 'none'].copy()
    n = len(trackable)
 
    start_ts = int(AB_TEST_START.timestamp())
    end_ts = int((AB_TEST_START + timedelta(days=3)).timestamp())
    assigned_at = pd.to_datetime(
        np.random.randint(start_ts, end_ts, n), unit='s'
    )
 
    assignments = pd.DataFrame({
        'assignment_id': gen_uuids(n),
        'experiment_id': AB_EXPERIMENT_UUID,
        'user_id': trackable['user_id'].values,
        'cookie_id': trackable['cookie_id'].values,
        'experiment_group': trackable['ab_group'].values,
        'assigned_at': assigned_at,
    })
 
    client.insert_df('farpost.experiment_assignments', assignments)
    print(f"Вставлено {n:,} назначений в farpost.experiment_assignments")
 
 
def insert_batch(client, df):
    """Вставляет батч событий в raw_events."""
    cols = [
        'event_id', 'event_timestamp', 'section', 'event_type',
        'user_type', 'is_registered', 'user_id', 'cookie_id', 'fingerprint_id',
        'session_id', 'category', 'listing_id', 'device_type', 'os', 'region',
    ]
    client.insert_df('farpost.raw_events', df[cols])
 
 
def main():
    """
    Основная функция: создаёт таблицы, пулы пользователей,
    генерирует события батчами и загружает в ClickHouse.
    """
    client = clickhouse_connect.get_client(
        host=os.getenv('CLICKHOUSE_HOST'),
        port=int(os.getenv('CLICKHOUSE_PORT', 8123)),
        username=os.getenv('CLICKHOUSE_USER'),
        password=os.getenv('CLICKHOUSE_PASSWORD'),
        database=os.getenv('CLICKHOUSE_DATABASE', 'farpost'),
    )
 
    create_raw_events_table(client)
    create_experiment_assignments_table(client)
 
    n_unique_users = int(DAU * N_DAYS / AVG_SESSIONS_PER_USER)
    print(f"Создание пулов пользователей ({n_unique_users:,} уникальных на раздел)...")
 
    ap_user_pool = create_user_pool(n_unique_users)
    re_user_pool = create_user_pool(n_unique_users)
 
    insert_experiment_assignments(client, ap_user_pool)
 
    total_events = 0
    n_batches = N_DAYS // BATCH_DAYS
 
    for batch_num in range(n_batches):
        batch_start = START_DATE + timedelta(days=batch_num * BATCH_DAYS)
        batch_days = min(BATCH_DAYS, N_DAYS - batch_num * BATCH_DAYS)
 
        print(f"Батч {batch_num + 1}/{n_batches}: {batch_start.date()} — {(batch_start + timedelta(days=batch_days)).date()}")
 
        ap_events = generate_autoparts_batch(ap_user_pool, batch_start, batch_days)
        re_events = generate_realty_batch(re_user_pool, batch_start, batch_days)
        batch_df = pd.concat([ap_events, re_events], ignore_index=True)
 
        insert_batch(client, batch_df)
        total_events += len(batch_df)
        print(f"  Вставлено {len(batch_df):,} событий (всего: {total_events:,})")
 
    print("\n Готово!")
    print(f"   farpost.raw_events: {total_events:,} событий")
    print(f"   farpost.experiment_assignments: {n_unique_users:,} назначений")
    print(f"   Период: {START_DATE.date()} — {END_DATE.date()}")
    print(f"   A/B тест: {AB_TEST_START.date()} — {AB_TEST_END.date()}")
 
 
if __name__ == '__main__':
    main()