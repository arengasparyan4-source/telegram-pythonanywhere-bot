"""Transient per-user conversation mode (which multi-step flow we're in).

Most messages are treated as a new topic → conspectus. A few features first
ASK the student something and then interpret their NEXT text message
specially instead of as a fresh conspectus request:

    "plan"       — awaiting the list of subjects for /plan (Feature 3)
    "ask"        — free Q&A mode (/ask); every message is answered directly
                   until the student leaves (Feature 6)
    "game_word"  — awaiting the guessed word in a "guess the word" game
                   (Feature 4)

State is a small JSON blob under ``mode:{user_id}`` so a flow can stash a
little context alongside the mode name (e.g. the game id). A short TTL means
a forgotten mode auto-clears rather than trapping the student forever.

Degrades gracefully: with no store (stateless mode) or on any error,
get_mode returns None so the bot falls back to normal conspectus behavior.
"""

import json

from bot.clients import store
from bot.config import MODE_TTL


def _key(user_id: int) -> str:
    return f"mode:{user_id}"


def set_mode(user_id: int, mode: str, data: dict | None = None) -> bool:
    """Put the user into ``mode`` (optionally with extra ``data``).

    Returns True on success, False if the store is unavailable — callers
    that need the mode to work (multi-step flows) can warn the student.
    """
    if store is None:
        return False
    payload = {"mode": mode}
    if data:
        payload.update(data)
    try:
        store.set(_key(user_id), json.dumps(payload), ex=MODE_TTL)
        return True
    except Exception as e:
        print(f"Store write error (mode): {e}")
        return False


def get_mode(user_id: int) -> dict | None:
    """Return the active mode payload ({"mode": str, ...}) or None."""
    if store is None:
        return None
    try:
        data = store.get(_key(user_id))
        return json.loads(data) if data else None
    except Exception as e:
        print(f"Store read error (mode): {e}")
        return None


def clear_mode(user_id: int) -> None:
    """Leave whatever mode the user was in (back to normal behavior)."""
    if store is None:
        return
    try:
        store.delete(_key(user_id))
    except Exception as e:
        print(f"Store delete error (mode): {e}")
