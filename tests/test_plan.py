from unittest.mock import MagicMock, patch

PLAN = "<b>Երկուշաբթի</b>\n• Մաթեմատիկա — 30 րոպե"


# ── bot.session (transient mode) ─────────────────────────────────────────────
def _dict_store():
    saved = {}
    s = MagicMock()
    s.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    s.get.side_effect = lambda k: saved.get(k)
    s.delete.side_effect = lambda k: saved.pop(k, None)
    return s, saved


def test_session_set_get_clear_mode():
    s, _ = _dict_store()
    with patch("bot.session.store", s):
        from bot.session import clear_mode, get_mode, set_mode

        assert set_mode(7, "plan") is True
        assert get_mode(7) == {"mode": "plan"}
        clear_mode(7)
        assert get_mode(7) is None


def test_session_set_mode_with_data():
    s, _ = _dict_store()
    with patch("bot.session.store", s):
        from bot.session import get_mode, set_mode

        set_mode(7, "game_word", {"game": "abc"})
        assert get_mode(7) == {"mode": "game_word", "game": "abc"}


def test_session_stateless_mode():
    with patch("bot.session.store", None):
        from bot.session import get_mode, set_mode

        assert set_mode(7, "plan") is False
        assert get_mode(7) is None


# ── ai.generate_study_plan ───────────────────────────────────────────────────
def test_generate_study_plan_returns_text():
    with patch("bot.ai.generate", return_value=PLAN) as mock_gen:
        from bot.ai import generate_study_plan

        out = generate_study_plan(123, "Մաթեմ, Ֆիզիկա")
        assert out == PLAN
        sent = mock_gen.call_args[0][1][-1]["content"]
        assert "Մաթեմ, Ֆիզիկա" in sent


# ── handlers: /plan flow ─────────────────────────────────────────────────────
def make_message(text="hello", user_id=123, chat_id=456):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.chat.type = "private"
    msg.reply_to_message = None
    return msg


def test_cmd_plan_sets_mode_and_prompts():
    with (
        patch("bot.handlers.set_mode", return_value=True) as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_plan

        cmd_plan(make_message(text="/plan"))
        mock_set.assert_called_once_with(123, "plan")
        assert "պլան" in mock_bot.send_message.call_args[0][1].lower()


def test_cmd_plan_warns_without_store():
    with (
        patch("bot.handlers.set_mode", return_value=False),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_plan

        cmd_plan(make_message(text="/plan"))
        assert "հիշողություն" in mock_bot.send_message.call_args[0][1]


def test_plan_mode_generates_plan_and_clears_mode():
    with (
        patch("bot.handlers.should_respond", return_value=True),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.BOT_INFO", MagicMock(username="testbot")),
        patch("bot.handlers.get_mode", return_value={"mode": "plan"}),
        patch("bot.handlers.clear_mode") as mock_clear,
        patch("bot.handlers.generate_study_plan", return_value=PLAN) as mock_gen,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.ask_ai") as mock_ask,
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import handle_message

        handle_message(make_message(text="Մաթեմ, Ֆիզիկա"))
        mock_gen.assert_called_once_with(123, "Մաթեմ, Ֆիզիկա")
        mock_clear.assert_called_once_with(123)
        # A plan reply was sent and the message was NOT treated as a conspectus.
        mock_ask.assert_not_called()
        assert PLAN in mock_send.call_args[0][1]
