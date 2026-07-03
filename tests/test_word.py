from unittest.mock import MagicMock, patch

DEF = "<b>Ֆոտոսինթեզ</b> — բույսերի սնունդ պատրաստելը։ Օրինակ՝ ..."


def make_message(text="/word", user_id=123, chat_id=456):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.chat.type = "private"
    msg.reply_to_message = None
    return msg


# ── ai.define_word ───────────────────────────────────────────────────────────
def test_define_word_returns_text():
    with patch("bot.ai.generate", return_value=DEF) as g:
        from bot.ai import define_word

        out = define_word(123, "ֆոտոսինթեզ")
        assert out == DEF
        assert "ֆոտոսինթեզ" in g.call_args[0][1][-1]["content"]


# ── handlers: /word inline + prompt + mode ───────────────────────────────────
def test_cmd_word_inline_defines_immediately():
    with (
        patch("bot.handlers.define_word", return_value=DEF) as mock_def,
        patch("bot.handlers.set_mode") as mock_set,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cmd_word

        cmd_word(make_message(text="/word ֆոտոսինթեզ"))
        mock_def.assert_called_once_with(123, "ֆոտոսինթեզ")
        mock_set.assert_not_called()  # no mode needed for inline form
        assert DEF in mock_send.call_args[0][1]


def test_cmd_word_no_arg_prompts_and_sets_mode():
    with (
        patch("bot.handlers.set_mode", return_value=True) as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_word

        cmd_word(make_message(text="/word"))
        mock_set.assert_called_once_with(123, "word_lookup")
        assert "Բառարան" in mock_bot.send_message.call_args[0][1]


def test_word_lookup_mode_defines_and_clears():
    with (
        patch("bot.handlers.should_respond", return_value=True),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.BOT_INFO", MagicMock(username="testbot")),
        patch("bot.handlers.touch_user"),
        patch("bot.handlers.incr_messages"),
        patch("bot.handlers.get_mode", return_value={"mode": "word_lookup"}),
        patch("bot.handlers.clear_mode") as mock_clear,
        patch("bot.handlers.define_word", return_value=DEF) as mock_def,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.ask_ai") as mock_ask,
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import handle_message

        handle_message(make_message(text="գոլորշիացում"))
        mock_def.assert_called_once_with(123, "գոլորշիացում")
        mock_clear.assert_called_once_with(123)
        mock_ask.assert_not_called()
        assert DEF in mock_send.call_args[0][1]
