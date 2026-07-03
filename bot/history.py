import json
from bot.clients import store
from bot.config import MAX_HISTORY, HISTORY_TTL

# ── Interface language (Feature 7) ───────────────────────────────────────────
# A FIXED per-user language for the bot's own strings (menus / commands /
# buttons), independent of the language the AI mirrors in its replies. Stored
# under lang:{user_id}. Default Armenian, matching the bot's default voice.
VALID_LANGUAGES = ("hy", "ru", "en")
DEFAULT_LANGUAGE = "hy"


def get_language(user_id: int) -> str:
    """Return the user's interface language code, defaulting to Armenian."""
    if store is None:
        return DEFAULT_LANGUAGE
    try:
        value = store.get(f"lang:{user_id}")
    except Exception as e:
        print(f"Store read error (language): {e}")
        return DEFAULT_LANGUAGE
    return value if value in VALID_LANGUAGES else DEFAULT_LANGUAGE


def set_language(user_id: int, lang: str) -> bool:
    """Save the user's interface language. Returns True on success."""
    if lang not in VALID_LANGUAGES:
        return False
    if store is None:
        return False
    try:
        store.set(f"lang:{user_id}", lang)
        return True
    except Exception as e:
        print(f"Store write error (language): {e}")
        return False


# ── Favorite topics (Feature 8) ──────────────────────────────────────────────
# A per-user list of saved topic strings under fav:{user_id}, newest last and
# capped so it can't grow without bound. Case-insensitive de-dup on add.
FAV_MAX = 20


def get_favorites(user_id: int) -> list:
    """Return the user's saved favorite topics (oldest first). [] if none."""
    if store is None:
        return []
    try:
        data = store.get(f"fav:{user_id}")
        return json.loads(data) if data else []
    except Exception as e:
        print(f"Store read error (favorites): {e}")
        return []


def add_favorite(user_id: int, topic: str) -> bool:
    """Save ``topic`` to favorites. Returns True if newly added, False if the
    topic was blank, already saved, or the store is unavailable."""
    topic = (topic or "").strip()
    if not topic or store is None:
        return False
    try:
        favs = get_favorites(user_id)
        if any(f.lower() == topic.lower() for f in favs):
            return False  # already a favorite
        favs.append(topic)
        store.set(f"fav:{user_id}", json.dumps(favs[-FAV_MAX:]))
        return True
    except Exception as e:
        print(f"Store write error (favorites): {e}")
        return False


def remove_favorite(user_id: int, topic: str) -> None:
    """Remove ``topic`` (case-insensitive) from the user's favorites."""
    if store is None:
        return
    try:
        favs = [f for f in get_favorites(user_id) if f.lower() != topic.lower()]
        store.set(f"fav:{user_id}", json.dumps(favs))
    except Exception as e:
        print(f"Store write error (favorites remove): {e}")


# ── Weak spots (Feature 9) ───────────────────────────────────────────────────
# Topics the student keeps getting wrong in quizzes, stored under
# weak:{user_id} as JSON {topic: strikes}. A wrong quiz answer adds a strike;
# a correct one removes a strike; at zero strikes the topic clears itself —
# so a topic leaves the list once it's been answered right as often as wrong.
WEAK_MAX = 30  # most topics tracked at once (highest-strike kept)


def get_weakspots(user_id: int) -> dict:
    """Return {topic: strikes} of the user's weak spots. {} if none."""
    if store is None:
        return {}
    try:
        data = store.get(f"weak:{user_id}")
        return json.loads(data) if data else {}
    except Exception as e:
        print(f"Store read error (weakspots): {e}")
        return {}


def record_weak_answer(user_id: int, topic: str, correct: bool) -> None:
    """Update weak-spot strikes for ``topic`` after a quiz answer.

    Wrong answer → +1 strike (topic becomes/stays weak). Correct answer →
    −1 strike, removing the topic when it reaches zero. No-op for a blank
    topic or when the store is unavailable.
    """
    topic = (topic or "").strip()
    if not topic or store is None:
        return
    try:
        weak = get_weakspots(user_id)
        if correct:
            if topic in weak:
                weak[topic] -= 1
                if weak[topic] <= 0:
                    del weak[topic]
                store.set(f"weak:{user_id}", json.dumps(weak))
        else:
            weak[topic] = min(weak.get(topic, 0) + 1, 99)
            if len(weak) > WEAK_MAX:
                weak = dict(
                    sorted(weak.items(), key=lambda kv: kv[1], reverse=True)[:WEAK_MAX]
                )
            store.set(f"weak:{user_id}", json.dumps(weak))
    except Exception as e:
        print(f"Store write error (weakspots): {e}")


def list_weakspots(user_id: int) -> list:
    """Return weak-spot topics, most-missed first."""
    weak = get_weakspots(user_id)
    return [t for t, _ in sorted(weak.items(), key=lambda kv: kv[1], reverse=True)]


def clear_weakspot(user_id: int, topic: str) -> None:
    """Remove ``topic`` from the user's weak spots entirely."""
    if store is None:
        return
    try:
        weak = get_weakspots(user_id)
        if weak.pop(topic, None) is not None:
            store.set(f"weak:{user_id}", json.dumps(weak))
    except Exception as e:
        print(f"Store write error (weakspots clear): {e}")


def get_history(user_id: int) -> list:
    if store is None:
        return []
    try:
        data = store.get(f"chat:{user_id}")
        return json.loads(data) if data else []
    except Exception as e:
        print(f"Store read error (history): {e}")
        return []


def save_history(user_id: int, history: list) -> None:
    if store is None:
        return
    try:
        store.set(
            f"chat:{user_id}",
            json.dumps(history[-MAX_HISTORY:]),
            ex=HISTORY_TTL,
        )
    except Exception as e:
        print(f"Store write error (history): {e}")


def clear_history(user_id: int) -> None:
    if store is None:
        return
    try:
        store.delete(f"chat:{user_id}")
    except Exception as e:
        print(f"Store delete error (history): {e}")
