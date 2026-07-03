import json
from unittest.mock import MagicMock, patch


def make_message(text="/challenge", user_id=123, chat_id=456):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.chat.type = "private"
    msg.reply_to_message = None
    return msg


def _dict_store():
    saved = {}
    s = MagicMock()
    s.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    s.get.side_effect = lambda k: saved.get(k)
    s.delete.side_effect = lambda k: saved.pop(k, None)
    return s, saved


# ── ai.generate_challenge ────────────────────────────────────────────────────
def test_generate_challenge_returns_text():
    with patch("bot.ai.generate", return_value="Ինչո՞ւ է երկինքը կապույտ։"):
        from bot.ai import generate_challenge

        assert generate_challenge(123) == "Ինչո՞ւ է երկինքը կապույտ։"


# ── bot.challenges state + scheduler logic ───────────────────────────────────
def test_set_and_clear_challenge_time():
    s, saved = _dict_store()
    with patch("bot.challenges.store", s):
        from bot.challenges import (
            clear_challenge_time,
            get_challenge_time,
            set_challenge_time,
        )

        assert set_challenge_time(7, "09:00") is True
        assert get_challenge_time(7) == "09:00"
        assert json.loads(saved["challenge:index"]) == {"7": "09:00"}
        clear_challenge_time(7)
        assert get_challenge_time(7) is None
        assert json.loads(saved["challenge:index"]) == {}


def test_run_due_challenges_sends_and_dedups():
    s, saved = _dict_store()
    saved["challenge:index"] = json.dumps({"7": "09:00", "8": "10:00"})
    mock_bot = MagicMock()
    with (
        patch("bot.challenges.store", s),
        patch("bot.challenges.bot", mock_bot),
        patch("bot.challenges.generate_challenge", return_value="Հարց օրվա"),
    ):
        from bot.challenges import run_due_challenges

        # Only user 7 is due at 09:00.
        assert run_due_challenges("09:00", "2026-07-03") == 1
        assert mock_bot.send_message.call_args[0][0] == 7
        assert "Հարց օրվա" in mock_bot.send_message.call_args[0][1]
        # Second run same day is de-duped.
        assert run_due_challenges("09:00", "2026-07-03") == 0


def test_run_due_challenges_stateless():
    with patch("bot.challenges.store", None):
        from bot.challenges import run_due_challenges

        assert run_due_challenges("09:00", "2026-07-03") == 0


# ── handlers: /challenge ─────────────────────────────────────────────────────
def test_cmd_challenge_no_arg_sends_now():
    with (
        patch("bot.handlers.generate_challenge", return_value="Հարց"),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_challenge

        cmd_challenge(make_message(text="/challenge"))
        assert "Հարց" in mock_bot.send_message.call_args[0][1]


def test_cmd_challenge_schedules_daily():
    with (
        patch("bot.handlers.set_challenge_time", return_value=True) as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_challenge

        cmd_challenge(make_message(text="/challenge 09:00"))
        mock_set.assert_called_once_with(123, "09:00")
        assert "09:00" in mock_bot.send_message.call_args[0][1]


def test_cmd_challenge_off_cancels():
    with (
        patch("bot.handlers.clear_challenge_time") as mock_clear,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_challenge

        cmd_challenge(make_message(text="/challenge off"))
        mock_clear.assert_called_once_with(123)
        assert "անջատված" in mock_bot.send_message.call_args[0][1]


def test_cmd_challenge_rejects_bad_time():
    with (
        patch("bot.handlers.set_challenge_time") as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_challenge

        cmd_challenge(make_message(text="/challenge later"))
        mock_set.assert_not_called()
        assert "Սխալ ձևաչափ" in mock_bot.send_message.call_args[0][1]
