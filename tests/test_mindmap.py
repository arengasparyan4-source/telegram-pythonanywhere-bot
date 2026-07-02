from unittest.mock import MagicMock, patch

TREE = (
    "🌍 Ֆոտոսինթեզ\n"
    "  ├── 📌 Բաղադրիչներ\n"
    "  │     ├── ջուր\n"
    "  │     └── արև\n"
    "  └── 📌 Արդյունք"
)


# ── ai.generate_mindmap ──────────────────────────────────────────────────────
def test_generate_mindmap_returns_tree():
    with patch("bot.ai.generate", return_value=TREE):
        from bot.ai import generate_mindmap

        out = generate_mindmap(123, "Ֆոտոսինթեզ", "notes")
        assert out == TREE


def test_generate_mindmap_strips_code_fence():
    with patch("bot.ai.generate", return_value="```\n" + TREE + "\n```"):
        from bot.ai import generate_mindmap

        assert generate_mindmap(123, "t", "notes") == TREE


# ── handlers: _send_mindmap + callback ───────────────────────────────────────
def _call(data="mindmap:show", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


def test_send_mindmap_without_conspectus_prompts():
    with (
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_mindmap

        _send_mindmap(456, 123)
        assert "Նախ" in mock_bot.send_message.call_args[0][1]


def test_send_mindmap_failure_message():
    with (
        patch("bot.handlers.get_last_conspectus", return_value={"topic": "t", "text": "b"}),
        patch("bot.handlers.generate_mindmap", return_value="   "),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_mindmap

        _send_mindmap(456, 123)
        assert "Չստացվեց" in mock_bot.send_message.call_args[0][1]


def test_send_mindmap_sends_tree_plain():
    with (
        patch("bot.handlers.get_last_conspectus", return_value={"topic": "t", "text": "b"}),
        patch("bot.handlers.generate_mindmap", return_value=TREE),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_mindmap

        _send_mindmap(456, 123)
        # Sent verbatim (no parse_mode) to preserve tree formatting.
        args, kwargs = mock_bot.send_message.call_args
        assert args == (456, TREE)
        assert "parse_mode" not in kwargs


def test_cb_mindmap_routes():
    with (
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers._send_mindmap") as mock_send,
    ):
        from bot.handlers import cb_mindmap

        cb_mindmap(_call())
        mock_send.assert_called_once_with(456, 123)
        mock_bot.answer_callback_query.assert_called_once()
