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
    """Fire any reminders due at the current minute. Never raises."""
    from bot.reminders import run_due_reminders

    now = datetime.now()
    try:
        run_due_reminders(now.strftime("%H:%M"), now.strftime("%Y-%m-%d"))
    except Exception as e:
        print(f"Reminder tick error: {e}")


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
