from unittest.mock import MagicMock, patch


def make_message(text="/weakspots", user_id=123, chat_id=456):
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


# ── history: weak-spot tracking ──────────────────────────────────────────────
def test_wrong_answer_adds_weakspot():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import get_weakspots, record_weak_answer

        record_weak_answer(7, "Ֆիզիկա", correct=False)
        assert get_weakspots(7) == {"Ֆիզիկա": 1}


def test_correct_answers_clear_weakspot_when_mastered():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import get_weakspots, list_weakspots, record_weak_answer

        # Missed twice → 2 strikes.
        record_weak_answer(7, "Քիմիա", correct=False)
        record_weak_answer(7, "Քիմիա", correct=False)
        assert get_weakspots(7) == {"Քիմիա": 2}
        # One correct → still weak (1 strike left).
        record_weak_answer(7, "Քիմիա", correct=True)
        assert list_weakspots(7) == ["Քիմիա"]
        # Second correct → cleared.
        record_weak_answer(7, "Քիմիա", correct=True)
        assert list_weakspots(7) == []


def test_correct_answer_on_unknown_topic_is_noop():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import get_weakspots, record_weak_answer

        record_weak_answer(7, "Նոր թեմա", correct=True)
        assert get_weakspots(7) == {}


def test_record_weak_answer_blank_topic_and_stateless():
    with patch("bot.history.store", MagicMock()):
        from bot.history import get_weakspots, record_weak_answer

        record_weak_answer(7, "   ", correct=False)
        assert get_weakspots(7) == {}
    with patch("bot.history.store", None):
        from bot.history import record_weak_answer

        record_weak_answer(7, "x", correct=False)  # no crash


def test_list_weakspots_sorted_by_strikes():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import list_weakspots, record_weak_answer

        record_weak_answer(7, "A", correct=False)
        record_weak_answer(7, "B", correct=False)
        record_weak_answer(7, "B", correct=False)
        assert list_weakspots(7) == ["B", "A"]  # B has more strikes


# ── quiz integration: wrong answers feed weak spots ──────────────────────────
def test_quiz_wrong_answer_records_weakspot():
    state = {
        "questions": [{"q": "q1", "options": ["a", "b"], "correct": 0, "explanation": "e"}],
        "idx": 0,
        "score": 0,
        "topic": "Ֆիզիկա",
    }
    with (
        patch("bot.handlers.get_quiz", return_value=state),
        patch("bot.handlers.update_quiz"),
        patch("bot.handlers.record_weak_answer") as mock_weak,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _handle_quiz_answer

        _handle_quiz_answer(456, 123, "quizans:0:1")  # wrong
        mock_weak.assert_called_once_with(123, "Ֆիզիկա", False)


# ── handlers: /weakspots ─────────────────────────────────────────────────────
def test_cmd_weakspots_empty():
    with (
        patch("bot.handlers.list_weakspots", return_value=[]),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_weakspots

        cmd_weakspots(make_message())
        assert "թույլ կողմեր չկան" in mock_bot.send_message.call_args[0][1]


def test_cmd_weakspots_lists_topics():
    with (
        patch("bot.handlers.list_weakspots", return_value=["Ֆիզիկա", "Քիմիա"]),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_weakspots

        cmd_weakspots(make_message())
        assert mock_bot.send_message.call_args.kwargs.get("reply_markup") is not None


def test_cb_weakspots_regenerates_topic():
    with (
        patch("bot.handlers.list_weakspots", return_value=["Ֆիզիկա", "Քիմիա"]),
        patch("bot.handlers._regenerate_from_topic") as mock_regen,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cb_weakspots

        call = _call("weak:show:1")
        cb_weakspots(call)
        mock_regen.assert_called_once_with(456, 123, "Քիմիա", call.message)
