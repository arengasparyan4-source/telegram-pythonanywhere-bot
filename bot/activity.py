"""Per-user daily activity tracking.

Feeds the "3 days in a row" achievement (streak) and the parent report
("days active"). One JSON record per user under ``activity:{uid}``::

    {"last": "YYYY-MM-DD", "streak": int, "days": ["YYYY-MM-DD", ...]}

`days` keeps the most recent active dates (capped) so a weekly count can be
computed without scanning. Dates are server-local (UTC on PythonAnywhere),
matching bot/reminders.py. Degrades gracefully: with no store, recording is
a no-op and the getters return 0.
"""

import json
from datetime import date, timedelta

from bot.clients import store

_MAX_DAYS = 30  # how many recent active dates to retain per user


def _today() -> str:
    return date.today().isoformat()


def _load(user_id: int) -> dict:
    if store is None:
        return {}
    try:
        data = store.get(f"activity:{user_id}")
        return json.loads(data) if data else {}
    except Exception as e:
        print(f"Store read error (activity): {e}")
        return {}


def record_activity(user_id: int, today: str | None = None) -> int:
    """Record that the user was active today; return the current day streak.

    The streak increments when today is exactly one day after the last
    active day, resets to 1 on a gap, and is unchanged if we already logged
    today. Never raises.
    """
    if store is None:
        return 0
    today = today or _today()
    rec = _load(user_id)
    last = rec.get("last")
    streak = int(rec.get("streak", 0))
    days = rec.get("days", [])

    if last == today:
        return streak  # already counted today

    if last:
        try:
            delta = (date.fromisoformat(today) - date.fromisoformat(last)).days
        except ValueError:
            delta = None
        streak = streak + 1 if delta == 1 else 1
    else:
        streak = 1

    if today not in days:
        days.append(today)
    days = sorted(days)[-_MAX_DAYS:]

    try:
        store.set(
            f"activity:{user_id}",
            json.dumps({"last": today, "streak": streak, "days": days}),
        )
    except Exception as e:
        print(f"Store write error (activity): {e}")
    return streak


def get_streak(user_id: int) -> int:
    """Return the user's current consecutive-day streak (0 if none)."""
    return int(_load(user_id).get("streak", 0))


def days_active_last_n(user_id: int, n: int = 7, today: str | None = None) -> int:
    """Count distinct active days within the last `n` days (inclusive)."""
    today = today or _today()
    try:
        end = date.fromisoformat(today)
    except ValueError:
        return 0
    start = end - timedelta(days=n - 1)
    count = 0
    for d in _load(user_id).get("days", []):
        try:
            if start <= date.fromisoformat(d) <= end:
                count += 1
        except ValueError:
            continue
    return count
