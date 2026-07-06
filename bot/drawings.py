"""Participation tracking for 'draw the topic' (Feature 12).

By default the bot doesn't analyze a child's drawing (that would need a vision
model); it warmly encourages every drawing they send and records that they took
part, under a per-user counter stat:drawings:{uid}.

Degrades gracefully: with no store (stateless mode) or on any store error,
record_drawing is a no-op returning 0 and get_drawing_count returns 0.
"""

from bot.clients import store


def record_drawing(user_id: int) -> int:
    """Count one drawing the child shared; return the new total (0 if no store)."""
    if store is None:
        return 0
    try:
        return store.incr(f"stat:drawings:{user_id}")
    except Exception as e:
        print(f"Store incr error (drawings): {e}")
        return 0


def get_drawing_count(user_id: int) -> int:
    """Return how many drawings the child has shared (0 if none/unavailable)."""
    if store is None:
        return 0
    try:
        value = store.get(f"stat:drawings:{user_id}")
        return int(value) if value else 0
    except Exception as e:
        print(f"Store read error (drawings): {e}")
        return 0
