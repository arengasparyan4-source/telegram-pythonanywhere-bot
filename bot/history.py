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


# ── Group class mode (Feature 4) ─────────────────────────────────────────────
# A class question + collected answers, keyed by the GROUP chat_id (not a
# user_id), under class:{chat_id}. The teacher posts a question with
# /askclass; students' replies are collected (one answer per student, latest
# wins). Expires after a day so an abandoned question clears itself.
_CLASS_TTL = 86400  # an active class question lives for 1 day (seconds)
_CLASS_MAX_ANSWERS = 200


def set_group_question(chat_id: int, question: str, asker_id: int) -> bool:
    """Start a new class question in a group, clearing any previous answers."""
    if store is None:
        return False
    try:
        store.set(
            f"class:{chat_id}",
            json.dumps({"question": question, "asker": asker_id, "answers": []}),
            ex=_CLASS_TTL,
        )
        return True
    except Exception as e:
        print(f"Store write error (class question): {e}")
        return False


def get_group_question(chat_id: int) -> dict | None:
    """Return the group's active class question dict, or None."""
    if store is None:
        return None
    try:
        data = store.get(f"class:{chat_id}")
        return json.loads(data) if data else None
    except Exception as e:
        print(f"Store read error (class question): {e}")
        return None


def add_class_answer(chat_id: int, user_id: int, name: str, text: str) -> bool:
    """Record a student's answer to the active class question (one per student).

    Returns True if stored, False if there's no active question. A repeat
    answer from the same student replaces their earlier one.
    """
    data = get_group_question(chat_id)
    if not data or store is None:
        return False
    try:
        answers = [a for a in data.get("answers", []) if a.get("uid") != user_id]
        answers.append({"uid": user_id, "name": name, "text": text})
        data["answers"] = answers[-_CLASS_MAX_ANSWERS:]
        store.set(f"class:{chat_id}", json.dumps(data), ex=_CLASS_TTL)
        return True
    except Exception as e:
        print(f"Store write error (class answer): {e}")
        return False


def clear_group_question(chat_id: int) -> None:
    """End the active class question in a group."""
    if store is None:
        return
    try:
        store.delete(f"class:{chat_id}")
    except Exception as e:
        print(f"Store delete error (class question): {e}")


# ── Leaderboard (Feature 5) ──────────────────────────────────────────────────
# Per-chat scoreboard under score:{chat_id} as JSON {uid: {"name", "points"}}.
# Scoped by chat_id so a class group has its own board (and a private chat has
# a personal one). Points come from correct quiz/game answers and duel wins.
def _load_scores(chat_id: int) -> dict:
    if store is None:
        return {}
    try:
        data = store.get(f"score:{chat_id}")
        return json.loads(data) if data else {}
    except Exception as e:
        print(f"Store read error (scores): {e}")
        return {}


def add_score(chat_id: int, user_id: int, name: str, points: int = 1) -> None:
    """Add ``points`` to a user's score within a chat's leaderboard."""
    if store is None or points <= 0:
        return
    try:
        board = _load_scores(chat_id)
        entry = board.get(str(user_id)) or {"name": name, "points": 0}
        entry["points"] = int(entry.get("points", 0)) + points
        if name:
            entry["name"] = name
        board[str(user_id)] = entry
        store.set(f"score:{chat_id}", json.dumps(board))
    except Exception as e:
        print(f"Store write error (add_score): {e}")


def get_leaderboard(chat_id: int) -> list:
    """Return [(name, points), ...] for a chat, ranked highest first."""
    board = _load_scores(chat_id)
    ranked = [
        (v.get("name") or f"user{uid}", int(v.get("points", 0)))
        for uid, v in board.items()
    ]
    ranked.sort(key=lambda t: t[1], reverse=True)
    return ranked


# ── Duel (Feature 6) ─────────────────────────────────────────────────────────
# A 2-player quiz duel, one active per chat, keyed by the chat_id under
# duel:{chat_id}. The handler layer owns the game logic (rounds, scoring,
# timing); this module just persists the state blob with a TTL so an
# abandoned duel (a player who drops out / never joins) clears itself.
_DUEL_TTL = 3600  # an in-progress duel expires after 1 hour (seconds)


def save_duel(chat_id: int, state: dict) -> bool:
    """Persist a duel's state for a chat. Returns True on success."""
    if store is None:
        return False
    try:
        store.set(f"duel:{chat_id}", json.dumps(state), ex=_DUEL_TTL)
        return True
    except Exception as e:
        print(f"Store write error (duel): {e}")
        return False


def get_duel(chat_id: int) -> dict | None:
    """Return the chat's active duel state, or None."""
    if store is None:
        return None
    try:
        data = store.get(f"duel:{chat_id}")
        return json.loads(data) if data else None
    except Exception as e:
        print(f"Store read error (duel): {e}")
        return None


def clear_duel(chat_id: int) -> None:
    """End the chat's duel."""
    if store is None:
        return
    try:
        store.delete(f"duel:{chat_id}")
    except Exception as e:
        print(f"Store delete error (duel): {e}")


# ── Spaced repetition (Feature 7) ────────────────────────────────────────────
# Per-user review schedule under review:{user_id} as JSON
# {topic: {"studied": epoch, "stage": int}}. A topic becomes "due" after 1,
# then 3, then 7 days; each review advances the stage. Studying a topic afresh
# resets it to stage 0.
_REVIEW_INTERVALS_DAYS = (1, 3, 7)
_REVIEW_MAX = 50


def _load_reviews(user_id: int) -> dict:
    if store is None:
        return {}
    try:
        data = store.get(f"review:{user_id}")
        return json.loads(data) if data else {}
    except Exception as e:
        print(f"Store read error (reviews): {e}")
        return {}


def record_study(user_id: int, topic: str, now: int | None = None) -> None:
    """Record that a topic was studied now, (re)starting its review schedule."""
    topic = (topic or "").strip()
    if not topic or store is None:
        return
    ts = int(now if now is not None else time.time())
    try:
        data = _load_reviews(user_id)
        data[topic] = {"studied": ts, "stage": 0}
        if len(data) > _REVIEW_MAX:
            data = dict(
                sorted(data.items(), key=lambda kv: kv[1]["studied"], reverse=True)[
                    :_REVIEW_MAX
                ]
            )
        store.set(f"review:{user_id}", json.dumps(data))
    except Exception as e:
        print(f"Store write error (record_study): {e}")


def get_due_reviews(user_id: int, now: int | None = None) -> list:
    """Return topics whose spaced-repetition review is due now (most overdue
    first)."""
    now = int(now if now is not None else time.time())
    due = []
    for topic, info in _load_reviews(user_id).items():
        stage = info.get("stage", 0)
        if stage >= len(_REVIEW_INTERVALS_DAYS):
            continue  # fully reviewed — graduated
        due_at = info.get("studied", 0) + _REVIEW_INTERVALS_DAYS[stage] * 86400
        if now >= due_at:
            due.append((topic, due_at))
    due.sort(key=lambda t: t[1])
    return [topic for topic, _ in due]


def mark_reviewed(user_id: int, topic: str, now: int | None = None) -> None:
    """Advance a topic to its next review stage after a successful review."""
    if store is None:
        return
    ts = int(now if now is not None else time.time())
    try:
        data = _load_reviews(user_id)
        if topic in data:
            data[topic]["stage"] = data[topic].get("stage", 0) + 1
            data[topic]["studied"] = ts
            store.set(f"review:{user_id}", json.dumps(data))
    except Exception as e:
        print(f"Store write error (mark_reviewed): {e}")


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
