"""Draw the topic (Feature 12): participation tracking in bot/drawings.py and
the photo handler in bot/handlers.py (warm acknowledgement, no image analysis)."""

from unittest.mock import MagicMock, patch


def make_photo(user_id=123, chat_id=456, chat_type="private", reply_to=None):
    msg = MagicMock()
    msg.text = None
    msg.caption = None
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.chat.type = chat_type
    msg.reply_to_message = reply_to
    return msg


# ── drawings counter ──────────────────────────────────────────────────────────
def test_record_drawing_increments_counter():
    with patch("bot.drawings.store") as s:
        s.incr.return_value = 3
        from bot.drawings import record_drawing

        assert record_drawing(123) == 3
        s.incr.assert_called_once_with("stat:drawings:123")


def test_record_drawing_noop_without_store():
    with patch("bot.drawings.store", None):
        from bot.drawings import record_drawing

        assert record_drawing(123) == 0


def test_get_drawing_count_reads_counter():
    with patch("bot.drawings.store") as s:
        s.get.return_value = "5"
        from bot.drawings import get_drawing_count

        assert get_drawing_count(123) == 5


# ── handlers: photo handler ────────────────────────────────────────────────────
def test_handle_photo_acknowledges_warmly_and_records():
    with (
        patch("bot.handlers.touch_user") as mock_touch,
        patch("bot.handlers.record_drawing", return_value=1) as mock_rec,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import handle_photo

        handle_photo(make_photo())
        mock_rec.assert_called_once_with(123)
        mock_touch.assert_called_once_with(123)
        sent = mock_bot.send_message.call_args[0][1]
        assert "նկար" in sent  # warm acknowledgement, no analysis


def test_handle_photo_mentions_count_after_first():
    with (
        patch("bot.handlers.touch_user"),
        patch("bot.handlers.record_drawing", return_value=4),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import handle_photo

        handle_photo(make_photo())
        sent = mock_bot.send_message.call_args[0][1]
        assert "4" in sent


def test_handle_photo_silent_in_group_without_mention():
    with (
        patch("bot.handlers.BOT_INFO", MagicMock(id=42, username="testbot")),
        patch("bot.handlers.record_drawing") as mock_rec,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import handle_photo

        # A photo dropped in a group, not a reply to / mention of the bot.
        handle_photo(make_photo(chat_type="supergroup"))
        mock_rec.assert_not_called()
        mock_bot.send_message.assert_not_called()


def test_handle_photo_responds_in_group_when_reply_to_bot():
    reply = MagicMock()
    reply.from_user.id = 42  # the bot
    with (
        patch("bot.handlers.BOT_INFO", MagicMock(id=42, username="testbot")),
        patch("bot.handlers.touch_user"),
        patch("bot.handlers.record_drawing", return_value=1) as mock_rec,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import handle_photo

        handle_photo(make_photo(chat_type="supergroup", reply_to=reply))
        mock_rec.assert_called_once()
        mock_bot.send_message.assert_called_once()
