"""Per-user daily "repeat the last conspectus" reminders.

The user sets a time with /remind HH:MM; once a day at that time the bot
resends their most recent conspectus. State lives in the shared KV store:

    remind:{uid}        the user's reminder time as "HH:MM" (server time)
    remind:index        JSON {uid_str: "HH:MM"} of everyone with a reminder
    remind:sent:{uid}   ISO date of the last day we fired, to de-dup

An index key is kept because the store is a plain KV with no "scan all
keys" operation — the scheduler needs to find due users without one.

Times are interpreted in the SERVER'S local time (UTC on PythonAnywhere).
Per-user timezones would need extra state; this keeps the teaching example
simple. Degrades gracefully: with no store every function is a safe no-op.

Delivery is driven by bot/scheduler.py (APScheduler). On PythonAnywhere's
free tier a worker is only alive while serving requests, so in-process
firing is best-effort; for guaranteed delivery, call run_due_reminders()
from an external cron hitting a small endpoint. The logic lives here so
either driver can reuse it.
"""

import json
import re

from bot.clients import bot, store
from bot.conspectus import get_last_conspectus

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_INDEX_KEY = "remind:index"

# Header prepended to a resent conspectus (shared by /repeat and reminders).
REPEAT_HEADER = "🔁 Կրկնենք երեկվա թեման:"


def normalize_time(raw: str) -> str | None:
    """Return a zero-padded "HH:MM" if `raw` is a valid 24h time, else None."""
    m = _TIME_RE.match((raw or "").strip())
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _load_index() -> dict:
    if store is None:
        return {}
    try:
        data = store.get(_INDEX_KEY)
        return json.loads(data) if data else {}
    except Exception as e:
        print(f"Store read error (remind index): {e}")
        return {}


def _save_index(index: dict) -> None:
    try:
        store.set(_INDEX_KEY, json.dumps(index))
    except Exception as e:
        print(f"Store write error (remind index): {e}")


def get_reminder(user_id: int) -> str | None:
    """Return the user's reminder time "HH:MM", or None if unset."""
    if store is None:
        return None
    try:
        return store.get(f"remind:{user_id}") or None
    except Exception as e:
        print(f"Store read error (remind): {e}")
        return None


def set_reminder(user_id: int, hhmm: str) -> bool:
    """Save the user's daily reminder time. Returns True on success."""
    if store is None:
        return False
    try:
        store.set(f"remind:{user_id}", hhmm)
        index = _load_index()
        index[str(user_id)] = hhmm
        _save_index(index)
        return True
    except Exception as e:
        print(f"Store write error (remind): {e}")
        return False


def clear_reminder(user_id: int) -> None:
    """Turn off the user's daily reminder."""
    if store is None:
        return
    try:
        store.delete(f"remind:{user_id}")
        index = _load_index()
        if index.pop(str(user_id), None) is not None:
            _save_index(index)
    except Exception as e:
        print(f"Store delete error (remind): {e}")


def run_due_reminders(now_hhmm: str, today_iso: str) -> int:
    """Send the last conspectus to every user whose reminder is due now.

    `now_hhmm` is the current "HH:MM"; `today_iso` is today's date string
    used to de-dup so a user is reminded at most once per day even if this
    runs several times within the minute. Returns the number of reminders
    actually sent. Never raises — a bad single user is logged and skipped.
    """
    if store is None:
        return 0
    sent = 0
    for uid_str, hhmm in _load_index().items():
        if hhmm != now_hhmm:
            continue
        try:
            if store.get(f"remind:sent:{uid_str}") == today_iso:
                continue  # already reminded today
            consp = get_last_conspectus(int(uid_str))
            if not consp:
                continue
            bot.send_message(
                int(uid_str),
                f"{REPEAT_HEADER}\n\n{consp['text']}",
                parse_mode="HTML",
            )
            store.set(f"remind:sent:{uid_str}", today_iso)
            sent += 1
        except Exception as e:
            print(f"Reminder send error for {uid_str}: {e}")
    return sent
