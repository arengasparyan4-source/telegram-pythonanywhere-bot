"""Smart inactivity reminder (Feature 9): the history helpers and
bot/inactivity.py's nudge scan."""

from unittest.mock import patch

from bot.config import INACTIVITY_COOLDOWN

DAY = 86400


# ── history helpers ───────────────────────────────────────────────────────────
def test_get_last_seen_returns_int():
    with patch("bot.history.store") as s:
        s.get.return_value = "1700000000"
        from bot.history import get_last_seen

        assert get_last_seen(1) == 1700000000


def test_get_last_seen_none_when_unset():
    with patch("bot.history.store") as s:
        s.get.return_value = None
        from bot.history import get_last_seen

        assert get_last_seen(1) is None


def test_get_last_seen_none_without_store():
    with patch("bot.history.store", None):
        from bot.history import get_last_seen

        assert get_last_seen(1) is None


# ── topic suggestion priority ─────────────────────────────────────────────────
def test_suggested_topic_prefers_due_review():
    with (
        patch("bot.inactivity.get_due_reviews", return_value=["A", "B"]),
        patch("bot.inactivity.get_last_conspectus", return_value={"topic": "C"}),
        patch("bot.inactivity.get_favorites", return_value=["D"]),
    ):
        from bot.inactivity import _suggested_topic

        assert _suggested_topic(1) == "A"


def test_suggested_topic_falls_back_to_last_conspectus():
    with (
        patch("bot.inactivity.get_due_reviews", return_value=[]),
        patch("bot.inactivity.get_last_conspectus", return_value={"topic": "C"}),
        patch("bot.inactivity.get_favorites", return_value=["D"]),
    ):
        from bot.inactivity import _suggested_topic

        assert _suggested_topic(1) == "C"


def test_suggested_topic_falls_back_to_favorite():
    with (
        patch("bot.inactivity.get_due_reviews", return_value=[]),
        patch("bot.inactivity.get_last_conspectus", return_value=None),
        patch("bot.inactivity.get_favorites", return_value=["D", "E"]),
    ):
        from bot.inactivity import _suggested_topic

        assert _suggested_topic(1) == "E"  # most recent favorite


def test_suggested_topic_none_when_nothing():
    with (
        patch("bot.inactivity.get_due_reviews", return_value=[]),
        patch("bot.inactivity.get_last_conspectus", return_value=None),
        patch("bot.inactivity.get_favorites", return_value=[]),
    ):
        from bot.inactivity import _suggested_topic

        assert _suggested_topic(1) is None


# ── run_inactivity_nudges ─────────────────────────────────────────────────────
def test_nudges_inactive_user_and_sets_cooldown():
    with (
        patch("bot.inactivity.store") as s,
        patch("bot.inactivity.get_all_user_ids", return_value=["100"]),
        patch("bot.inactivity.get_last_seen", return_value=1000),
        patch("bot.inactivity._suggested_topic", return_value="Ֆիզիկա"),
        patch("bot.inactivity.bot") as mock_bot,
    ):
        s.get.return_value = None  # not in cooldown
        from bot.inactivity import run_inactivity_nudges

        now = 1000 + 4 * DAY  # 4 days of silence → inactive (> 3)
        sent = run_inactivity_nudges(now, "2026-07-10")
        assert sent == 1
        assert "Ֆիզիկա" in mock_bot.send_message.call_args[0][1]
        assert s.set.call_args[0][0] == "nudge:100"
        assert s.set.call_args[1]["ex"] == INACTIVITY_COOLDOWN


def test_skips_recently_active_user():
    with (
        patch("bot.inactivity.store") as s,
        patch("bot.inactivity.get_all_user_ids", return_value=["100"]),
        patch("bot.inactivity.get_last_seen", return_value=1000),
        patch("bot.inactivity._suggested_topic", return_value="Ֆիզիկա"),
        patch("bot.inactivity.bot") as mock_bot,
    ):
        s.get.return_value = None
        from bot.inactivity import run_inactivity_nudges

        now = 1000 + 1 * DAY  # only 1 day → still active
        assert run_inactivity_nudges(now, "2026-07-10") == 0
        mock_bot.send_message.assert_not_called()


def test_skips_user_in_cooldown():
    with (
        patch("bot.inactivity.store") as s,
        patch("bot.inactivity.get_all_user_ids", return_value=["100"]),
        patch("bot.inactivity.get_last_seen", return_value=1000),
        patch("bot.inactivity._suggested_topic", return_value="Ֆիզիկա"),
        patch("bot.inactivity.bot") as mock_bot,
    ):
        s.get.return_value = "2026-07-08"  # cooldown marker present → skip
        from bot.inactivity import run_inactivity_nudges

        now = 1000 + 5 * DAY
        assert run_inactivity_nudges(now, "2026-07-10") == 0
        mock_bot.send_message.assert_not_called()


def test_skips_user_with_no_topic():
    with (
        patch("bot.inactivity.store") as s,
        patch("bot.inactivity.get_all_user_ids", return_value=["100"]),
        patch("bot.inactivity.get_last_seen", return_value=1000),
        patch("bot.inactivity._suggested_topic", return_value=None),
        patch("bot.inactivity.bot") as mock_bot,
    ):
        s.get.return_value = None
        from bot.inactivity import run_inactivity_nudges

        now = 1000 + 5 * DAY
        assert run_inactivity_nudges(now, "2026-07-10") == 0
        mock_bot.send_message.assert_not_called()


def test_one_bad_user_does_not_stop_the_scan():
    with (
        patch("bot.inactivity.store") as s,
        patch("bot.inactivity.get_all_user_ids", return_value=["bad", "100"]),
        patch("bot.inactivity.get_last_seen", return_value=1000),
        patch("bot.inactivity._suggested_topic", return_value="Ֆիզիկա"),
        patch("bot.inactivity.bot") as mock_bot,
    ):
        s.get.return_value = None
        from bot.inactivity import run_inactivity_nudges

        # "bad" int() raises inside the loop; the scan continues to "100".
        now = 1000 + 5 * DAY
        assert run_inactivity_nudges(now, "2026-07-10") == 1
        mock_bot.send_message.assert_called_once()


def test_run_inactivity_nudges_noop_without_store():
    with patch("bot.inactivity.store", None):
        from bot.inactivity import run_inactivity_nudges

        assert run_inactivity_nudges(0, "2026-01-01") == 0
