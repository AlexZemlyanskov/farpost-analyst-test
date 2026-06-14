"""
Генерация синтетических данных веб-аналитики для тестового задания Фарпост.
Пишет напрямую в ClickHouse (DROP + CREATE + INSERT).

Запуск: python generate_data.py
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import uuid
import os
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()

# ─── Подключение к ClickHouse ─────────────────────────────────────────────────

client = clickhouse_connect.get_client(
    host=os.getenv("CLICKHOUSE_HOST"),
    port=int(os.getenv("CLICKHOUSE_PORT", 8123)),
    username=os.getenv("CLICKHOUSE_USER"),
    password=os.getenv("CLICKHOUSE_PASSWORD"),
    database=os.getenv("CLICKHOUSE_DATABASE", "farpost"),
)

# ─── Параметры ────────────────────────────────────────────────────────────────

N_USERS_AUTOPARTS = 8_000
N_USERS_REALTY    = 12_000
N_DAYS            = 90
AB_TEST_START_DAY = 30
AB_TEST_END_DAY   = 60

END_DATE   = datetime(2025, 3, 31)
START_DATE = END_DATE - timedelta(days=N_DAYS)

np.random.seed(42)
random.seed(42)

# ─── Справочники ──────────────────────────────────────────────────────────────

REGIONS = [
    "Приморский край", "Хабаровский край", "Амурская область",
    "Сахалинская область", "Камчатский край", "Магаданская область",
    "Еврейская АО", "Чукотский АО"
]
REGION_WEIGHTS = [0.40, 0.22, 0.12, 0.10, 0.07, 0.04, 0.03, 0.02]

DEVICES   = ["desktop", "mobile", "tablet"]
D_WEIGHTS = [0.45, 0.48, 0.07]

OS_MAP = {
    "desktop": ["Windows", "macOS", "Linux"],
    "mobile":  ["Android", "iOS"],
    "tablet":  ["Android", "iOS"],
}

AUTOPARTS_CATEGORIES = [
    "Двигатель", "Кузов", "Трансмиссия", "Электрика",
    "Подвеска", "Тормоза", "Оптика", "Шины и диски"
]

REALTY_CATEGORIES = [
    "Квартиры вторичные", "Квартиры новостройки", "Дома и дачи",
    "Земельные участки", "Коммерческая недвижимость", "Гаражи"
]
REALTY_CAT_WEIGHTS = [0.38, 0.22, 0.18, 0.10, 0.08, 0.04]

# ─── Вспомогательные функции ──────────────────────────────────────────────────

def random_timestamp(start, end):
    date = start + timedelta(days=random.randint(0, (end - start).days))
    hour_weights = [1,1,1,1,1,2,3,5,8,10,10,9,7,7,7,6,7,9,10,10,8,6,4,2]
    hour = random.choices(range(24), weights=hour_weights)[0]
    return date.replace(hour=hour, minute=random.randint(0,59), second=random.randint(0,59))

def make_user_pool(n, section):
    devices = random.choices(DEVICES, weights=D_WEIGHTS, k=n)
    return pd.DataFrame({
        "user_id":       [f"{section[:2].upper()}-{str(uuid.uuid4())[:8]}" for _ in range(n)],
        "region":        random.choices(REGIONS, weights=REGION_WEIGHTS, k=n),
        "device_type":   devices,
        "os":            [random.choice(OS_MAP[d]) for d in devices],
        "is_registered": np.random.choice([True, False], size=n, p=[0.35, 0.65]),
    })

def make_event(event_type, ts, user, session_id, section, category,
               exp_id=None, exp_group=None, listing_id=None, offset_sec=0):
    return {
        "event_id":         str(uuid.uuid4()),
        "event_timestamp":  ts + timedelta(seconds=offset_sec),
        "user_id":          user["user_id"],
        "session_id":       session_id,
        "event_type":       event_type,
        "section":          section,
        "category":         category,
        "experiment_id":    exp_id,
        "experiment_group": exp_group,
        "listing_id":       listing_id,
        "device_type":      user["device_type"],
        "os":               user["os"],
        "region":           user["region"],
        "is_registered":    user["is_registered"],
    }

# ─── Генерация Автозапчасти ───────────────────────────────────────────────────

def generate_autoparts_events(users):
    ab_start = START_DATE + timedelta(days=AB_TEST_START_DAY)
    ab_end   = START_DATE + timedelta(days=AB_TEST_END_DAY)
    users = users.copy()
    n = len(users)
    users["ab_group"] = np.where(np.arange(n) < n // 2, "control", "treatment")

    records = []
    for _, user in users.iterrows():
        for _ in range(np.random.poisson(3)):
            ts         = random_timestamp(START_DATE, END_DATE)
            session_id = str(uuid.uuid4())[:12]
            in_ab      = ab_start <= ts <= ab_end
            exp_id     = "exp_layout_001" if in_ab else None
            exp_group  = user["ab_group"] if in_ab else None
            category   = random.choice(AUTOPARTS_CATEGORIES)

            records.append(make_event("page_view", ts, user, session_id, "autoparts", category, exp_id, exp_group))

            ctr = 0.35 * (1.12 if (in_ab and exp_group == "treatment") else 1.0)
            if random.random() < ctr:
                lid = f"AP-{random.randint(100000, 999999)}"
                records.append(make_event("listing_click", ts, user, session_id, "autoparts", category, exp_id, exp_group, lid, random.randint(5, 60)))
                if random.random() < 0.18:
                    records.append(make_event("contact_seller", ts, user, session_id, "autoparts", category, exp_id, exp_group, lid, random.randint(30, 180)))

            if random.random() < 0.40:
                records.append(make_event("search", ts, user, session_id, "autoparts", category, exp_id, exp_group, offset_sec=random.randint(2, 30)))

    return pd.DataFrame(records)

# ─── Генерация Недвижимость ───────────────────────────────────────────────────

def generate_realty_events(users):
    records = []
    for _, user in users.iterrows():
        for _ in range(np.random.poisson(2)):
            ts         = random_timestamp(START_DATE, END_DATE)
            session_id = str(uuid.uuid4())[:12]
            boost      = 1.2 if ts.month == 3 else 1.0
            category   = random.choices(REALTY_CATEGORIES, weights=REALTY_CAT_WEIGHTS)[0]

            records.append(make_event("page_view", ts, user, session_id, "realty", category))

            if random.random() < 0.42 * boost:
                lid = f"RE-{random.randint(100000, 999999)}"
                records.append(make_event("listing_click", ts, user, session_id, "realty", category, listing_id=lid, offset_sec=random.randint(10, 90)))
                if random.random() < 0.22:
                    records.append(make_event("favorite_add", ts, user, session_id, "realty", category, listing_id=lid, offset_sec=random.randint(30, 120)))
                if random.random() < 0.12 * boost:
                    records.append(make_event("contact_seller", ts, user, session_id, "realty", category, listing_id=lid, offset_sec=random.randint(60, 300)))

            if user["is_registered"] and random.random() < 0.05:
                records.append(make_event("listing_publish", ts, user, session_id, "realty", category,
                                          listing_id=f"RE-{random.randint(100000, 999999)}", offset_sec=random.randint(120, 600)))

            if random.random() < 0.55:
                records.append(make_event("search", ts, user, session_id, "realty", category, offset_sec=random.randint(2, 20)))

    return pd.DataFrame(records)

# ─── Загрузка в ClickHouse ────────────────────────────────────────────────────

def load_to_clickhouse(df):
    print("Создание таблицы в ClickHouse...")
    client.command("DROP TABLE IF EXISTS farpost.raw_events")
    client.command("""
        CREATE TABLE farpost.raw_events (
            event_id          String,
            event_timestamp   DateTime,
            user_id           String,
            session_id        String,
            event_type        String,
            section           String,
            category          String,
            experiment_id     Nullable(String),
            experiment_group  Nullable(String),
            listing_id        Nullable(String),
            device_type       String,
            os                String,
            region            String,
            is_registered     UInt8
        ) ENGINE = MergeTree()
        ORDER BY (section, event_timestamp)
    """)

    print(f"Вставка {len(df):,} строк...")
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
    df["is_registered"]   = df["is_registered"].astype(int)
    df = df.fillna("")  # Nullable поля — пустая строка вместо None для вставки

    client.insert_df("farpost.raw_events", df)
    print("✅ Данные загружены в farpost.raw_events")

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Генерация пользователей...")
    users_ap = make_user_pool(N_USERS_AUTOPARTS, "autoparts")
    users_re = make_user_pool(N_USERS_REALTY,    "realty")

    print("Генерация событий Автозапчасти...")
    df_ap = generate_autoparts_events(users_ap)

    print("Генерация событий Недвижимость...")
    df_re = generate_realty_events(users_re)

    df = pd.concat([df_ap, df_re], ignore_index=True)
    df = df.sort_values("event_timestamp").reset_index(drop=True)

    print(f"\nВсего событий: {len(df):,}")
    print(df["event_type"].value_counts().to_string())

    load_to_clickhouse(df)
