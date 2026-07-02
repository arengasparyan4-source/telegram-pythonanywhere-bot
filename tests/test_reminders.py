import json
from unittest.mock import MagicMock, patch


def _dict_store():
    """A MagicMock store backed by a real dict for get/set/delete."""
    saved = {}
    s = MagicMock()
    s.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    s.get.side_effect = lambda k: saved.get(k)
    s.delete.side_effect = lambda k: saved.pop(k, None)
    return s, saved


# ── normalize_time ───────────────────────────────────────────────────────────
def test_normalize_time_valid_and_padding():
    from bot.reminders import normalize_time

    assert normalize_time("18:00") == "18:00"
    assert normalize_time("9:05") == "09:05"
    assert normalize_time("23:59") == "23:59"
    assert normalize_time(" 7:30 ") == "07:30"


def test_normalize_time_rejects_bad_input():
    from bot.reminders import normalize_time

    for bad in ("", "25:00", "12:60", "abc", "1800", "12", "12:5"):
        assert normalize_time(bad) is None


# ── set / get / clear + index ────────────────────────────────────────────────
def test_set_get_clear_reminder_maintains_index():
    s, saved = _dict_store()
    with patch("bot.reminders.store", s):
        from bot.reminders import clear_reminder, get_reminder, set_reminder

        assert set_reminder(7, "18:00") is True
        assert get_reminder(7) == "18:00"
        assert json.loads(saved["remind:index"]) == {"7": "18:00"}

        clear_reminder(7)
        assert get_reminder(7) is None
        assert json.loads(saved["remind:index"]) == {}


def test_reminder_stateless_mode():
    with patch("bot.reminders.store", None):
        from bot.reminders import get_reminder, set_reminder

        assert set_reminder(7, "18:00") is False
        assert get_reminder(7) is None


# ── run_due_reminders ────────────────────────────────────────────────────────
def test_run_due_reminders_sends_to_due_user_only():
    s, saved = _dict_store()
    saved["remind:index"] = json.dumps({"7": "18:00", "8": "09:00"})
    mock_bot = MagicMock()
    with (
        patch("bot.reminders.store", s),
        patch("bot.reminders.bot", mock_bot),
        patch("bot.reminders.get_last_conspectus", return_value={"topic": "t", "text": "BODY"}),
    ):
        from bot.reminders import run_due_reminders

        sent = run_due_reminders("18:00", "2026-07-02")
        assert sent == 1
        # Only user 7 (18:00) got a message, containing the repeat header + body.
        assert mock_bot.send_message.call_count == 1
        chat_id, text = mock_bot.send_message.call_args[0][0], mock_bot.send_message.call_args[0][1]
        assert chat_id == 7
        assert "🔁 Կրկնենք երեկվա թեման:" in text and "BODY" in text
        # De-dup marker recorded.
        assert saved["remind:sent:7"] == "2026-07-02"


def test_run_due_reminders_dedups_same_day():
    s, saved = _dict_store()
    saved["remind:index"] = json.dumps({"7": "18:00"})
    saved["remind:sent:7"] = "2026-07-02"
    mock_bot = MagicMock()
    with (
        patch("bot.reminders.store", s),
        patch("bot.reminders.bot", mock_bot),
        patch("bot.reminders.get_last_conspectus", return_value={"topic": "t", "text": "B"}),
    ):
        from bot.reminders import run_due_reminders

        assert run_due_reminders("18:00", "2026-07-02") == 0
        mock_bot.send_message.assert_not_called()


def test_run_due_reminders_skips_user_without_conspectus():
    s, saved = _dict_store()
    saved["remind:index"] = json.dumps({"7": "18:00"})
    mock_bot = MagicMock()
    with (
        patch("bot.reminders.store", s),
        patch("bot.reminders.bot", mock_bot),
        patch("bot.reminders.get_last_conspectus", return_value=None),
    ):
        from bot.reminders import run_due_reminders

        assert run_due_reminders("18:00", "2026-07-02") == 0
        mock_bot.send_message.assert_not_called()


# ── scheduler._tick ──────────────────────────────────────────────────────────
def test_scheduler_tick_calls_run_due_reminders():
    with patch("bot.reminders.run_due_reminders", return_value=0) as mock_run:
        from bot.scheduler import _tick

        _tick()
        mock_run.assert_called_once()
        # Args are (HH:MM, YYYY-MM-DD) strings.
        hhmm, day = mock_run.call_args[0]
        assert len(hhmm) == 5 and hhmm[2] == ":"
        assert len(day) == 10 and day[4] == "-"


# ── handlers: /repeat + /remind ──────────────────────────────────────────────
def _msg(text="/remind", user_id=123, chat_id=456):
    m = MagicMock()
    m.text = text
    m.from_user.id = user_id
    m.chat.id = chat_id
    return m


def test_cmd_repeat_without_conspectus_prompts():
    with (
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_repeat

        cmd_repeat(_msg(text="/repeat"))
        assert "չկա" in mock_bot.send_message.call_args[0][1]


def test_cmd_repeat_resends_with_header():
    with (
        patch("bot.handlers.get_last_conspectus", return_value={"topic": "t", "text": "BODY"}),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cmd_repeat

        cmd_repeat(_msg(text="/repeat"))
        text = mock_send.call_args[0][1]
        assert text.startswith("🔁 Կրկնենք երեկվա թեման:") and "BODY" in text


def test_cmd_remind_sets_time():
    with (
        patch("bot.handlers.set_reminder", return_value=True) as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_remind

        cmd_remind(_msg(text="/remind 18:00"))
        mock_set.assert_called_once_with(123, "18:00")
        assert "18:00" in mock_bot.send_message.call_args[0][1]


def test_cmd_remind_off_clears():
    with (
        patch("bot.handlers.clear_reminder") as mock_clear,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_remind

        cmd_remind(_msg(text="/remind off"))
        mock_clear.assert_called_once_with(123)
        assert "անջատված" in mock_bot.send_message.call_args[0][1]


def test_cmd_remind_rejects_bad_format():
    with (
        patch("bot.handlers.set_reminder") as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_remind

        cmd_remind(_msg(text="/remind 99:99"))
        mock_set.assert_not_called()
        assert "Սխալ ձևաչափ" in mock_bot.send_message.call_args[0][1]


def test_cmd_remind_no_arg_shows_current():
    with (
        patch("bot.handlers.get_reminder", return_value="18:00"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_remind

        cmd_remind(_msg(text="/remind"))
        assert "18:00" in mock_bot.send_message.call_args[0][1]
