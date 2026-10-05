"""Mark bounced contacts in the sheet and trip a kill switch if too many sends bounce."""
import os

from status import Status

MAX_BOUNCE_RATE = float(os.getenv("MAX_BOUNCE_RATE", "0.05"))
# Rates on a handful of sends are noise; don't trip until we have this many sends.
MIN_SAMPLE_SIZE = int(os.getenv("KILL_SWITCH_MIN_SAMPLE", "50"))

# Only rows that haven't reached a terminal state can be reclassified.
RECLASSIFIABLE = {Status.NEW.value, Status.SCHEDULED.value, Status.SENT.value, ""}


def apply_bounces(rows, bounced, update_cells, row_number):
    """Mark bounced contacts in the sheet (and in `rows`) so they are never sent to again."""
    changed = 0
    for row in rows:
        if str(row.get("Status") or "") not in RECLASSIFIABLE:
            continue
        addresses = [a.strip().lower() for a in str(row.get("Email", "")).split(",")]
        if not any(addr in bounced for addr in addresses):
            continue
        update_cells({f"F{row_number(row)}": Status.BOUNCED.value})
        row["Status"] = Status.BOUNCED.value
        changed += 1
    return changed


def check_health(rows):
    """Return (healthy, message). Unhealthy means the caller should stop sending."""
    statuses = [str(row.get("Status") or "") for row in rows]
    bounced = statuses.count(Status.BOUNCED.value)
    attempted = statuses.count(Status.SENT.value) + bounced
    if attempted < MIN_SAMPLE_SIZE:
        return True, f"{attempted} sends so far; below kill-switch sample size."

    bounce_rate = bounced / attempted
    summary = f"bounce={bounce_rate:.2%} over {attempted} sends"
    if bounce_rate > MAX_BOUNCE_RATE:
        return False, f"Bounce rate above {MAX_BOUNCE_RATE:.2%}: {summary}"
    return True, summary
