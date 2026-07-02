from unittest.mock import MagicMock, patch

STORY = "Մի անգամ մի փոքրիկ ջրի կաթիլ որոշեց ճամփորդել...\n\nԵվ այդպես սկսվեց արկածը։"


# ── ai.generate_story ────────────────────────────────────────────────────────
def test_generate_story_returns_text():
    with patch("bot.ai.generate", return_value=STORY) as mock_gen:
        from bot.ai import generate_story

        out = generate_story(123, "Ջրի շրջապտույտ", "notes")
        assert out == STORY
        # Prompt references the topic and the notes.
        sent = mock_gen.call_args[0][1][-1]["content"]
        assert "Ջրի շրջապտույտ" in sent and "notes" in sent


# ── handlers: _send_story + callback ─────────────────────────────────────────
def _call(data="story:show", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


def test_send_story_without_conspectus_prompts():
    with (
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_story

        _send_story(456, 123, MagicMock())
        assert "Նախ" in mock_bot.send_message.call_args[0][1]


def test_send_story_failure_message():
    with (
        patch("bot.handlers.get_last_conspectus", return_value={"topic": "t", "text": "b"}),
        patch("bot.handlers.generate_story", return_value=""),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_story

        _send_story(456, 123, MagicMock())
        assert "Չստացվեց" in mock_bot.send_message.call_args[0][1]


def test_send_story_sends_via_send_reply():
    msg = MagicMock()
    with (
        patch("bot.handlers.get_last_conspectus", return_value={"topic": "t", "text": "b"}),
        patch("bot.handlers.generate_story", return_value=STORY),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _send_story

        _send_story(456, 123, msg)
        args = mock_send.call_args[0]
        assert args[0] is msg
        assert STORY in args[1] and args[1].startswith("📖")


def test_cb_story_routes():
    with (
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers._send_story") as mock_send,
    ):
        from bot.handlers import cb_story

        call = _call()
        cb_story(call)
        mock_send.assert_called_once_with(456, 123, call.message)
        mock_bot.answer_callback_query.assert_called_once()
