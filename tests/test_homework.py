from unittest.mock import MagicMock, patch

HOMEWORK = "1. Նկարիր ջրի շրջապտույտը։\n2. Բեր երեք օրինակ գոլորշիացման։"


# ── ai.generate_homework ─────────────────────────────────────────────────────
def test_generate_homework_returns_text():
    with patch("bot.ai.generate", return_value=HOMEWORK) as mock_gen:
        from bot.ai import generate_homework

        out = generate_homework(123, "Ջրի շրջապտույտ", "notes")
        assert out == HOMEWORK
        # Prompt references the topic and the notes.
        sent = mock_gen.call_args[0][1][-1]["content"]
        assert "Ջրի շրջապտույտ" in sent and "notes" in sent


def test_generate_homework_sanitizes_foreign_scripts():
    with patch("bot.ai.generate", return_value="1. задание 你好"):
        from bot.ai import generate_homework

        out = generate_homework(123, "t", "notes")
        assert "你好" not in out


# ── handlers: _send_homework + callback ──────────────────────────────────────
def _call(data="homework:show", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


def test_send_homework_without_conspectus_prompts():
    with (
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_homework

        _send_homework(456, 123, MagicMock())
        assert "Նախ" in mock_bot.send_message.call_args[0][1]


def test_send_homework_failure_message():
    with (
        patch(
            "bot.handlers.get_last_conspectus",
            return_value={"topic": "t", "text": "b"},
        ),
        patch("bot.handlers.generate_homework", return_value=""),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_homework

        _send_homework(456, 123, MagicMock())
        assert "Չստացվեց" in mock_bot.send_message.call_args[0][1]


def test_send_homework_sends_via_send_reply():
    msg = MagicMock()
    with (
        patch(
            "bot.handlers.get_last_conspectus",
            return_value={"topic": "t", "text": "b"},
        ),
        patch("bot.handlers.generate_homework", return_value=HOMEWORK),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _send_homework

        _send_homework(456, 123, msg)
        args = mock_send.call_args[0]
        assert args[0] is msg
        assert HOMEWORK in args[1] and "Տնային" in args[1]


def test_cb_homework_routes():
    with (
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers._send_homework") as mock_send,
    ):
        from bot.handlers import cb_homework

        call = _call()
        cb_homework(call)
        mock_send.assert_called_once_with(456, 123, call.message)
        mock_bot.answer_callback_query.assert_called_once()
