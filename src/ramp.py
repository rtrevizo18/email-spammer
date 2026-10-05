"""Warm-up schedule: how many emails may go out on each day of the campaign."""
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


def daily_cap(default_cap):
    """Today's send cap.

    RAMP_START_DATE=YYYY-MM-DD and RAMP_QUOTAS=150,400,1000 mean day 1 allows 150 sends,
    day 2 allows 400, day 3 and later allow 1000. Without both, fall back to `default_cap`.
    """
    start_text = os.getenv("RAMP_START_DATE")
    quotas_text = os.getenv("RAMP_QUOTAS")
    if not start_text or not quotas_text:
        return default_cap

    quotas = [int(q) for q in quotas_text.split(",") if q.strip()]
    today = datetime.now(CENTRAL_TZ).date()
    day_index = (today - date.fromisoformat(start_text)).days
    if day_index < 0:
        return 0
    return quotas[min(day_index, len(quotas) - 1)]
