"""Smart inactivity reminders (Feature 9).

When a student hasn't interacted for INACTIVITY_DAYS or more, the bot sends a
single gentle nudge suggesting they review a specific past topic — a due
spaced-repetition topic if any (Feature 7), else their last conspectus, else a
saved favorite. If there's nothing to suggest, the student isn't nudged.

Reuses the scheduler pattern of bot/reminders.py, driven by bot/scheduler.py's
once-a-minute tick — but the scheduler only calls run_inactivity_nudges once a
day (at INACTIVITY_CHECK_HHMM), so the scan is cheap. A per-user cooldown key
(nudge:{uid}, TTL INACTIVITY_COOLDOWN) means an inactive student is nudged at
most once per cooldown window, never every day.

'Last seen' is the seen:{uid} epoch written by history.touch_user on every
interaction. Degrades gracefully: with no store every function is a safe no-op.
"""

import html

from bot.clients import bot, store
from bot.config import INACTIVITY_COOLDOWN, INACTIVITY_DAYS
from bot.conspectus import get_last_conspectus
from bot.history import get_all_user_ids, get_due_reviews, get_favorites, get_last_seen


def _suggested_topic(user_id: int) -> str | None:
    """Pick a past topic to suggest for review, or None if there's nothing.

    Priority: a topic whose spaced-repetition review is due → the last
    conspectus → the most recent favorite.
    """
    due = get_due_reviews(user_id)
    if due:
        return due[0]
    consp = get_last_conspectus(user_id)
    if consp and consp.get("topic"):
        return consp["topic"]
    favs = get_favorites(user_id)
    return favs[-1] if favs else None


def run_inactivity_nudges(now: int, today_iso: str) -> int:
    """Nudge every user inactive for >= INACTIVITY_DAYS to review a past topic.

    ``now`` is the current epoch seconds; ``today_iso`` stamps the cooldown
    marker. Users seen recently, still within a cooldown, or with no topic to
    suggest are skipped. Returns the number of nudges sent. Never raises — a
    bad single user is logged and skipped.
    """
    if store is None:
        return 0
    cutoff = now - INACTIVITY_DAYS * 86400
    sent = 0
    for uid_str in get_all_user_ids():
        try:
            uid = int(uid_str)
            last_seen = get_last_seen(uid)
            if last_seen is None or last_seen > cutoff:
                continue  # active recently (or never really seen) — no nudge
            if store.get(f"nudge:{uid}"):
                continue  # still within the cooldown from a recent nudge
            topic = _suggested_topic(uid)
            if not topic:
                continue  # nothing to suggest — stay quiet
            bot.send_message(
                uid,
                "🔔 Բարև 🙂 Վաղուց չենք սովորել։ Ի՞նչ կասես՝ միասին կրկնենք "
                f"«<b>{html.escape(str(topic))}</b>» թեման։ Գրիր /review կամ "
                "ուղարկիր թեման, և կշարունակենք 📚",
                parse_mode="HTML",
            )
            store.set(f"nudge:{uid}", today_iso, ex=INACTIVITY_COOLDOWN)
            sent += 1
        except Exception as e:
            print(f"Inactivity nudge error for {uid_str}: {e}")
    return sent
