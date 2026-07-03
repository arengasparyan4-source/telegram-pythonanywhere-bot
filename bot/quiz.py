"""Per-user quiz state for the post-conspectus quiz (Feature 1).

A quiz is a short list of multiple-choice questions generated from the
student's most recent conspectus. The whole quiz can't fit in Telegram's
64-byte callback_data, so the question list and progress are persisted in
the store and the inline buttons only carry the chosen option index.

State shape (JSON under ``quiz:{user_id}``)::

    {
      "questions": [
        {"q": str, "options": [str, ...], "correct": int, "explanation": str},
        ...
      ],
      "idx": int,    # index of the question currently being asked
      "score": int   # number answered correctly so far
    }

Quizzes require the store (we can't track progress across callbacks in
stateless mode). Every call degrades gracefully: when the store is
absent or a call fails, save returns False and get returns None, and the
handler tells the student the quiz needs memory enabled.
"""

import json
from bot.clients import store
from bot.config import QUIZ_TTL


def _key(user_id: int) -> str:
    return f"quiz:{user_id}"


def save_quiz(user_id: int, questions: list, topic: str = "") -> bool:
    """Start a fresh quiz from ``questions``. Returns True on success.

    ``topic`` is the conspectus topic the quiz is about; it's stored so wrong
    answers can be attributed to a weak spot (Feature 9).
    """
    if store is None:
        return False
    state = {"questions": questions, "idx": 0, "score": 0, "topic": topic}
    try:
        store.set(_key(user_id), json.dumps(state), ex=QUIZ_TTL)
        return True
    except Exception as e:
        print(f"Store write error (quiz): {e}")
        return False


def get_quiz(user_id: int) -> dict | None:
    """Return the active quiz state, or None if there's no quiz running."""
    if store is None:
        return None
    try:
        data = store.get(_key(user_id))
        return json.loads(data) if data else None
    except Exception as e:
        print(f"Store read error (quiz): {e}")
        return None


def update_quiz(user_id: int, state: dict) -> bool:
    """Persist an advanced quiz state (after grading an answer)."""
    if store is None:
        return False
    try:
        store.set(_key(user_id), json.dumps(state), ex=QUIZ_TTL)
        return True
    except Exception as e:
        print(f"Store write error (quiz): {e}")
        return False


def clear_quiz(user_id: int) -> None:
    """Drop the quiz once it's finished (or to abandon it)."""
    if store is None:
        return
    try:
        store.delete(_key(user_id))
    except Exception as e:
        print(f"Store delete error (quiz): {e}")
