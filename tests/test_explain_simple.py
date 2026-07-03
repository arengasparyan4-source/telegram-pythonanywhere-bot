from unittest.mock import MagicMock, patch

SIMPLE = "Պատկերացրու, որ արևը մեծ ջեռուցիչ է..."


# ── ai.explain_simply ────────────────────────────────────────────────────────
def test_explain_simply_returns_text():
    with patch("bot.ai.generate", return_value=SIMPLE) as mock_gen:
        from bot.ai import explain_simply

        out = explain_simply(123, "Ֆոտոսինթեզ", "notes")
        assert out == SIMPLE
        sent = mock_gen.call_args[0][1][-1]["content"]
        assert "Ֆոտոսինթեզ" in sent and "notes" in sent
        # The prompt asks for a 5-year-old-level explanation.
        assert "5-year-old" in sent


def test_explain_simply_sanitizes_foreign_scripts():
    with patch("bot.ai.generate", return_value="просто 你好"):
        from bot.ai import explain_simply

        assert "你好" not in explain_simply(123, "t", "notes")


# ── handlers: _send_simple + callback ────────────────────────────────────────
def _call(data="simple:show", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


def test_send_simple_without_conspectus_prompts():
    with (
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_simple

        _send_simple(456, 123, MagicMock())
        assert "Նախ" in mock_bot.send_message.call_args[0][1]


def test_send_simple_sends_via_send_reply():
    msg = MagicMock()
    with (
        patch(
            "bot.handlers.get_last_conspectus",
            return_value={"topic": "t", "text": "b"},
        ),
        patch("bot.handlers.explain_simply", return_value=SIMPLE),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _send_simple

        _send_simple(456, 123, msg)
        args = mock_send.call_args[0]
        assert args[0] is msg
        assert SIMPLE in args[1] and "Պարզ" in args[1]


def test_cb_simple_routes():
    with (
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers._send_simple") as mock_send,
    ):
        from bot.handlers import cb_simple

        call = _call()
        cb_simple(call)
        mock_send.assert_called_once_with(456, 123, call.message)
        mock_bot.answer_callback_query.assert_called_once()
