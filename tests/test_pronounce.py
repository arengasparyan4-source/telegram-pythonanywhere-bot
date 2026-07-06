"""Pronunciation (Feature 11): pronounce_term in bot/ai.py plus the /pronounce
command, the 🗣 button under /word, and the callback in bot/handlers.py."""

from unittest.mock import MagicMock, patch

GUIDE = "ֆո-տո-<b>ՍԻՆ</b>-թեզ"


def make_message(text="/pronounce", user_id=123, chat_id=456):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.chat.type = "private"
    msg.reply_to_message = None
    return msg


def make_call(data="pron:ֆոտոսինթեզ", user_id=777, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


# ── ai.pronounce_term ─────────────────────────────────────────────────────────
def test_pronounce_term_returns_guide_and_includes_term():
    with patch("bot.ai.generate", return_value=GUIDE) as g:
        from bot.ai import pronounce_term

        out = pronounce_term(123, "ֆոտոսինթեզ")
        assert out == GUIDE
        assert "ֆոտոսինթեզ" in g.call_args[0][1][-1]["content"]


def test_pronounce_term_sanitizes():
    with patch("bot.ai.generate", return_value="ֆո-տո 你好"):
        from bot.ai import pronounce_term

        assert "你好" not in pronounce_term(123, "t")


# ── _pron_keyboard ────────────────────────────────────────────────────────────
def test_pron_keyboard_omitted_for_overlong_word():
    from bot.handlers import _pron_keyboard

    # 40 Armenian chars ≈ 80 bytes UTF-8 → exceeds the 64-byte callback cap.
    assert _pron_keyboard("ա" * 40) is None


def test_pron_keyboard_built_for_normal_word():
    with patch("bot.handlers.types") as mock_types:
        from bot.handlers import _pron_keyboard

        _pron_keyboard("ֆոտոսինթեզ")
        datas = [
            kw.get("callback_data")
            for _a, kw in mock_types.InlineKeyboardButton.call_args_list
        ]
        assert "pron:ֆոտոսինթեզ" in datas


# ── handlers: /pronounce ───────────────────────────────────────────────────────
def test_cmd_pronounce_inline_pronounces_immediately():
    with (
        patch("bot.handlers.pronounce_term", return_value=GUIDE) as mock_pron,
        patch("bot.handlers.set_mode") as mock_set,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cmd_pronounce

        cmd_pronounce(make_message(text="/pronounce ֆոտոսինթեզ"))
        mock_pron.assert_called_once_with(123, "ֆոտոսինթեզ")
        mock_set.assert_not_called()
        assert GUIDE in mock_send.call_args[0][1]


def test_cmd_pronounce_no_arg_sets_mode():
    with (
        patch("bot.handlers.set_mode", return_value=True) as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_pronounce

        cmd_pronounce(make_message(text="/pronounce"))
        mock_set.assert_called_once_with(123, "pronounce_lookup")
        assert "Արտասանություն" in mock_bot.send_message.call_args[0][1]


def test_pronounce_lookup_mode_pronounces_and_clears():
    with (
        patch("bot.handlers.should_respond", return_value=True),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.BOT_INFO", MagicMock(username="testbot")),
        patch("bot.handlers.touch_user"),
        patch("bot.handlers.incr_messages"),
        patch("bot.handlers.note_message", return_value=False),
        patch("bot.handlers.get_mode", return_value={"mode": "pronounce_lookup"}),
        patch("bot.handlers.clear_mode") as mock_clear,
        patch("bot.handlers.pronounce_term", return_value=GUIDE) as mock_pron,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.ask_ai") as mock_ask,
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import handle_message

        handle_message(make_message(text="ջերմաստիճան"))
        mock_pron.assert_called_once_with(123, "ջերմաստիճան")
        mock_clear.assert_called_once_with(123)
        mock_ask.assert_not_called()
        assert GUIDE in mock_send.call_args[0][1]


# ── handlers: 🗣 button under a word definition ────────────────────────────────
def test_cb_pronounce_uses_tapping_user_not_message_owner():
    with (
        patch("bot.handlers.pronounce_term", return_value=GUIDE) as mock_pron,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply"),
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cb_pronounce

        # data carries the word; user id must come from call.from_user (777),
        # NOT call.message.from_user (the bot).
        cb_pronounce(make_call(data="pron:ֆոտոսինթեզ", user_id=777))
        mock_pron.assert_called_once_with(777, "ֆոտոսինթեզ")


def test_cb_pronounce_handles_term_with_colon():
    with (
        patch("bot.handlers.pronounce_term", return_value=GUIDE) as mock_pron,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply"),
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cb_pronounce

        cb_pronounce(make_call(data="pron:a:b", user_id=1))
        mock_pron.assert_called_once_with(1, "a:b")  # not split on ':'


def test_define_word_attaches_pronounce_button():
    with (
        patch("bot.handlers.define_word", return_value="📖 բացատրություն"),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _define_word

        _define_word(make_message(), "ֆոտոսինթեզ")
        # send_reply called with a reply_markup (the pronounce keyboard).
        assert mock_send.call_args[1].get("reply_markup") is not None
