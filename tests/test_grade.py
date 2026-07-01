from unittest.mock import MagicMock, patch


# ── grade state module ──────────────────────────────────────────────────────


def test_set_and_get_grade():
    fake_store = MagicMock()
    saved = {}
    fake_store.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    fake_store.get.side_effect = lambda k: saved.get(k)
    with patch("bot.grade.store", fake_store):
        from bot.grade import get_grade, set_grade

        assert set_grade(7, "5-9") is True
        assert get_grade(7) == "5-9"


def test_set_grade_rejects_invalid():
    with patch("bot.grade.store", MagicMock()):
        from bot.grade import set_grade

        assert set_grade(7, "13-14") is False


def test_get_grade_default_none_when_unset():
    fake_store = MagicMock()
    fake_store.get.return_value = None
    with patch("bot.grade.store", fake_store):
        from bot.grade import get_grade

        assert get_grade(7) is None


def test_grade_stateless_mode():
    with patch("bot.grade.store", None):
        from bot.grade import get_grade, set_grade

        assert set_grade(7, "5-9") is False
        assert get_grade(7) is None


def test_clear_grade():
    fake_store = MagicMock()
    saved = {"grade:7": "5-9"}
    fake_store.get.side_effect = lambda k: saved.get(k)
    fake_store.delete.side_effect = lambda k: saved.pop(k, None)
    with patch("bot.grade.store", fake_store):
        from bot.grade import clear_grade, get_grade

        clear_grade(7)
        assert get_grade(7) is None


# ── ai layer: grade clause injection ────────────────────────────────────────


def test_ask_ai_injects_grade_into_system_prompt():
    captured = {}
    with (
        patch("bot.ai.get_grade", return_value="5-9"),
        patch("bot.ai.get_history", return_value=[{"role": "user", "content": "prev"}]),
        patch("bot.ai.save_history"),
        patch("bot.ai.generate", side_effect=lambda uid, msgs: captured.update(msgs=msgs) or "ok"),
    ):
        from bot.ai import ask_ai

        ask_ai(123, "hello")
        system = captured["msgs"][0]["content"]
        assert "grades 5-9" in system


def test_ask_ai_no_grade_clause_when_unset():
    captured = {}
    with (
        patch("bot.ai.get_grade", return_value=None),
        patch("bot.ai.get_history", return_value=[{"role": "user", "content": "prev"}]),
        patch("bot.ai.save_history"),
        patch("bot.ai.generate", side_effect=lambda uid, msgs: captured.update(msgs=msgs) or "ok"),
    ):
        from bot.ai import ask_ai

        ask_ai(123, "hello")
        system = captured["msgs"][0]["content"]
        assert "grades" not in system


def test_generate_quiz_includes_grade_in_instruction():
    captured = {}
    with (
        patch("bot.ai.get_grade", return_value="1-4"),
        patch("bot.ai.generate", side_effect=lambda uid, msgs: captured.update(msgs=msgs) or "[]"),
    ):
        from bot.ai import generate_quiz

        generate_quiz(123, "notes")
        user_instruction = captured["msgs"][-1]["content"]
        assert "grades 1-4" in user_instruction


def test_expand_conspectus_injects_grade():
    captured = {}
    with (
        patch("bot.ai.get_grade", return_value="10-12"),
        patch("bot.ai.generate", side_effect=lambda uid, msgs: captured.update(msgs=msgs) or "deep"),
    ):
        from bot.ai import expand_conspectus

        expand_conspectus(123, "Topic", "old")
        system = captured["msgs"][0]["content"]
        assert "grades 10-12" in system


# ── handlers: /grade + callback ─────────────────────────────────────────────


def _call(data, user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


def make_message(user_id=123, chat_id=456):
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    return msg


def test_cmd_grade_shows_picker_with_keyboard():
    with (
        patch("bot.handlers.get_grade", return_value=None),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_grade

        cmd_grade(make_message())
        args, kwargs = mock_bot.send_message.call_args
        assert "Ընտրիր" in args[1]
        assert kwargs.get("reply_markup") is not None


def test_cmd_grade_shows_current_when_set():
    with (
        patch("bot.handlers.get_grade", return_value="5-9"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_grade

        cmd_grade(make_message())
        assert "5-9" in mock_bot.send_message.call_args[0][1]


def test_cb_grade_sets_grade():
    with (
        patch("bot.handlers.set_grade", return_value=True) as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cb_grade

        cb_grade(_call("grade:set:5-9"))
        mock_set.assert_called_once_with(123, "5-9")
        assert "5-9" in mock_bot.send_message.call_args[0][1]


def test_cb_grade_set_failure_message():
    with (
        patch("bot.handlers.set_grade", return_value=False),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cb_grade

        cb_grade(_call("grade:set:5-9"))
        assert "Չստացվեց" in mock_bot.send_message.call_args[0][1]


def test_cb_grade_clear():
    with (
        patch("bot.handlers.clear_grade") as mock_clear,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cb_grade

        cb_grade(_call("grade:clear"))
        mock_clear.assert_called_once_with(123)
        assert "Հանեցի" in mock_bot.send_message.call_args[0][1]
