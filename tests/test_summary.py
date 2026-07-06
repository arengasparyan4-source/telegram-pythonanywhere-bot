"""Auto summary (Feature 8): the session counter in bot/summary.py,
generate_summary in bot/ai.py, and the /summary command + offer wiring."""

import json
from unittest.mock import MagicMock, patch

RECAP = "📌 Այս սեսիայում սովորեցիր՝\n• ֆոտոսինթեզ\n• ջրի շրջապտույտ"


def make_message(text="/summary", user_id=123, chat_id=456):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.chat.type = "private"
    msg.reply_to_message = None
    return msg


def make_call(data="summary:make", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


# ── summary counter ───────────────────────────────────────────────────────────
def test_note_message_offers_every_summary_every():
    with (
        patch("bot.summary.store") as s,
        patch("bot.summary.SUMMARY_EVERY", 3),
    ):
        from bot.summary import note_message

        s.incr.side_effect = [1, 2, 3, 4, 5, 6]
        results = [note_message(123) for _ in range(6)]
        assert results == [False, False, True, False, False, True]


def test_note_message_refreshes_session_ttl():
    with patch("bot.summary.store") as s:
        s.incr.return_value = 1
        from bot.summary import note_message
        from bot.config import SUMMARY_SESSION_TTL

        note_message(123)
        s.expire.assert_called_once_with("summary:count:123", SUMMARY_SESSION_TTL)


def test_note_message_noop_without_store():
    with patch("bot.summary.store", None):
        from bot.summary import note_message

        assert note_message(123) is False


def test_note_message_survives_store_error():
    with patch("bot.summary.store") as s:
        s.incr.side_effect = Exception("db down")
        from bot.summary import note_message

        assert note_message(123) is False  # must not raise


# ── ai.generate_summary ───────────────────────────────────────────────────────
def test_generate_summary_empty_history_returns_blank():
    with patch("bot.ai.get_history", return_value=[]):
        from bot.ai import generate_summary

        assert generate_summary(123) == ""


def test_generate_summary_builds_recap_from_history():
    history = [
        {"role": "user", "content": "ֆոտոսինթեզ"},
        {"role": "assistant", "content": "Բույսերը լույսից սնունդ են ստանում..."},
    ]
    with (
        patch("bot.ai.get_history", return_value=history),
        patch("bot.ai.generate", return_value=RECAP) as g,
    ):
        from bot.ai import generate_summary

        out = generate_summary(123)
        assert out == RECAP
        # The transcript of recent turns is handed to the model.
        sent = g.call_args[0][1][-1]["content"]
        assert "ֆոտոսինթեզ" in sent


def test_generate_summary_does_not_touch_history():
    history = [{"role": "user", "content": "ջուր"}]
    with (
        patch("bot.ai.get_history", return_value=history),
        patch("bot.ai.save_history") as mock_save,
        patch("bot.ai.generate", return_value=RECAP),
    ):
        from bot.ai import generate_summary

        generate_summary(123)
        mock_save.assert_not_called()


# ── handlers: /summary + callback ─────────────────────────────────────────────
def test_cmd_summary_sends_recap():
    with (
        patch("bot.handlers.generate_summary", return_value=RECAP),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cmd_summary

        cmd_summary(make_message())
        assert RECAP in mock_send.call_args[0][1]


def test_cmd_summary_blank_recap_is_friendly():
    with (
        patch("bot.handlers.generate_summary", return_value=""),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_summary

        cmd_summary(make_message())
        mock_send.assert_not_called()
        assert "ամփոփ" in mock_bot.send_message.call_args[0][1]


def test_cb_summary_sends_recap():
    with (
        patch("bot.handlers.generate_summary", return_value=RECAP),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cb_summary

        cb_summary(make_call())
        assert RECAP in mock_send.call_args[0][1]


# ── handlers: the offer is posted when the counter says so ────────────────────
def test_handle_message_offers_summary_when_due():
    with (
        patch("bot.handlers.should_respond", return_value=True),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.BOT_INFO", MagicMock(username="testbot")),
        patch("bot.handlers.note_message", return_value=True),
        patch("bot.handlers.ask_ai", return_value="notes"),
        patch("bot.handlers.get_provider", return_value="main"),
        patch("bot.handlers.save_last_conspectus"),
        patch("bot.handlers.record_study"),
        patch("bot.handlers.send_reply"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import handle_message

        handle_message(make_message(text="ֆիզիկա"))
        # The offer message carries the summary button.
        offered = any(
            kwargs.get("reply_markup") is not None
            for _args, kwargs in mock_bot.send_message.call_args_list
        )
        assert offered


def test_handle_message_no_offer_when_not_due():
    with (
        patch("bot.handlers.should_respond", return_value=True),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.BOT_INFO", MagicMock(username="testbot")),
        patch("bot.handlers.note_message", return_value=False),
        patch("bot.handlers.ask_ai", return_value="notes"),
        patch("bot.handlers.get_provider", return_value="main"),
        patch("bot.handlers.save_last_conspectus"),
        patch("bot.handlers.record_study"),
        patch("bot.handlers.send_reply"),
        patch("bot.handlers._offer_summary") as mock_offer,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import handle_message

        handle_message(make_message(text="ֆիզիկա"))
        mock_offer.assert_not_called()
