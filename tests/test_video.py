"""Video suggestion (Feature 10): suggest_video_search in bot/ai.py and the
🎥 button handler in bot/handlers.py. No YouTube scraping — just a search URL."""

from unittest.mock import MagicMock, patch


def make_call(data="video:show", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


# ── ai.suggest_video_search ───────────────────────────────────────────────────
def test_suggest_video_search_returns_query():
    with patch("bot.ai.generate", return_value="ֆոտոսինթեզ բույսեր երեխաների համար") as g:
        from bot.ai import suggest_video_search

        out = suggest_video_search(123, "Ֆոտոսինթեզ")
        assert out == "ֆոտոսինթեզ բույսեր երեխաների համար"
        assert "Ֆոտոսինթեզ" in g.call_args[0][1][-1]["content"]


def test_suggest_video_search_keeps_first_line_and_strips_quotes():
    with patch("bot.ai.generate", return_value='"ջրի շրջապտույտ"\nextra second line'):
        from bot.ai import suggest_video_search

        assert suggest_video_search(123, "ջուր") == "ջրի շրջապտույտ"


def test_suggest_video_search_falls_back_to_topic_when_blank():
    with patch("bot.ai.generate", return_value="   "):
        from bot.ai import suggest_video_search

        assert suggest_video_search(123, "Հրաբուխներ") == "Հրաբուխներ"


# ── handlers: 🎥 button ────────────────────────────────────────────────────────
def test_video_suggestion_builds_youtube_search_url():
    with (
        patch(
            "bot.handlers.get_last_conspectus",
            return_value={"topic": "Ֆոտոսինթեզ", "text": "..."},
        ),
        patch("bot.handlers.suggest_video_search", return_value="ֆոտոսինթեզ երեխաների"),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _send_video_suggestion

        _send_video_suggestion(456, 123, MagicMock())
        sent = mock_send.call_args[0][1]
        assert "youtube.com/results?search_query=" in sent
        # The query is URL-encoded (spaces become +), never scraped.
        assert "search_query=%D6%86" in sent or "+" in sent
        assert "Ֆոտոսինթեզ" in sent


def test_video_suggestion_without_conspectus_prompts_topic():
    with (
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.suggest_video_search") as mock_sugg,
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_video_suggestion

        _send_video_suggestion(456, 123, MagicMock())
        mock_sugg.assert_not_called()
        mock_send.assert_not_called()
        assert "թեման" in mock_bot.send_message.call_args[0][1]


def test_video_suggestion_falls_back_to_topic_on_error():
    with (
        patch(
            "bot.handlers.get_last_conspectus",
            return_value={"topic": "Հրաբուխներ", "text": "..."},
        ),
        patch("bot.handlers.suggest_video_search", side_effect=Exception("boom")),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _send_video_suggestion

        _send_video_suggestion(456, 123, MagicMock())
        sent = mock_send.call_args[0][1]
        assert "youtube.com/results" in sent
        assert "Հրաբուխներ" in sent


def test_cb_video_routes_to_suggestion():
    with (
        patch("bot.handlers._send_video_suggestion") as mock_send,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cb_video

        call = make_call("video:show")
        cb_video(call)
        mock_send.assert_called_once_with(456, 123, call.message)
        mock_bot.answer_callback_query.assert_called_once()


def test_conspectus_keyboard_has_video_button():
    with (
        patch("bot.handlers.t", side_effect=lambda uid, key: key),
        patch("bot.handlers.types") as mock_types,
    ):
        from bot.handlers import _conspectus_keyboard

        _conspectus_keyboard(123)
        datas = [
            kw.get("callback_data")
            for _a, kw in mock_types.InlineKeyboardButton.call_args_list
        ]
        assert "video:show" in datas
