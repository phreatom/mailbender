from datetime import datetime, timedelta, timezone

_ORDER = ["high", "medium", "low"]


def group_by_priority(rows):
    groups = []
    for level in _ORDER:
        matched = [r for r in rows if r.priority == level]
        groups.append({"priority": level, "count": len(matched), "rows": matched})
    return groups


def next_run_countdown(last_run_at, schedule_minutes: int, now=None) -> str:
    if schedule_minutes <= 0:
        return "manual"
    if last_run_at is None:
        return "—"
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    due = last_run_at + timedelta(minutes=schedule_minutes)
    if due <= now:
        return "due now"
    mins = int((due - now).total_seconds() // 60)
    return f"in {mins}m"
