"""
Проверяем, какие дни недели охватывает период A/B теста, чтобы учесть сезонность при анализе результатов.
"""
from datetime import datetime, timedelta

END_DATE = datetime(2026, 5, 31)
START_DATE = END_DATE - timedelta(days=90)

ab_start = START_DATE + timedelta(days=31)
ab_end = START_DATE + timedelta(days=60)

print(f"Старт теста: {ab_start.date()} ({ab_start.strftime('%A')})")
print(f"Конец теста: {ab_end.date()} ({ab_end.strftime('%A')})")
print(f"Дней: {(ab_end - ab_start).days}")


ab_start = START_DATE + timedelta(days=28)
ab_end = ab_start + timedelta(weeks=4)  # ровно 4 полные недели

print(f"Старт: {ab_start.date()} ({ab_start.strftime('%A')})")
print(f"Конец: {ab_end.date()} ({ab_end.strftime('%A')})")
print(f"Дней: {(ab_end - ab_start).days}")