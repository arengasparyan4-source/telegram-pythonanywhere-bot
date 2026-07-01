from unittest.mock import MagicMock, patch


def _call(data, user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


# ── ai.expand_conspectus ────────────────────────────────────────────────────


def test_expand_conspectus_includes_topic_and_previous_text():
    captured = {}

    def fake_generate(user_id, messages):
        captured["messages"] = messages
        return "deeper notes"

    with patch("bot.ai.generate", side_effect=fake_generate):
        from bot.ai import expand_conspectus

        out = expand_conspectus(123, "Ֆոտոսինթեզ", "short notes")
        assert out == "deeper notes"
        user_msg = captured["messages"][-1]["content"]
        assert "Ֆոտոսինթեզ" in user_msg
        assert "short notes" in user_msg
        # System prompt is still in front.
        assert captured["messages"][0]["role"] == "system"


# ── handlers: "more detail" button ──────────────────────────────────────────


def test_more_detail_without_cache_prompts_topic():
    with (
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.expand_conspectus") as mock_expand,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _more_detail

        _more_detail(456, 123, MagicMock())
        mock_expand.assert_not_called()
        sent = mock_bot.send_message.call_args[0][1]
        assert "Չգտա" in sent


def test_more_detail_regenerates_and_recaches():
    msg = MagicMock()
    msg.chat.id = 456
    with (
        patch(
            "bot.handlers.get_last_conspectus",
            return_value={"topic": "Ֆոտոսինթեզ", "text": "old"},
        ),
        patch("bot.handlers.expand_conspectus", return_value="DEEPER") as mock_expand,
        patch("bot.handlers.save_last_conspectus") as mock_save,
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _more_detail

        _more_detail(456, 123, msg)
        mock_expand.assert_called_once_with(123, "Ֆոտոսինթեզ", "old")
        # Expanded version replaces the cached conspectus.
        mock_save.assert_called_once_with(123, "Ֆոտոսինթեզ", "DEEPER")
        # Re-sent with the inline keyboard.
        args, kwargs = mock_send.call_args
        assert args[1] == "DEEPER"
        assert kwargs.get("reply_markup") is not None


def test_more_detail_handles_generation_error():
    with (
        patch(
            "bot.handlers.get_last_conspectus",
            return_value={"topic": "t", "text": "old"},
        ),
        patch("bot.handlers.expand_conspectus", side_effect=Exception("boom")),
        patch("bot.handlers.save_last_conspectus") as mock_save,
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _more_detail

        _more_detail(456, 123, MagicMock())
        mock_save.assert_not_called()
        mock_send.assert_not_called()
        sent = mock_bot.send_message.call_args[0][1]
        assert "այնպես չգնաց" in sent


# ── handlers: "different topic" button ──────────────────────────────────────


def test_prompt_new_topic_message():
    with patch("bot.handlers.bot") as mock_bot:
        from bot.handlers import _prompt_new_topic

        _prompt_new_topic(456)
        sent = mock_bot.send_message.call_args[0][1]
        assert "նոր" in sent


# ── handlers: callback routing ──────────────────────────────────────────────


def test_cb_conspectus_routes_more_and_new():
    with (
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers._more_detail") as mock_more,
        patch("bot.handlers._prompt_new_topic") as mock_new,
    ):
        from bot.handlers import cb_conspectus

        c1 = _call("consp:more")
        cb_conspectus(c1)
        mock_more.assert_called_once_with(456, 123, c1.message)

        cb_conspectus(_call("consp:new"))
        mock_new.assert_called_once_with(456)
        assert mock_bot.answer_callback_query.call_count == 2
