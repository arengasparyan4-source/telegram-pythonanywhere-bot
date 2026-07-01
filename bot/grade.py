"""Per-user grade level (Feature 3).

Lets a student pick their school grade band so conspectus explanations
and quiz questions can be tuned in complexity and vocabulary. Stored
under ``grade:{user_id}`` via the shared KV store, mirroring
preferences.py.

Default is *no* grade restriction: when the student hasn't chosen one
(or the store is unavailable), ``get_grade`` returns None and the AI
layer adds no grade instruction, so the bot behaves exactly as before.
"""

from bot.clients import store

# School grade bands offered by /grade. Kept as plain strings so they
# can go straight into callback_data and into the AI prompt.
VALID_GRADES = ("1-4", "5-9", "10-12")

# Armenian labels for the picker / confirmations.
GRADE_LABELS = {
    "1-4": "կրտսեր դասարաններ",
    "5-9": "միջին դասարաններ",
    "10-12": "ավագ դասարաններ",
}


def get_grade(user_id: int) -> str | None:
    """Return the user's chosen grade band, or None if unset/unavailable."""
    if store is None:
        return None
    try:
        value = store.get(f"grade:{user_id}")
    except Exception as e:
        print(f"Store read error (grade): {e}")
        return None
    return value if value in VALID_GRADES else None


def set_grade(user_id: int, grade: str) -> bool:
    """Save the user's grade band. Returns True on success."""
    if grade not in VALID_GRADES:
        return False
    if store is None:
        return False
    try:
        store.set(f"grade:{user_id}", grade)
        return True
    except Exception as e:
        print(f"Store write error (grade): {e}")
        return False


def clear_grade(user_id: int) -> None:
    """Remove any grade restriction (back to the default general style)."""
    if store is None:
        return
    try:
        store.delete(f"grade:{user_id}")
    except Exception as e:
        print(f"Store delete error (grade): {e}")
