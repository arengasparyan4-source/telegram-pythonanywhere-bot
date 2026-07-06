"""APScheduler wiring for daily /remind delivery.

Kept separate from bot/reminders.py so the reminder logic has no hard
dependency on APScheduler and stays trivially unit-testable. This module
is imported only by the entrypoints (pythonanywhere_wsgi.py, run_local.py)
via start_scheduler(); the test suite never imports it, so APScheduler is
not needed to run the tests.

PythonAnywhere free-tier caveat: a web worker only runs while it's serving
requests and is recycled when idle, so this in-process scheduler is
BEST-EFFORT. For guaranteed delivery, trigger reminders.run_due_reminders()
from an external cron instead — the logic is deliberately reusable.
"""

from datetime import datetime

_scheduler = None


def _tick() -> None:
    """Fire reminders, daily challenges, and (once a day) inactivity nudges due
    this minute. Never raises."""
    from bot.challenges import run_due_challenges
    from bot.config import INACTIVITY_CHECK_HHMM
    from bot.inactivity import run_inactivity_nudges
    from bot.reminders import run_due_reminders

    now = datetime.now()
    hhmm, today = now.strftime("%H:%M"), now.strftime("%Y-%m-%d")
    try:
        run_due_reminders(hhmm, today)
    except Exception as e:
        print(f"Reminder tick error: {e}")
    try:
        run_due_challenges(hhmm, today)
    except Exception as e:
        print(f"Challenge tick error: {e}")
    # Feature 9: scan for inactive students once a day (the per-user cooldown
    # is the real spam guard; the time gate just keeps the daily scan cheap).
    if hhmm == INACTIVITY_CHECK_HHMM:
        try:
            run_inactivity_nudges(int(now.timestamp()), today)
        except Exception as e:
            print(f"Inactivity tick error: {e}")


def start_scheduler() -> None:
    """Start the once-a-minute reminder scheduler (idempotent)."""
    global _scheduler
    if _scheduler is not None:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except Exception as e:
        print(f"APScheduler unavailable, daily reminders disabled: {e}")
        return
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(_tick, "cron", minute="*", id="reminders", replace_existing=True)
    sched.start()
    _scheduler = sched
    print("Reminder scheduler started (checks every minute).")
