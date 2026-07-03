import json
from unittest.mock import MagicMock, patch


def make_message(text="hello", user_id=123, chat_id=456):
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


# ── bot.games state ──────────────────────────────────────────────────────────
def test_game_state_roundtrip():
    s, _ = _dict_store()
    with patch("bot.games.store", s):
        from bot.games import clear_game, get_game, save_game, update_game

        assert save_game(7, "tf", [{"s": "x", "ok": True, "why": "w"}]) is True
        state = get_game(7)
        assert state["kind"] == "tf" and state["idx"] == 0 and state["score"] == 0
        state["score"] = 2
        update_game(7, state)
        assert get_game(7)["score"] == 2
        clear_game(7)
        assert get_game(7) is None


def test_game_stateless():
    with patch("bot.games.store", None):
        from bot.games import get_game, save_game

        assert save_game(7, "tf", []) is False
        assert get_game(7) is None


# ── ai parsers/generators ────────────────────────────────────────────────────
def test_generate_truefalse_parses_json():
    payload = json.dumps(
        [
            {"s": "Ջուրը թաց է", "ok": True, "why": "որովհետև"},
            {"s": "Կրակը սառն է", "ok": False, "why": "ոչ"},
        ]
    )
    with patch("bot.ai.generate", return_value=payload):
        from bot.ai import generate_truefalse

        rounds = generate_truefalse(123, "notes", 5)
        assert len(rounds) == 2
        assert rounds[0]["ok"] is True and rounds[1]["ok"] is False


def test_generate_truefalse_rejects_bad_shape():
    with patch("bot.ai.generate", return_value='[{"s": "x"}]'):
        from bot.ai import generate_truefalse

        assert generate_truefalse(123, "notes", 5) == []


def test_generate_word_game_parses_json():
    payload = json.dumps([{"word": "ջուր", "hint": "թաց է"}])
    with patch("bot.ai.generate", return_value=payload):
        from bot.ai import generate_word_game

        rounds = generate_word_game(123, "notes", 5)
        assert rounds == [{"word": "ջուր", "hint": "թաց է"}]


# ── handlers: /game menu and flow ────────────────────────────────────────────
def test_cmd_game_shows_menu():
    with (
        patch("bot.handlers.store", MagicMock()),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_game

        cmd_game(make_message(text="/game"))
        assert "Խաղ" in mock_bot.send_message.call_args[0][1]
        assert mock_bot.send_message.call_args.kwargs.get("reply_markup") is not None


def test_cmd_game_requires_store():
    with (
        patch("bot.handlers.store", None),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_game

        cmd_game(make_message(text="/game"))
        assert "հիշողություն" in mock_bot.send_message.call_args[0][1]


def test_cb_game_uses_last_conspectus():
    with (
        patch(
            "bot.handlers.get_last_conspectus",
            return_value={"topic": "t", "text": "notes"},
        ),
        patch("bot.handlers._start_game") as mock_start,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cb_game

        cb_game(_call("game:tf"))
        mock_start.assert_called_once_with(456, 123, "tf", "notes")


def test_cb_game_asks_topic_without_conspectus():
    with (
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.set_mode", return_value=True) as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cb_game

        cb_game(_call("game:word"))
        mock_set.assert_called_once_with(123, "game_topic", {"kind": "word"})
        assert "թեմա" in mock_bot.send_message.call_args[0][1].lower()


def test_start_game_generates_and_sends_first_round():
    rounds = [{"s": "x", "ok": True, "why": "w"}]
    with (
        patch("bot.handlers.generate_truefalse", return_value=rounds),
        patch("bot.handlers.save_game", return_value=True),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.get_game", return_value={"kind": "tf", "rounds": rounds, "idx": 0, "score": 0}),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _start_game

        _start_game(456, 123, "tf", "notes")
        # Intro + first question sent.
        assert mock_bot.send_message.call_count >= 2


def test_tf_answer_scores_correct_and_advances():
    state = {"kind": "tf", "rounds": [{"s": "x", "ok": True, "why": "w"}], "idx": 0, "score": 0}
    with (
        patch("bot.handlers.get_game", return_value=state),
        patch("bot.handlers.update_game") as mock_update,
        patch("bot.handlers._send_game_round") as mock_next,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _handle_tf_answer

        _handle_tf_answer(456, 123, "tfans:0:1")  # said "true", correct
        assert state["score"] == 1 and state["idx"] == 1
        assert "Ճիշտ" in mock_bot.send_message.call_args[0][1]
        mock_update.assert_called_once()
        mock_next.assert_called_once_with(456, 123)


def test_word_guess_correct():
    state = {"kind": "word", "rounds": [{"word": "Ջուր", "hint": "թաց"}], "idx": 0, "score": 0}
    with (
        patch("bot.handlers.get_game", return_value=state),
        patch("bot.handlers.update_game"),
        patch("bot.handlers.clear_mode"),
        patch("bot.handlers._send_game_round"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _handle_word_guess

        # Case/space-insensitive match.
        assert _handle_word_guess(make_message(text="  ջուր "), "  ջուր ") is True
        assert state["score"] == 1
        assert "Ճիշտ" in mock_bot.send_message.call_args[0][1]


def test_word_guess_wrong_reveals_answer():
    state = {"kind": "word", "rounds": [{"word": "ջուր", "hint": "թաց"}], "idx": 0, "score": 0}
    with (
        patch("bot.handlers.get_game", return_value=state),
        patch("bot.handlers.update_game"),
        patch("bot.handlers.clear_mode"),
        patch("bot.handlers._send_game_round"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _handle_word_guess

        _handle_word_guess(make_message(text="կրակ"), "կրակ")
        assert state["score"] == 0
        assert "ջուր" in mock_bot.send_message.call_args[0][1]


def test_finish_game_reports_score():
    state = {"kind": "tf", "rounds": [1, 2, 3], "idx": 3, "score": 2}
    with (
        patch("bot.handlers.clear_game") as mock_clear,
        patch("bot.handlers.clear_mode"),
        patch("bot.handlers.record_activity"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _finish_game

        _finish_game(456, 123, state)
        mock_clear.assert_called_once_with(123)
        assert "2/3" in mock_bot.send_message.call_args[0][1]
