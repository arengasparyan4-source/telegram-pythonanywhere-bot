from unittest.mock import MagicMock, patch


def make_message(text="/leaderboard", user_id=1, chat_id=-100):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.chat.type = "supergroup"
    msg.reply_to_message = None
    return msg


def _dict_store():
    saved = {}
    s = MagicMock()
    s.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    s.get.side_effect = lambda k: saved.get(k)
    s.delete.side_effect = lambda k: saved.pop(k, None)
    return s, saved


# ── history: per-chat scoreboard ─────────────────────────────────────────────
def test_add_score_accumulates_and_ranks():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import add_score, get_leaderboard

        add_score(-100, 1, "Անի", 1)
        add_score(-100, 1, "Անի", 2)  # accumulates → 3
        add_score(-100, 2, "Բաբկեն", 1)
        board = get_leaderboard(-100)
        assert board == [("Անի", 3), ("Բաբկեն", 1)]  # ranked desc


def test_scores_are_scoped_per_chat():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import add_score, get_leaderboard

        add_score(-100, 1, "Անի", 5)   # group A
        add_score(-200, 1, "Անի", 1)   # group B — separate board
        assert get_leaderboard(-100) == [("Անի", 5)]
        assert get_leaderboard(-200) == [("Անի", 1)]


def test_add_score_stateless_and_nonpositive():
    with patch("bot.history.store", None):
        from bot.history import add_score, get_leaderboard

        add_score(-100, 1, "Անի", 1)
        assert get_leaderboard(-100) == []
    with patch("bot.history.store", MagicMock()):
        from bot.history import add_score

        add_score(-100, 1, "Անի", 0)  # no-op, must not raise


# ── handlers: award on correct answers ───────────────────────────────────────
def test_correct_quiz_answer_awards_point():
    state = {
        "questions": [{"q": "q", "options": ["a", "b"], "correct": 0, "explanation": ""}],
        "idx": 0,
        "score": 0,
        "topic": "t",
    }
    call = MagicMock()
    call.data = "quizans:0:0"
    call.from_user = MagicMock(id=1, first_name="Անի", username=None)
    call.message.chat.id = -100
    with (
        patch("bot.handlers.get_quiz", return_value=state),
        patch("bot.handlers.update_quiz"),
        patch("bot.handlers.record_weak_answer"),
        patch("bot.handlers._send_quiz_question"),
        patch("bot.handlers.add_score") as mock_add,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cb_quiz

        cb_quiz(call)
        mock_add.assert_called_once_with(-100, 1, "Անի", 1)


def test_wrong_quiz_answer_no_point():
    state = {
        "questions": [{"q": "q", "options": ["a", "b"], "correct": 0, "explanation": ""}],
        "idx": 0,
        "score": 0,
        "topic": "t",
    }
    call = MagicMock()
    call.data = "quizans:0:1"  # wrong
    call.from_user = MagicMock(id=1, first_name="Անի", username=None)
    call.message.chat.id = -100
    with (
        patch("bot.handlers.get_quiz", return_value=state),
        patch("bot.handlers.update_quiz"),
        patch("bot.handlers.record_weak_answer"),
        patch("bot.handlers._send_quiz_question"),
        patch("bot.handlers.add_score") as mock_add,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cb_quiz

        cb_quiz(call)
        mock_add.assert_not_called()


# ── handlers: /leaderboard display ───────────────────────────────────────────
def test_leaderboard_empty():
    with (
        patch("bot.handlers.get_leaderboard", return_value=[]),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_leaderboard

        cmd_leaderboard(make_message())
        assert "Դեռ միավորներ չկան" in mock_bot.send_message.call_args[0][1]


def test_leaderboard_ranked_with_medals():
    board = [("Անի", 10), ("Բաբկեն", 7), ("Գագիկ", 3), ("Դավիթ", 1)]
    with (
        patch("bot.handlers.get_leaderboard", return_value=board),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_leaderboard

        cmd_leaderboard(make_message())
        sent = mock_bot.send_message.call_args[0][1]
        assert "🥇" in sent and "🥈" in sent and "🥉" in sent
        assert "Անի" in sent and "10" in sent
        assert "4. <b>Դավիթ</b>" in sent  # 4th place uses a number, not a medal
