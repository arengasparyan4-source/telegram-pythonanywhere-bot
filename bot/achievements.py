"""Per-user achievement badges.

Badges are derived from the /stats counters (bot/stats.py) plus the day
streak (bot/activity.py) and are awarded once, then remembered as a set of
badge ids under ``badges:{uid}``. check_and_award() is called after each
study action; it returns any NEWLY earned badges so the handler can send a
congratulation. Degrades gracefully: with no store nothing is awarded.
"""

import json

from bot.activity import get_streak
from bot.clients import store
from bot.stats import get_stats

# Ordered catalog: (id, Armenian display, predicate(stats_dict, streak_int)).
# Order controls both award-check order and /achievements listing order.
BADGES = [
    ("first_conspectus", "🥇 Առաջին կոնսպեկտ", lambda s, streak: s["conspectuses"] >= 1),
    ("five_topics", "📚 5 թեմա", lambda s, streak: s["topics"] >= 5),
    ("quiz_maestro", "🧠 Quiz մաեստրո", lambda s, streak: s["quizzes"] >= 5),
    ("active_student", "⚡ Ակտիվ ուսանող", lambda s, streak: streak >= 3),
]


def _load_earned(user_id: int) -> set:
    if store is None:
        return set()
    try:
        data = store.get(f"badges:{user_id}")
        return set(json.loads(data)) if data else set()
    except Exception as e:
        print(f"Store read error (badges): {e}")
        return set()


def _save_earned(user_id: int, earned: set) -> None:
    try:
        store.set(f"badges:{user_id}", json.dumps(sorted(earned)))
    except Exception as e:
        print(f"Store write error (badges): {e}")


def check_and_award(user_id: int) -> list:
    """Award any newly-satisfied badges; return their display names (new only)."""
    if store is None:
        return []
    stats = get_stats(user_id)
    streak = get_streak(user_id)
    earned = _load_earned(user_id)
    newly = []
    for badge_id, display, predicate in BADGES:
        if badge_id not in earned and predicate(stats, streak):
            earned.add(badge_id)
            newly.append(display)
    if newly:
        _save_earned(user_id, earned)
    return newly


def get_badges(user_id: int) -> list:
    """Return the user's earned badge display names, in catalog order."""
    earned = _load_earned(user_id)
    return [display for badge_id, display, _ in BADGES if badge_id in earned]
