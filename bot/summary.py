"""Auto-summary offer counter (Feature 8).

Counts a user's processed messages within a study session and signals when
it's time to offer a "📌 Ամփոփում" recap — every SUMMARY_EVERY messages. The
counter key carries a sliding TTL (refreshed on every message) so a gap of
SUMMARY_SESSION_TTL seconds of inactivity starts a fresh session: the key
expires and the next message re-creates it at 1.

The recap text itself is produced by bot/ai.py::generate_summary from the
user's recent conversation history. This module only decides WHEN to offer it.

Degrades gracefully: with no store (stateless mode) or on any store error,
note_message is a no-op that returns False, so a recap is simply never offered.
"""

from bot.clients import store
from bot.config import SUMMARY_EVERY, SUMMARY_SESSION_TTL


def note_message(user_id: int) -> bool:
    """Count one processed message; return True when a recap should be offered.

    Returns True on every SUMMARY_EVERY-th message of a session (18th, 36th,
    …). Refreshes the session TTL on every call so the count only resets after
    a real gap of inactivity. Never raises.
    """
    if store is None:
        return False
    try:
        key = f"summary:count:{user_id}"
        count = store.incr(key)
        # Sliding window: keep the session alive while the student is active;
        # once they go quiet for SUMMARY_SESSION_TTL the key expires and the
        # next message starts a new session at 1.
        store.expire(key, SUMMARY_SESSION_TTL)
        return count % SUMMARY_EVERY == 0
    except Exception as e:
        print(f"Store error (summary counter): {e}")
        return False
