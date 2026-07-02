"""Parent mode: a weekly activity report for a linked child.

A parent runs /parent <child_id>; we remember the link and assemble a
report from the child's existing per-user data:

    stats     -> bot/stats.py     (topics, conspectuses, quizzes, flashcards)
    days      -> bot/activity.py  (distinct active days in the last 7)
    badges    -> bot/achievements.py

The parent -> children link is stored under ``parent:{parent_id}`` as a
JSON list of child ids. The counters are lifetime totals; only "days
active" is windowed to the last 7 days. Degrades gracefully: with no store
linking is a no-op and the report still renders (all zeros).
"""

import json

from bot.achievements import get_badges
from bot.activity import days_active_last_n
from bot.clients import store
from bot.stats import get_stats


def link_child(parent_id: int, child_id: int) -> bool:
    """Remember that `parent_id` follows `child_id`. Returns True on success."""
    if store is None:
        return False
    try:
        data = store.get(f"parent:{parent_id}")
        children = set(json.loads(data)) if data else set()
        children.add(int(child_id))
        store.set(f"parent:{parent_id}", json.dumps(sorted(children)))
        return True
    except Exception as e:
        print(f"Store write error (parent link): {e}")
        return False


def get_children(parent_id: int) -> list:
    """Return the list of child ids this parent has linked."""
    if store is None:
        return []
    try:
        data = store.get(f"parent:{parent_id}")
        return list(json.loads(data)) if data else []
    except Exception as e:
        print(f"Store read error (parent): {e}")
        return []


def build_report(child_id: int) -> str:
    """Assemble the Armenian weekly activity report for a child."""
    s = get_stats(child_id)
    days = days_active_last_n(child_id, 7)
    badges = get_badges(child_id)
    lines = [
        f"👨‍👩‍👧 Շաբաթվա հաշվետվություն (ID: {child_id})",
        "",
        f"📚 Ուսումնասիրած թեմաներ — {s['topics']}",
        f"📝 Կոնսպեկտներ — {s['conspectuses']}",
        f"✅ Անցած վիկտորինաներ — {s['quizzes']}",
        f"🧠 Flashcard սեսիաներ — {s['flashcards']}",
        f"📅 Ակտիվ օրեր (վերջին 7 օր) — {days}",
        "",
    ]
    if badges:
        lines.append("🏅 Նշաններ՝")
        lines.extend(f"• {b}" for b in badges)
    else:
        lines.append("🏅 Նշաններ՝ դեռ չկան")
    return "\n".join(lines)
