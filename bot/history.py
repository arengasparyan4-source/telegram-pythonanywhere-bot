import json
import time
from bot.clients import store
from bot.config import ADMIN_SESSION_TTL, MAX_HISTORY, HISTORY_TTL

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


# ── User tracking + admin stats (/admin) ─────────────────────────────────────
# Aggregate, bot-wide usage tracked for the admin dashboard:
#   seen:{uid}       last-active epoch seconds for a user (O(1) write/msg)
#   known:{uid}      one-time marker so a user is added to the index once
#   users:index      JSON list of every user_id string ever seen
#   stat:messages:total   global counter of messages processed
# Per-message writes stay O(1) (a seen: set + a set_nx probe); the index is
# only appended to when a brand-new user appears. Aggregation (get_admin_stats)
# is O(users) and runs only when an admin views the dashboard.
_USERS_INDEX_KEY = "users:index"
_MESSAGES_KEY = "stat:messages:total"


def _load_users_index() -> list:
    if store is None:
        return []
    try:
        data = store.get(_USERS_INDEX_KEY)
        return json.loads(data) if data else []
    except Exception as e:
        print(f"Store read error (users index): {e}")
        return []


def touch_user(user_id: int, now: int | None = None) -> None:
    """Record that ``user_id`` just interacted, updating last-seen time.

    Adds the user to the global index the first time they're seen. No-op
    without a store. Never raises — tracking must not break a reply.
    """
    if store is None:
        return
    ts = int(now if now is not None else time.time())
    try:
        store.set(f"seen:{user_id}", str(ts))
        # set_nx wins only the first time we ever see this user — append then.
        if store.set_nx(f"known:{user_id}", "1"):
            index = _load_users_index()
            if str(user_id) not in index:
                index.append(str(user_id))
                store.set(_USERS_INDEX_KEY, json.dumps(index))
    except Exception as e:
        print(f"Store write error (touch_user): {e}")


def incr_messages() -> None:
    """Count one processed message toward the bot-wide total."""
    if store is None:
        return
    try:
        store.incr(_MESSAGES_KEY)
    except Exception as e:
        print(f"Store incr error (messages): {e}")


def get_message_count() -> int:
    """Total messages processed bot-wide (0 if untracked/unavailable)."""
    if store is None:
        return 0
    try:
        return int(store.get(_MESSAGES_KEY) or 0)
    except Exception as e:
        print(f"Store read error (messages): {e}")
        return 0


def get_admin_stats(now: int | None = None) -> dict:
    """Aggregate bot-wide usage for the /admin dashboard.

    Returns total_users, active_today (seen in the last 24h), active_week
    (last 7 days), total_messages, and total_conspectuses (summed from the
    per-user counters in bot/stats.py). Safe/zeroed when the store is off.
    """
    now = int(now if now is not None else time.time())
    uids = _load_users_index()
    day_ago, week_ago = now - 86400, now - 7 * 86400
    active_today = active_week = 0
    total_conspectuses = 0
    from bot.stats import get_stats  # lazy: avoid import cycle at module load

    for uid in uids:
        try:
            seen = store.get(f"seen:{uid}") if store is not None else None
            if seen is not None:
                ts = int(seen)
                if ts >= day_ago:
                    active_today += 1
                if ts >= week_ago:
                    active_week += 1
            total_conspectuses += get_stats(int(uid)).get("conspectuses", 0)
        except Exception as e:
            print(f"Admin stats error for {uid}: {e}")
    return {
        "total_users": len(uids),
        "active_today": active_today,
        "active_week": active_week,
        "total_messages": get_message_count(),
        "total_conspectuses": total_conspectuses,
    }


# ── Admin session (remembers a successful /admin login) ──────────────────────
def start_admin_session(user_id: int) -> None:
    """Mark the user as an authenticated admin for ADMIN_SESSION_TTL seconds."""
    if store is None:
        return
    try:
        store.set(f"admin:{user_id}", "1", ex=ADMIN_SESSION_TTL)
    except Exception as e:
        print(f"Store write error (admin session): {e}")


def is_admin(user_id: int) -> bool:
    """True if the user has a live (non-expired) admin session."""
    if store is None:
        return False
    try:
        return store.get(f"admin:{user_id}") == "1"
    except Exception as e:
        print(f"Store read error (admin session): {e}")
        return False


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
