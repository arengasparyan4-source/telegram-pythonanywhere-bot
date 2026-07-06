"""Spaced repetition (Feature 7): the review schedule in bot/history.py and
the /review command + wiring in bot/handlers.py."""

import json
from unittest.mock import MagicMock, patch

DAY = 86400


def make_message(text="/review", user_id=123, chat_id=456):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.chat.type = "private"
    msg.reply_to_message = None
    return msg


def make_call(data="review:show:0", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


# ── history: schedule ─────────────────────────────────────────────────────────
def test_record_study_starts_schedule_at_stage_zero():
    with patch("bot.history.store") as s:
        s.get.return_value = None
        from bot.history import record_study

        record_study(123, "Ֆիզիկա", now=1000)
        saved = json.loads(s.set.call_args[0][1])
        assert saved["Ֆիզիկա"] == {"studied": 1000, "stage": 0}


def test_record_study_ignores_blank_topic():
    with patch("bot.history.store") as s:
        from bot.history import record_study

        record_study(123, "   ", now=1000)
        s.set.assert_not_called()


def test_get_due_reviews_due_only_after_interval():
    reviews = {"T": {"studied": 1000, "stage": 0}}  # stage 0 → due after 1 day
    with patch("bot.history.store") as s:
        s.get.return_value = json.dumps(reviews)
        from bot.history import get_due_reviews

        assert get_due_reviews(1, now=1000 + DAY) == ["T"]
        assert get_due_reviews(1, now=1000 + DAY - 1) == []


def test_get_due_reviews_orders_most_overdue_first():
    reviews = {
        "recent": {"studied": 5000, "stage": 0},
        "old": {"studied": 1000, "stage": 0},
    }
    with patch("bot.history.store") as s:
        s.get.return_value = json.dumps(reviews)
        from bot.history import get_due_reviews

        # Both due; the one studied longest ago (earliest due_at) comes first.
        assert get_due_reviews(1, now=5000 + DAY) == ["old", "recent"]


def test_get_due_reviews_skips_graduated_topics():
    # stage 3 == len(intervals) → fully reviewed, never due again.
    reviews = {"T": {"studied": 0, "stage": 3}}
    with patch("bot.history.store") as s:
        s.get.return_value = json.dumps(reviews)
        from bot.history import get_due_reviews

        assert get_due_reviews(1, now=10**12) == []


def test_mark_reviewed_advances_stage_and_restamps():
    reviews = {"T": {"studied": 1000, "stage": 0}}
    with patch("bot.history.store") as s:
        s.get.return_value = json.dumps(reviews)
        from bot.history import mark_reviewed

        mark_reviewed(1, "T", now=2000)
        saved = json.loads(s.set.call_args[0][1])
        assert saved["T"]["stage"] == 1
        assert saved["T"]["studied"] == 2000


def test_review_functions_are_noops_without_store():
    with patch("bot.history.store", None):
        from bot.history import get_due_reviews, mark_reviewed, record_study

        record_study(1, "T")  # must not raise
        mark_reviewed(1, "T")  # must not raise
        assert get_due_reviews(1) == []


# ── handlers: /review ─────────────────────────────────────────────────────────
def test_cmd_review_no_due_topics():
    with (
        patch("bot.handlers.get_due_reviews", return_value=[]),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_review

        cmd_review(make_message())
        assert "կրկնել" in mock_bot.send_message.call_args[0][1]


def test_cmd_review_lists_due_topics_with_buttons():
    with (
        patch("bot.handlers.get_due_reviews", return_value=["Ֆիզիկա", "Քիմիա"]),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_review

        cmd_review(make_message())
        kwargs = mock_bot.send_message.call_args[1]
        assert kwargs.get("reply_markup") is not None


def test_cb_review_marks_reviewed_then_regenerates():
    with (
        patch("bot.handlers.get_due_reviews", return_value=["Ֆիզիկա"]),
        patch("bot.handlers.mark_reviewed") as mock_mark,
        patch("bot.handlers._regenerate_from_topic") as mock_regen,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cb_review

        cb_review(make_call("review:show:0"))
        mock_mark.assert_called_once_with(123, "Ֆիզիկա")
        mock_regen.assert_called_once()
        assert mock_regen.call_args[0][2] == "Ֆիզիկա"


def test_cb_review_ignores_out_of_range_index():
    with (
        patch("bot.handlers.get_due_reviews", return_value=["Ֆիզիկա"]),
        patch("bot.handlers.mark_reviewed") as mock_mark,
        patch("bot.handlers._regenerate_from_topic") as mock_regen,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cb_review

        cb_review(make_call("review:show:5"))
        mock_mark.assert_not_called()
        mock_regen.assert_not_called()


# ── wiring: studying a topic enters the schedule ──────────────────────────────
def test_handle_message_records_study_on_conspectus():
    with (
        patch("bot.handlers.should_respond", return_value=True),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.BOT_INFO", MagicMock(username="testbot")),
        patch("bot.handlers.ask_ai", return_value="notes"),
        patch("bot.handlers.get_provider", return_value="main"),
        patch("bot.handlers.save_last_conspectus"),
        patch("bot.handlers.record_study") as mock_study,
        patch("bot.handlers.send_reply"),
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import handle_message

        handle_message(make_message(text="Ֆիզիկա"))
        mock_study.assert_called_once_with(123, "Ֆիզիկա")
