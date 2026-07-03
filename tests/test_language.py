from unittest.mock import MagicMock, patch


def make_message(text="/language", user_id=123, chat_id=456):
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


# ── history: language storage ────────────────────────────────────────────────
def test_set_and_get_language():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import get_language, set_language

        assert get_language(7) == "hy"  # default
        assert set_language(7, "en") is True
        assert get_language(7) == "en"


def test_set_language_rejects_invalid():
    with patch("bot.history.store", MagicMock()):
        from bot.history import set_language

        assert set_language(7, "fr") is False


def test_get_language_default_when_stateless():
    with patch("bot.history.store", None):
        from bot.history import get_language, set_language

        assert set_language(7, "en") is False
        assert get_language(7) == "hy"


# ── i18n: translation + fallback ─────────────────────────────────────────────
def test_i18n_translates_by_language():
    with patch("bot.i18n.get_language", return_value="ru"):
        from bot.i18n import t

        assert "Русский" in t(7, "lang_set")


def test_i18n_falls_back_to_armenian():
    # An unknown key returns "", a known key in an untranslated slot falls
    # back to Armenian.
    with patch("bot.i18n.get_language", return_value="en"):
        from bot.i18n import t

        assert t(7, "no_such_key") == ""
        assert t(7, "btn_quiz") == "📝 Quiz"


def test_help_lines_localized():
    from bot.i18n import help_lines

    with patch("bot.i18n.get_language", return_value="en"):
        assert any(line.startswith("/start") for line in help_lines(7))
        assert any("study plan" in line for line in help_lines(7))
    with patch("bot.i18n.get_language", return_value="hy"):
        assert any("կոնսպեկտ" in line for line in help_lines(7))


# ── handlers: /language + /help localization ─────────────────────────────────
def test_cmd_language_shows_picker():
    with patch("bot.handlers.bot") as mock_bot:
        from bot.handlers import cmd_language

        cmd_language(make_message(text="/language"))
        assert mock_bot.send_message.call_args.kwargs.get("reply_markup") is not None


def test_cb_language_sets_and_confirms():
    with (
        patch("bot.handlers.set_language", return_value=True) as mock_set,
        patch("bot.handlers.t", return_value="✅ set") as mock_t,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cb_language

        cb_language(_call("lang:en"))
        mock_set.assert_called_once_with(123, "en")
        assert mock_bot.send_message.call_args[0][1] == "✅ set"


def test_cb_language_warns_without_store():
    with (
        patch("bot.handlers.set_language", return_value=False),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cb_language

        cb_language(_call("lang:en"))
        assert "հիշողություն" in mock_bot.send_message.call_args[0][1]


def test_cmd_help_uses_localized_lines():
    with (
        patch("bot.handlers.help_lines", return_value=["/start — go"]),
        patch("bot.handlers.t", side_effect=lambda uid, key, **kw: f"[{key}]"),
        patch("bot.handlers.HF_SPACE_ID", ""),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_help

        cmd_help(make_message(text="/help"))
        sent = mock_bot.send_message.call_args[0][1]
        assert "[help_title]" in sent and "/start — go" in sent
