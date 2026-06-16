Тестовое задание — Продуктовый аналитик Фарпост

Задачи

Задача 1 — Дизайн A/B теста (раздел Автозапчасти)

Оценка эффекта от смены вида отображения объявлений: список - плитка


Дизайн теста: гипотеза, первичная метрика (CTR) и guardrail-метрика (contact rate), разбивка трафика 50/50, длительность с учётом эффекта новизны
Расчёт размера выборки и статистической мощности (MDE)
Способы оценки результата: Z-тест, доверительные интервалы, p-value


📁 ab-test-design/01_ab_test_design.ipynb — основной ноутбук: дизайн теста, расчёты, оценка результата  
📁 ab-test-design/ab_test_mart_ddl.sql — DDL + INSERT витрины mart_ab_test   
📁 ab-test-design/generate_data.py — генерация синтетических событий и назначений A/B-группы, загрузка в ClickHouse  
📁 ab-test-design/check_dates.py — проверка диапазона дат сгенерированных данных относительно периода теста  


Задача 2 — Дашборд метрик (раздел Недвижимость)

Проектирование дашборда для регулярного мониторинга здоровья продукта


Выбор метрик с обоснованием (DAU/MAU, Retention D7/D30, конверсия в клик, конверсия в контакт с продавцом и др.)
Визуализация и структура дашборда: вкладки KPI / Распределение посещений / Детализация
Фильтры и период агрегации
Гипотезы для анализа динамики


📁 dashboard/reality_dashboard_mart_ddl.sql — агрегированная витрина по дням и категориям (источник для KPI и распределений)  
📁 dashboard/mart_reality_retention.sql — когортная витрина для расчёта Retention/Churn по дням с первого визита  


Архитектура данных

generate_data.py
      │
      ▼
ClickHouse: raw_events + experiment_assignments     (сырые данные)
      │
      ▼
dbt staging: stg_autoparts_events / stg_realty_events     (чистка + джойн с группой эксперимента)
      │
      ▼
SQL-витрины: mart_ab_test, reality_dashboard_mart, mart_reality_retention
      │
      ▼
Ноутбук (A/B тест) / Дашборд (Недвижимость)

raw_events не содержит информацию об эксперименте — назначение группы хранится отдельно в experiment_assignments (имитирует GrowthBook) и присоединяется только на staging-слое в dbt. Так raw остаётся неизменным источником истины, а бизнес-логика эксперимента живёт отдельно.


Структура репозитория

farpost-analyst-test/
├── ab-test-design/                      # Задача 1 - A/B тест
│   ├── 01_ab_test_design.ipynb          # Дизайн теста, расчёты, оценка результата
│   ├── ab_test_mart_ddl.sql             # DDL + INSERT витрины mart_ab_test
│   ├── check_dates.py                   # Проверка дат данных vs период теста
│   └── generate_data.py                 # Генерация событий - ClickHouse
│
├── dashboard/                           # Задача 2 - Дашборд
│   ├── reality_dashboard_mart_ddl.sql   # Витрина по дням/категориям для KPI
│   └── mart_reality_retention.sql       # Когортная витрина Retention
│
├── dbt/                                  # Staging-слой, общий для обеих задач
│   └── models/
│       ├── sources.yml                   # Источники: raw_events, experiment_assignments
│       └── staging/
│           ├── schema.yml                # Описания колонок staging-моделей
│           ├── stg_autoparts_events.sql  # Автозапчасти + джойн с experiment_assignments
│           └── stg_realty_events.sql     # Недвижимость, без A/B-группы
│
├── .env.example                          # Шаблон переменных подключения к ClickHouse
├── .gitignore
└── README.md


Остальная структура dbt/ (analyses, macros, seeds, snapshots, tests, target, logs, dbt_project.yml) - шаблоны dbt




Стек


Python: pandas, numpy, scipy, matplotlib, seaborn, clickhouse-connect
Jupyter Notebooks
ClickHouse — хранилище данных
dbt — staging-трансформации и документация моделей
SQL — витрины для аналитики
Superset — отчетная система для дашборда
