from unittest.mock import MagicMock, patch

WHY = "Ֆոտոսինթեզը կարևոր է, որովհետև բույսերն են արտադրում թթվածինը, որով մենք շնչում ենք։"


# ── ai.generate_why_matters ──────────────────────────────────────────────────
def test_generate_why_matters_returns_text():
    with patch("bot.ai.generate", return_value=WHY) as mock_gen:
        from bot.ai import generate_why_matters

        out = generate_why_matters(123, "Ֆոտոսինթեզ", "notes")
        assert out == WHY
        sent = mock_gen.call_args[0][1][-1]["content"]
        assert "Ֆոտոսինթեզ" in sent and "notes" in sent


# ── handlers: _send_why_matters + callback ───────────────────────────────────
def _call(data="why:show", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


def test_send_why_without_conspectus_prompts():
    with (
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_why_matters

        _send_why_matters(456, 123, MagicMock())
        assert "Նախ" in mock_bot.send_message.call_args[0][1]


def test_send_why_failure_message():
    with (
        patch("bot.handlers.get_last_conspectus", return_value={"topic": "t", "text": "b"}),
        patch("bot.handlers.generate_why_matters", return_value=""),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_why_matters

        _send_why_matters(456, 123, MagicMock())
        assert "Չստացվեց" in mock_bot.send_message.call_args[0][1]


def test_send_why_sends_via_send_reply_with_header():
    msg = MagicMock()
    with (
        patch("bot.handlers.get_last_conspectus", return_value={"topic": "t", "text": "b"}),
        patch("bot.handlers.generate_why_matters", return_value=WHY),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _send_why_matters

        _send_why_matters(456, 123, msg)
        text = mock_send.call_args[0][1]
        assert text.startswith("🌍") and WHY in text


def test_cb_why_routes():
    with (
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers._send_why_matters") as mock_send,
    ):
        from bot.handlers import cb_why_matters

        call = _call()
        cb_why_matters(call)
        mock_send.assert_called_once_with(456, 123, call.message)
        mock_bot.answer_callback_query.assert_called_once()
