from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import random

central = ZoneInfo("America/Chicago")
utc = ZoneInfo("UTC")

def generate_schedule():
    now_central = datetime.now(central)

    start = now_central.replace(hour=8, minute=0, second=0, microsecond=0)
    end = now_central.replace(hour=14, minute=0, second=0, microsecond=0)

    total_minutes = int((end - start).total_seconds() / 60)

    random_minutes = sorted(random.sample(range(total_minutes), 20))

    scheduled_times_utc = []
    for m in random_minutes:
        send_time_central = start + timedelta(minutes=m)

        send_time_utc = send_time_central.astimezone(utc)

        scheduled_times_utc.append(send_time_utc)

    return scheduled_times_utc