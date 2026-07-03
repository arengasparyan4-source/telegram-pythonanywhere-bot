from unittest.mock import MagicMock, patch

EXAM = "🎯 <b>Հիմնական կետեր</b>\n• ...\n📝 <b>Վարժանք</b>\n1. ..."


def make_message(text="/exam", user_id=123, chat_id=456):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.chat.type = "private"
    msg.reply_to_message = None
    return msg


# ── ai.generate_exam ─────────────────────────────────────────────────────────
def test_generate_exam_returns_text():
    with patch("bot.ai.generate", return_value=EXAM) as mock_gen:
        from bot.ai import generate_exam

        out = generate_exam(123, "Ֆիզիկա")
        assert out == EXAM
        sent = mock_gen.call_args[0][1][-1]["content"]
        assert "Ֆիզիկա" in sent and "10" in sent


def test_generate_exam_sanitizes():
    with patch("bot.ai.generate", return_value="Դաս 你好"):
        from bot.ai import generate_exam

        assert "你好" not in generate_exam(123, "t")


# ── handlers: /exam flow ─────────────────────────────────────────────────────
def test_cmd_exam_sets_mode_and_prompts():
    with (
        patch("bot.handlers.set_mode", return_value=True) as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_exam

        cmd_exam(make_message(text="/exam"))
        mock_set.assert_called_once_with(123, "exam")
        assert "պատրաստ" in mock_bot.send_message.call_args[0][1].lower()


def test_cmd_exam_requires_store():
    with (
        patch("bot.handlers.set_mode", return_value=False),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_exam

        cmd_exam(make_message(text="/exam"))
        assert "հիշողություն" in mock_bot.send_message.call_args[0][1]


def test_exam_mode_generates_and_clears():
    with (
        patch("bot.handlers.should_respond", return_value=True),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.BOT_INFO", MagicMock(username="testbot")),
        patch("bot.handlers.touch_user"),
        patch("bot.handlers.incr_messages"),
        patch("bot.handlers.get_mode", return_value={"mode": "exam"}),
        patch("bot.handlers.clear_mode") as mock_clear,
        patch("bot.handlers.generate_exam", return_value=EXAM) as mock_gen,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.ask_ai") as mock_ask,
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import handle_message

        handle_message(make_message(text="Ֆիզիկա"))
        mock_gen.assert_called_once_with(123, "Ֆիզիկա")
        mock_clear.assert_called_once_with(123)
        mock_ask.assert_not_called()
        assert EXAM in mock_send.call_args[0][1]
