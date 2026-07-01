"""Cache of each user's most recent conspectus (study notes).

The bot stores the last topic + conspectus text per user so that the
quiz (Feature 1), the "more detail" inline button (Feature 2), and PDF
export (Feature 4) can all act on what was just sent without re-asking
the AI or re-deriving the topic.

Like history/preferences, this degrades gracefully: when the store is
not configured (stateless mode) or a store call fails, save is a no-op
and get returns None — the caller then tells the student to send a
topic first.
"""

import json
from bot.clients import store
from bot.config import CONSPECTUS_TTL


def save_last_conspectus(user_id: int, topic: str, text: str) -> None:
    """Cache the latest conspectus (topic + generated text) for a user."""
    if store is None:
        return
    try:
        store.set(
            f"conspectus:{user_id}",
            json.dumps({"topic": topic, "text": text}),
            ex=CONSPECTUS_TTL,
        )
    except Exception as e:
        print(f"Store write error (conspectus): {e}")


def get_last_conspectus(user_id: int) -> dict | None:
    """Return {"topic": str, "text": str} or None if nothing is cached."""
    if store is None:
        return None
    try:
        data = store.get(f"conspectus:{user_id}")
        return json.loads(data) if data else None
    except Exception as e:
        print(f"Store read error (conspectus): {e}")
        return None
