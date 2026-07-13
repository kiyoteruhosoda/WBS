from datetime import date


def progress_percent(status: str, actual_hours: float, remaining_hours: float | None) -> float:
    if status == "DONE":
        return 100.0
    remaining = remaining_hours or 0.0
    if actual_hours == 0 and remaining == 0:
        return 0.0
    return round(actual_hours * 100 / (actual_hours + remaining), 1)


def overdue_days(due_date: str | None, status: str, today: date) -> int:
    if due_date is None or status in {"DONE", "CANCELLED"}:
        return 0
    due = date.fromisoformat(due_date)
    return max((today - due).days, 0)


def priority_score(priority: int, urgency: int, overdue: int) -> int:
    return priority * 100 + urgency * 80 + min(overdue, 7) * 100


def today_bucket(
    status: str, start_date: str | None, due_date: str | None, today: date
) -> str | None:
    tomorrow = today.toordinal() + 1
    if due_date:
        due = date.fromisoformat(due_date)
        if due < today:
            return "OVERDUE"
        if due == today:
            return "TODAY"
        if due.toordinal() == tomorrow:
            return "TOMORROW"
    if status == "DOING":
        return "DOING"
    if start_date and date.fromisoformat(start_date) <= today and status == "TODO":
        return "STARTED"
    return None
