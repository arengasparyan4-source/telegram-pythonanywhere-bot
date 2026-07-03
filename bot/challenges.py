"""Daily "challenge of the day" delivery (Feature 5).

Reuses the same scheduler pattern as bot/reminders.py. A user opts in with
/challenge HH:MM; once a day at that time the bot generates and sends a fresh
educational challenge (unlike /remind, which resends the last conspectus).

State in the shared KV store, mirroring reminders.py:

    challenge:{uid}        the user's daily time as "HH:MM" (server time)
    challenge:index        JSON {uid_str: "HH:MM"} of everyone opted in
    challenge:sent:{uid}   ISO date of the last day we fired, to de-dup

Times are server-local (UTC on PythonAnywhere), same caveat as reminders.
Degrades gracefully: with no store every function is a safe no-op. Delivery
is driven by bot/scheduler.py's once-a-minute tick calling run_due_challenges.
"""

import json

from bot.ai import generate_challenge
from bot.clients import bot, store

_INDEX_KEY = "challenge:index"

# Header prepended to a daily challenge (shared by /challenge and the scheduler).
CHALLENGE_HEADER = "🏅 Օրվա մարտահրավեր՝"


def _load_index() -> dict:
    if store is None:
        return {}
    try:
        data = store.get(_INDEX_KEY)
        return json.loads(data) if data else {}
    except Exception as e:
        print(f"Store read error (challenge index): {e}")
        return {}


def _save_index(index: dict) -> None:
    try:
        store.set(_INDEX_KEY, json.dumps(index))
    except Exception as e:
        print(f"Store write error (challenge index): {e}")


def get_challenge_time(user_id: int) -> str | None:
    """Return the user's daily challenge time "HH:MM", or None if unset."""
    if store is None:
        return None
    try:
        return store.get(f"challenge:{user_id}") or None
    except Exception as e:
        print(f"Store read error (challenge): {e}")
        return None


def set_challenge_time(user_id: int, hhmm: str) -> bool:
    """Save the user's daily challenge time. Returns True on success."""
    if store is None:
        return False
    try:
        store.set(f"challenge:{user_id}", hhmm)
        index = _load_index()
        index[str(user_id)] = hhmm
        _save_index(index)
        return True
    except Exception as e:
        print(f"Store write error (challenge): {e}")
        return False


def clear_challenge_time(user_id: int) -> None:
    """Turn off the user's daily challenge."""
    if store is None:
        return
    try:
        store.delete(f"challenge:{user_id}")
        index = _load_index()
        if index.pop(str(user_id), None) is not None:
            _save_index(index)
    except Exception as e:
        print(f"Store delete error (challenge): {e}")


def run_due_challenges(now_hhmm: str, today_iso: str) -> int:
    """Send a fresh challenge to every user whose daily time is due now.

    De-duped per day like reminders. Returns the number sent. Never raises —
    a bad single user is logged and skipped.
    """
    if store is None:
        return 0
    sent = 0
    for uid_str, hhmm in _load_index().items():
        if hhmm != now_hhmm:
            continue
        try:
            if store.get(f"challenge:sent:{uid_str}") == today_iso:
                continue  # already sent today
            text = generate_challenge(int(uid_str))
            if not (text and text.strip()):
                continue
            bot.send_message(
                int(uid_str),
                f"{CHALLENGE_HEADER}\n\n{text}",
                parse_mode="HTML",
            )
            store.set(f"challenge:sent:{uid_str}", today_iso)
            sent += 1
        except Exception as e:
            print(f"Challenge send error for {uid_str}: {e}")
    return sent
