from unittest.mock import MagicMock, patch


def make_message(text="hi", user_id=123, chat_id=456):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.chat.type = "private"
    msg.reply_to_message = None
    return msg


def _call(data="ask:stop", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


# ── ai.answer_question ───────────────────────────────────────────────────────
def test_answer_question_returns_text():
    with patch("bot.ai.generate", return_value="Որովհետև երկինքը ցրում է լույսը։") as g:
        from bot.ai import answer_question

        out = answer_question(123, "Ինչո՞ւ է երկինքը կապույտ")
        assert out == "Որովհետև երկինքը ցրում է լույսը։"
        assert "Ինչո՞ւ է երկինքը կապույտ" in g.call_args[0][1][-1]["content"]


# ── handlers: /ask flow ──────────────────────────────────────────────────────
def test_cmd_ask_enters_mode():
    with (
        patch("bot.handlers.set_mode", return_value=True) as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_ask

        cmd_ask(make_message(text="/ask"))
        mock_set.assert_called_once_with(123, "ask")
        assert mock_bot.send_message.call_args.kwargs.get("reply_markup") is not None


def test_cmd_ask_requires_store():
    with (
        patch("bot.handlers.set_mode", return_value=False),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_ask

        cmd_ask(make_message(text="/ask"))
        assert "հիշողություն" in mock_bot.send_message.call_args[0][1]


def test_ask_mode_answers_and_stays_in_mode():
    with (
        patch("bot.handlers.should_respond", return_value=True),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.BOT_INFO", MagicMock(username="testbot")),
        patch("bot.handlers.get_mode", return_value={"mode": "ask"}),
        patch("bot.handlers.set_mode", return_value=True) as mock_set,
        patch("bot.handlers.answer_question", return_value="Պատասխան") as mock_ans,
        patch("bot.handlers.ask_ai") as mock_ask_ai,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import handle_message

        handle_message(make_message(text="Ի՞նչ է ջուրը"))
        mock_ans.assert_called_once_with(123, "Ի՞նչ է ջուրը")
        # Not treated as a conspectus, and the mode is refreshed (stays in ask).
        mock_ask_ai.assert_not_called()
        mock_set.assert_called_with(123, "ask")
        assert mock_send.call_args[0][1] == "Պատասխան"


def test_cb_ask_stop_clears_mode():
    with (
        patch("bot.handlers.clear_mode") as mock_clear,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cb_ask

        cb_ask(_call("ask:stop"))
        mock_clear.assert_called_once_with(123)
        assert "Ավարտ" in mock_bot.send_message.call_args[0][1]
