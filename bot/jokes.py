"""Per-user "jokes disabled" flag for the /joke command.

Lets a student turn jokes off with /stopjoke and back on by sending
/joke again (toggle). Stored under ``jokes_disabled:{user_id}`` via the
shared KV store, mirroring preferences.py and grade.py.

Default is enabled: when the flag is unset (or the store is
unavailable), jokes work normally, so the bot behaves as before.
"""

from bot.clients import store


def jokes_disabled(user_id: int) -> bool:
    """Return True if the user has turned jokes off via /stopjoke."""
    if store is None:
        return False
    try:
        return store.get(f"jokes_disabled:{user_id}") == "1"
    except Exception as e:
        print(f"Store read error (jokes): {e}")
        return False


def set_jokes_disabled(user_id: int, disabled: bool) -> bool:
    """Turn jokes off (disabled=True) or back on. Returns True on success."""
    if store is None:
        return False
    try:
        if disabled:
            store.set(f"jokes_disabled:{user_id}", "1")
        else:
            store.delete(f"jokes_disabled:{user_id}")
        return True
    except Exception as e:
        print(f"Store write error (jokes): {e}")
        return False
