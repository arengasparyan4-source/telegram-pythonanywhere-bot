from unittest.mock import MagicMock, patch

QS = [
    {"q": "q1", "options": ["a", "b"], "correct": 0, "explanation": ""},
    {"q": "q2", "options": ["c", "d"], "correct": 1, "explanation": ""},
]


def user(uid, name="U"):
    u = MagicMock()
    u.id = uid
    u.first_name = name
    u.username = None
    return u


def call_with(data, uid, name="U", chat_id=-100):
    c = MagicMock()
    c.data = data
    c.from_user = user(uid, name)
    c.message.chat.id = chat_id
    return c


def message_with(text, uid, name="U", chat_id=-100):
    m = MagicMock()
    m.text = text
    m.from_user = user(uid, name)
    m.chat.id = chat_id
    m.chat.type = "supergroup"
    m.reply_to_message = None
    return m


def _dict_store():
    saved = {}
    s = MagicMock()
    s.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    s.get.side_effect = lambda k: saved.get(k)
    s.delete.side_effect = lambda k: saved.pop(k, None)
    return s, saved


# ── history: duel state persistence ──────────────────────────────────────────
def test_duel_state_roundtrip():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import clear_duel, get_duel, save_duel

        assert get_duel(-100) is None
        assert save_duel(-100, {"status": "waiting"}) is True
        assert get_duel(-100)["status"] == "waiting"
        clear_duel(-100)
        assert get_duel(-100) is None


# ── start + join lifecycle ───────────────────────────────────────────────────
def test_start_duel_creates_waiting_state_with_join_button():
    saved = {}
    with (
        patch("bot.handlers.get_duel", return_value=None),
        patch("bot.handlers.generate_quiz", return_value=QS),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.save_duel", side_effect=lambda cid, st: saved.update({cid: st}) or True),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _start_duel

        _start_duel(-100, user(1, "Անի"), "Ֆիզիկա", "Ֆիզիկա")
        st = saved[-100]
        assert st["status"] == "waiting"
        assert list(st["players"].keys()) == ["1"]
        assert mock_bot.send_message.call_args.kwargs.get("reply_markup") is not None


def test_start_duel_refuses_when_one_active():
    with (
        patch("bot.handlers.get_duel", return_value={"status": "active"}),
        patch("bot.handlers.generate_quiz") as mock_gen,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _start_duel

        _start_duel(-100, user(1), "t", "t")
        mock_gen.assert_not_called()
        assert "արդեն ակտիվ" in mock_bot.send_message.call_args[0][1]


def test_join_activates_and_sends_first_question():
    state = {
        "topic": "t", "questions": QS, "status": "waiting", "cur": 0,
        "round_ts": 0, "starter": 1,
        "players": {"1": {"name": "Անի", "score": 0, "answered": [], "time": 0}},
    }
    saved = {}
    with (
        patch("bot.handlers.get_duel", return_value=state),
        patch("bot.handlers.save_duel", side_effect=lambda cid, st: saved.update({cid: st}) or True),
        patch("bot.handlers._send_duel_question") as mock_send_q,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _join_duel

        _join_duel(-100, user(2, "Բաբկեն"))
        assert state["status"] == "active"
        assert set(state["players"].keys()) == {"1", "2"}
        mock_send_q.assert_called_once()


def test_join_rejects_third_player():
    state = {
        "status": "waiting", "cur": 0, "questions": QS, "round_ts": 0,
        "players": {
            "1": {"name": "A", "score": 0, "answered": [], "time": 0},
            "2": {"name": "B", "score": 0, "answered": [], "time": 0},
        },
    }
    with (
        patch("bot.handlers.get_duel", return_value=state),
        patch("bot.handlers.save_duel") as mock_save,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _join_duel

        _join_duel(-100, user(3))
        mock_save.assert_not_called()
        assert "լրացված" in mock_bot.send_message.call_args[0][1]


# ── synchronized rounds: advance only when BOTH answered ─────────────────────
def _active_state():
    return {
        "topic": "t", "questions": QS, "status": "active", "cur": 0,
        "round_ts": 0, "starter": 1,
        "players": {
            "1": {"name": "Անի", "score": 0, "answered": [], "time": 0},
            "2": {"name": "Բաբկեն", "score": 0, "answered": [], "time": 0},
        },
    }


def test_round_waits_for_both_players():
    state = _active_state()
    with (
        patch("bot.handlers.get_duel", return_value=state),
        patch("bot.handlers.save_duel", return_value=True),
        patch("bot.handlers._send_duel_question") as mock_next,
        patch("bot.handlers._finish_duel") as mock_finish,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _handle_duel_answer

        # Player 1 answers q0 correctly → should NOT advance yet.
        _handle_duel_answer(-100, user(1, "Անի"), "duelans:0:0")
        assert state["players"]["1"]["score"] == 1
        assert state["cur"] == 0
        mock_next.assert_not_called()
        mock_finish.assert_not_called()


def test_round_advances_when_both_answered():
    state = _active_state()
    with (
        patch("bot.handlers.get_duel", return_value=state),
        patch("bot.handlers.save_duel", return_value=True),
        patch("bot.handlers._send_duel_question") as mock_next,
        patch("bot.handlers._finish_duel") as mock_finish,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _handle_duel_answer

        _handle_duel_answer(-100, user(1), "duelans:0:0")  # correct
        _handle_duel_answer(-100, user(2), "duelans:0:1")  # wrong
        # Both answered q0 → advance to q1 (not finished, 2 questions).
        assert state["cur"] == 1
        mock_next.assert_called_once()
        mock_finish.assert_not_called()


def test_double_answer_by_same_player_ignored():
    state = _active_state()
    with (
        patch("bot.handlers.get_duel", return_value=state),
        patch("bot.handlers.save_duel", return_value=True),
        patch("bot.handlers._send_duel_question"),
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _handle_duel_answer

        _handle_duel_answer(-100, user(1), "duelans:0:0")  # correct
        _handle_duel_answer(-100, user(1), "duelans:0:1")  # same player again
        assert state["players"]["1"]["score"] == 1  # not double-counted
        assert state["cur"] == 0  # opponent still hasn't answered


def test_non_participant_answer_ignored():
    state = _active_state()
    with (
        patch("bot.handlers.get_duel", return_value=state),
        patch("bot.handlers.save_duel") as mock_save,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _handle_duel_answer

        _handle_duel_answer(-100, user(99, "Stranger"), "duelans:0:0")
        # No score change, no state save for an outsider.
        assert all(p["score"] == 0 for p in state["players"].values())
        mock_save.assert_not_called()


# ── finishing: winner, tie, dropout ──────────────────────────────────────────
def test_finish_duel_announces_winner_and_awards_points():
    state = {
        "players": {
            "1": {"name": "Անի", "score": 3, "time": 10},
            "2": {"name": "Բաբկեն", "score": 1, "time": 8},
        }
    }
    with (
        patch("bot.handlers.clear_duel") as mock_clear,
        patch("bot.handlers.add_score") as mock_add,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _finish_duel

        _finish_duel(-100, state)
        sent = mock_bot.send_message.call_args[0][1]
        assert "Հաղթող" in sent and "Անի" in sent
        mock_clear.assert_called_once_with(-100)
        mock_add.assert_called_once_with(-100, 1, "Անի", 3)  # winner rewarded


def test_finish_duel_tie_no_winner_points():
    state = {
        "players": {
            "1": {"name": "Անի", "score": 2, "time": 5},
            "2": {"name": "Բաբկեն", "score": 2, "time": 9},
        }
    }
    with (
        patch("bot.handlers.clear_duel"),
        patch("bot.handlers.add_score") as mock_add,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _finish_duel

        _finish_duel(-100, state)
        assert "Ոչ-ոքի" in mock_bot.send_message.call_args[0][1]
        mock_add.assert_not_called()


def test_endduel_active_settles_on_current_scores():
    state = {"status": "active", "players": {"1": {"name": "A", "score": 1, "time": 0}}}
    with (
        patch("bot.handlers.get_duel", return_value=state),
        patch("bot.handlers._finish_duel") as mock_finish,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cmd_endduel

        cmd_endduel(message_with("/endduel", 1))
        mock_finish.assert_called_once_with(-100, state)


def test_endduel_waiting_cancels():
    state = {"status": "waiting", "players": {"1": {}}}
    with (
        patch("bot.handlers.get_duel", return_value=state),
        patch("bot.handlers.clear_duel") as mock_clear,
        patch("bot.handlers._finish_duel") as mock_finish,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_endduel

        cmd_endduel(message_with("/endduel", 1))
        mock_clear.assert_called_once_with(-100)
        mock_finish.assert_not_called()
        assert "չեղարկվեց" in mock_bot.send_message.call_args[0][1]


def test_cb_duel_routes_join_and_answer():
    with (
        patch("bot.handlers._join_duel") as mock_join,
        patch("bot.handlers._handle_duel_answer") as mock_ans,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cb_duel

        cb_duel(call_with("duel:join", 2))
        mock_join.assert_called_once()
        cb_duel(call_with("duelans:0:1", 2))
        mock_ans.assert_called_once()
