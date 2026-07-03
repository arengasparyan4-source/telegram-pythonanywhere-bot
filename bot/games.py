"""Per-user game state for /game (Feature 4).

Two game kinds share one state shape, stored as JSON under ``game:{user_id}``::

    {
      "kind": "tf" | "word",
      "rounds": [ ... ],   # tf: {"s","ok","why"}; word: {"word","hint"}
      "idx": int,          # round currently being played
      "score": int         # correct answers so far
    }

Like the quiz, games need the store to track progress across callbacks /
messages, and degrade gracefully: with no store (stateless mode) or on any
error, save returns False and get returns None, and the handler tells the
student the game needs memory enabled.
"""

import json

from bot.clients import store
from bot.config import GAME_TTL


def _key(user_id: int) -> str:
    return f"game:{user_id}"


def save_game(user_id: int, kind: str, rounds: list) -> bool:
    """Start a fresh game of ``kind`` from ``rounds``. Returns True on success."""
    if store is None:
        return False
    state = {"kind": kind, "rounds": rounds, "idx": 0, "score": 0}
    try:
        store.set(_key(user_id), json.dumps(state), ex=GAME_TTL)
        return True
    except Exception as e:
        print(f"Store write error (game): {e}")
        return False


def get_game(user_id: int) -> dict | None:
    """Return the active game state, or None if no game is running."""
    if store is None:
        return None
    try:
        data = store.get(_key(user_id))
        return json.loads(data) if data else None
    except Exception as e:
        print(f"Store read error (game): {e}")
        return None


def update_game(user_id: int, state: dict) -> bool:
    """Persist an advanced game state (after a round)."""
    if store is None:
        return False
    try:
        store.set(_key(user_id), json.dumps(state), ex=GAME_TTL)
        return True
    except Exception as e:
        print(f"Store write error (game): {e}")
        return False


def clear_game(user_id: int) -> None:
    """Drop the game once it's finished (or to abandon it)."""
    if store is None:
        return
    try:
        store.delete(_key(user_id))
    except Exception as e:
        print(f"Store delete error (game): {e}")
