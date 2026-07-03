from unittest.mock import MagicMock, patch


def make_message(text="/favorites", user_id=123, chat_id=456):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.chat.type = "private"
    msg.reply_to_message = None
    return msg


def _call(data, user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


def _dict_store():
    saved = {}
    s = MagicMock()
    s.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    s.get.side_effect = lambda k: saved.get(k)
    s.delete.side_effect = lambda k: saved.pop(k, None)
    return s, saved


# ── history: favorites storage ───────────────────────────────────────────────
def test_add_and_get_favorites():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import add_favorite, get_favorites

        assert add_favorite(7, "Ֆոտոսինթեզ") is True
        assert add_favorite(7, "Ջրի շրջապտույտ") is True
        assert get_favorites(7) == ["Ֆոտոսինթեզ", "Ջրի շրջապտույտ"]


def test_add_favorite_dedups_case_insensitive():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import add_favorite, get_favorites

        assert add_favorite(7, "Ֆիզիկա") is True
        assert add_favorite(7, "ֆիզիկա") is False  # already saved
        assert get_favorites(7) == ["Ֆիզիկա"]


def test_add_favorite_rejects_blank_and_stateless():
    with patch("bot.history.store", MagicMock()):
        from bot.history import add_favorite

        assert add_favorite(7, "   ") is False
    with patch("bot.history.store", None):
        from bot.history import add_favorite, get_favorites

        assert add_favorite(7, "x") is False
        assert get_favorites(7) == []


def test_remove_favorite():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import add_favorite, get_favorites, remove_favorite

        add_favorite(7, "A")
        add_favorite(7, "B")
        remove_favorite(7, "a")  # case-insensitive
        assert get_favorites(7) == ["B"]


# ── handlers: /favorites + save/show callbacks ───────────────────────────────
def test_cmd_favorites_empty():
    with (
        patch("bot.handlers.get_favorites", return_value=[]),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_favorites

        cmd_favorites(make_message())
        assert "Դեռ" in mock_bot.send_message.call_args[0][1]


def test_cmd_favorites_lists_topics_as_buttons():
    with (
        patch("bot.handlers.get_favorites", return_value=["A", "B"]),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_favorites

        cmd_favorites(make_message())
        assert mock_bot.send_message.call_args.kwargs.get("reply_markup") is not None


def test_cb_fav_save_stores_last_conspectus():
    with (
        patch(
            "bot.handlers.get_last_conspectus",
            return_value={"topic": "Ֆոտոսինթեզ", "text": "b"},
        ),
        patch("bot.handlers.add_favorite", return_value=True) as mock_add,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cb_favorites

        cb_favorites(_call("fav:save"))
        mock_add.assert_called_once_with(123, "Ֆոտոսինթեզ")
        assert "Պահեցի" in mock_bot.send_message.call_args[0][1]


def test_cb_fav_save_without_conspectus():
    with (
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.add_favorite") as mock_add,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cb_favorites

        cb_favorites(_call("fav:save"))
        mock_add.assert_not_called()
        assert "Դեռ" in mock_bot.send_message.call_args[0][1]


def test_cb_fav_show_regenerates_conspectus():
    with (
        patch("bot.handlers.get_favorites", return_value=["Ֆոտոսինթեզ", "Ջուր"]),
        patch("bot.handlers._regenerate_from_topic") as mock_regen,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cb_favorites

        call = _call("fav:show:1")
        cb_favorites(call)
        mock_regen.assert_called_once_with(456, 123, "Ջուր", call.message)


def test_regenerate_from_topic_sends_conspectus():
    msg = MagicMock()
    with (
        patch("bot.handlers.ask_ai", return_value="Կոնսպեկտ") as mock_ask,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.save_last_conspectus") as mock_save,
        patch("bot.handlers.incr_topics"),
        patch("bot.handlers.incr_conspectuses"),
        patch("bot.handlers.record_activity"),
        patch("bot.handlers._award_new_badges"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _regenerate_from_topic

        _regenerate_from_topic(456, 123, "Ջուր", msg)
        mock_ask.assert_called_once_with(123, "Ջուր")
        mock_save.assert_called_once_with(123, "Ջուր", "Կոնսպեկտ")
        assert mock_send.call_args[0][1] == "Կոնսպեկտ"
        assert mock_send.call_args.kwargs.get("reply_markup") is not None
