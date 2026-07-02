import json
from unittest.mock import MagicMock, patch


def _dict_store():
    saved = {}
    s = MagicMock()
    s.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    s.get.side_effect = lambda k: saved.get(k)
    return s, saved


# ── bot/activity.py ──────────────────────────────────────────────────────────
def test_record_activity_streak_increments_on_consecutive_days():
    s, saved = _dict_store()
    with patch("bot.activity.store", s):
        from bot.activity import record_activity

        assert record_activity(7, today="2026-07-01") == 1
        assert record_activity(7, today="2026-07-02") == 2
        assert record_activity(7, today="2026-07-03") == 3
        # Same day again does not bump the streak.
        assert record_activity(7, today="2026-07-03") == 3


def test_record_activity_resets_after_gap():
    s, saved = _dict_store()
    with patch("bot.activity.store", s):
        from bot.activity import record_activity

        record_activity(7, today="2026-07-01")
        record_activity(7, today="2026-07-02")
        assert record_activity(7, today="2026-07-05") == 1  # gap resets


def test_days_active_last_n_counts_within_window():
    s, saved = _dict_store()
    saved["activity:7"] = json.dumps(
        {"last": "2026-07-10", "streak": 1, "days": ["2026-07-01", "2026-07-08", "2026-07-10"]}
    )
    with patch("bot.activity.store", s):
        from bot.activity import days_active_last_n

        # Window 2026-07-04..2026-07-10 includes 07-08 and 07-10 only.
        assert days_active_last_n(7, n=7, today="2026-07-10") == 2


def test_activity_stateless_is_zero():
    with patch("bot.activity.store", None):
        from bot.activity import get_streak, record_activity

        assert record_activity(7) == 0
        assert get_streak(7) == 0


# ── bot/achievements.py ──────────────────────────────────────────────────────
def test_check_and_award_first_conspectus():
    s, saved = _dict_store()
    with (
        patch("bot.achievements.store", s),
        patch("bot.achievements.get_stats", return_value={"topics": 1, "conspectuses": 1, "quizzes": 0, "flashcards": 0}),
        patch("bot.achievements.get_streak", return_value=1),
    ):
        from bot.achievements import check_and_award

        newly = check_and_award(7)
        assert newly == ["🥇 Առաջին կոնսպեկտ"]
        # Second call awards nothing new.
        assert check_and_award(7) == []


def test_check_and_award_multiple_thresholds():
    s, saved = _dict_store()
    with (
        patch("bot.achievements.store", s),
        patch("bot.achievements.get_stats", return_value={"topics": 5, "conspectuses": 5, "quizzes": 5, "flashcards": 0}),
        patch("bot.achievements.get_streak", return_value=3),
    ):
        from bot.achievements import check_and_award, get_badges

        newly = check_and_award(7)
        assert set(newly) == {
            "🥇 Առաջին կոնսպեկտ",
            "📚 5 թեմա",
            "🧠 Quiz մաեստրո",
            "⚡ Ակտիվ ուսանող",
        }
        assert len(get_badges(7)) == 4


def test_achievements_stateless():
    with patch("bot.achievements.store", None):
        from bot.achievements import check_and_award, get_badges

        assert check_and_award(7) == []
        assert get_badges(7) == []


# ── handlers: /achievements + award notifications ────────────────────────────
def _msg(user_id=123, chat_id=456):
    m = MagicMock()
    m.from_user.id = user_id
    m.chat.id = chat_id
    return m


def test_cmd_achievements_empty():
    with (
        patch("bot.handlers.get_badges", return_value=[]),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_achievements

        cmd_achievements(_msg())
        assert "դեռ նշաններ չունես" in mock_bot.send_message.call_args[0][1]


def test_cmd_achievements_lists_badges():
    with (
        patch("bot.handlers.get_badges", return_value=["🥇 Առաջին կոնսպեկտ", "📚 5 թեմա"]),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_achievements

        cmd_achievements(_msg())
        sent = mock_bot.send_message.call_args[0][1]
        assert "🥇 Առաջին կոնսպեկտ" in sent and "📚 5 թեմա" in sent


def test_award_new_badges_sends_congrats_per_badge():
    with (
        patch("bot.handlers.check_and_award", return_value=["🥇 Առաջին կոնսպեկտ"]),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _award_new_badges

        _award_new_badges(456, 123)
        sent = mock_bot.send_message.call_args[0][1]
        assert "Շնորհավո" in sent and "🥇 Առաջին կոնսպեկտ" in sent


def test_award_new_badges_silent_when_none():
    with (
        patch("bot.handlers.check_and_award", return_value=[]),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _award_new_badges

        _award_new_badges(456, 123)
        mock_bot.send_message.assert_not_called()
