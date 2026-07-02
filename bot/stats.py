"""Per-user progress counters for the /stats command.

Four lifetime counters per user, stored via the shared KV store's atomic
incr(), mirroring rate_limit.py's use of the store:

    stat:topics:{uid}       new topics studied
    stat:conspectus:{uid}   conspectuses generated (new + "more detail")
    stat:quiz:{uid}         quizzes completed
    stat:cards:{uid}        flashcard sessions run

Degrades gracefully: with no store (stateless mode) or on any store error,
increments are no-ops and get_stats returns zeros, so the bot still works.
"""

from bot.clients import store

# Public field name -> store key template. The field names are what the
# handlers and /stats display use; the key templates keep the on-disk
# names short and stable.
_KEYS = {
    "topics": "stat:topics:{}",
    "conspectuses": "stat:conspectus:{}",
    "quizzes": "stat:quiz:{}",
    "flashcards": "stat:cards:{}",
}


def _incr(field: str, user_id: int) -> None:
    if store is None:
        return
    try:
        store.incr(_KEYS[field].format(user_id))
    except Exception as e:
        print(f"Store incr error (stat {field}): {e}")


def incr_topics(user_id: int) -> None:
    """Count a new topic studied."""
    _incr("topics", user_id)


def incr_conspectuses(user_id: int) -> None:
    """Count a conspectus generated (new topic or a 'more detail' expansion)."""
    _incr("conspectuses", user_id)


def incr_quizzes(user_id: int) -> None:
    """Count a completed quiz."""
    _incr("quizzes", user_id)


def incr_flashcards(user_id: int) -> None:
    """Count a flashcard session."""
    _incr("flashcards", user_id)


def get_stats(user_id: int) -> dict:
    """Return the user's counters as a dict; zeros when unset/unavailable."""
    out = {field: 0 for field in _KEYS}
    if store is None:
        return out
    for field, template in _KEYS.items():
        try:
            value = store.get(template.format(user_id))
            out[field] = int(value) if value else 0
        except Exception as e:
            print(f"Store read error (stat {field}): {e}")
    return out
