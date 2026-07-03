from unittest.mock import MagicMock, patch


def make_message(text="/admin", user_id=123, chat_id=456, message_id=99):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.message_id = message_id
    msg.chat.type = "private"
    msg.reply_to_message = None
    return msg


def _dict_store():
    """A fake store supporting get/set/delete/incr/set_nx over a dict."""
    saved = {}

    def _set(k, v, ex=None):
        saved[k] = v

    def _incr(k):
        saved[k] = str(int(saved.get(k, "0")) + 1)
        return int(saved[k])

    def _set_nx(k, v, ex=None):
        if k in saved:
            return False
        saved[k] = v
        return True

    s = MagicMock()
    s.get.side_effect = lambda k: saved.get(k)
    s.set.side_effect = _set
    s.delete.side_effect = lambda k: saved.pop(k, None)
    s.incr.side_effect = _incr
    s.set_nx.side_effect = _set_nx
    return s, saved


# ── history: user tracking ───────────────────────────────────────────────────
def test_touch_user_indexes_unique_users():
    s, saved = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import _load_users_index, touch_user

        touch_user(7, now=1000)
        touch_user(7, now=2000)  # same user again — no duplicate
        touch_user(8, now=1500)
        idx = _load_users_index()
        assert sorted(idx) == ["7", "8"]
        assert saved["seen:7"] == "2000"  # last-seen updated


def test_touch_user_stateless_noop():
    with patch("bot.history.store", None):
        from bot.history import _load_users_index, touch_user

        touch_user(7)
        assert _load_users_index() == []


def test_incr_and_get_message_count():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import get_message_count, incr_messages

        assert get_message_count() == 0
        incr_messages()
        incr_messages()
        assert get_message_count() == 2


# ── history: aggregated admin stats ──────────────────────────────────────────
def test_get_admin_stats_counts_users_activity_and_conspectuses():
    s, saved = _dict_store()
    now = 1_000_000
    # In production bot.history.store and bot.stats.store are the same object
    # (both from bot.clients); patch both so the per-user conspectus sum works.
    with patch("bot.history.store", s), patch("bot.stats.store", s):
        from bot.history import incr_messages, touch_user

        touch_user(1, now=now - 100)  # active today + week
        touch_user(2, now=now - 2 * 86400)  # active week only
        touch_user(3, now=now - 10 * 86400)  # inactive
        incr_messages()
        incr_messages()
        incr_messages()

        # Per-user conspectus counters (bot/stats.py key format), summed.
        saved["stat:conspectus:1"] = "4"
        saved["stat:conspectus:2"] = "1"

        from bot.history import get_admin_stats

        stats = get_admin_stats(now=now)
        assert stats["total_users"] == 3
        assert stats["active_today"] == 1
        assert stats["active_week"] == 2
        assert stats["total_messages"] == 3
        assert stats["total_conspectuses"] == 5


# ── history: admin session ───────────────────────────────────────────────────
def test_admin_session_start_and_check():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import is_admin, start_admin_session

        assert is_admin(7) is False
        start_admin_session(7)
        assert is_admin(7) is True


# ── handlers: /admin flow ────────────────────────────────────────────────────
def test_cmd_admin_disabled_without_password():
    with (
        patch("bot.handlers.ADMIN_PASSWORD", ""),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_admin

        cmd_admin(make_message())
        assert "անջատված" in mock_bot.send_message.call_args[0][1]


def test_cmd_admin_prompts_for_password():
    with (
        patch("bot.handlers.ADMIN_PASSWORD", "s3cret"),
        patch("bot.handlers.is_admin", return_value=False),
        patch("bot.handlers.set_mode", return_value=True) as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_admin

        cmd_admin(make_message())
        mock_set.assert_called_once_with(123, "admin_login")
        assert "գաղտնաբառ" in mock_bot.send_message.call_args[0][1]


def test_cmd_admin_shows_stats_when_session_active():
    with (
        patch("bot.handlers.ADMIN_PASSWORD", "s3cret"),
        patch("bot.handlers.is_admin", return_value=True),
        patch("bot.handlers._show_admin_stats") as mock_show,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cmd_admin

        cmd_admin(make_message())
        mock_show.assert_called_once_with(456)


def test_admin_login_correct_password_opens_session_and_shows_stats():
    with (
        patch("bot.handlers.ADMIN_PASSWORD", "s3cret"),
        patch("bot.handlers.clear_mode"),
        patch("bot.handlers.start_admin_session") as mock_start,
        patch("bot.handlers._show_admin_stats") as mock_show,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _handle_admin_login

        _handle_admin_login(make_message(text="s3cret"), "s3cret")
        mock_start.assert_called_once_with(123)
        mock_show.assert_called_once_with(456)
        # The password message is deleted for security.
        mock_bot.delete_message.assert_called_once_with(456, 99)


def test_admin_login_wrong_password_rejected():
    with (
        patch("bot.handlers.ADMIN_PASSWORD", "s3cret"),
        patch("bot.handlers.clear_mode"),
        patch("bot.handlers.start_admin_session") as mock_start,
        patch("bot.handlers._show_admin_stats") as mock_show,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _handle_admin_login

        _handle_admin_login(make_message(text="wrong"), "wrong")
        mock_start.assert_not_called()
        mock_show.assert_not_called()
        assert "Սխալ գաղտնաբառ" in mock_bot.send_message.call_args[0][1]


def test_password_ok_is_false_when_unset():
    with patch("bot.handlers.ADMIN_PASSWORD", ""):
        from bot.handlers import _password_ok

        assert _password_ok("anything") is False


def test_admin_login_routed_via_pending_mode():
    with (
        patch("bot.handlers.should_respond", return_value=True),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.BOT_INFO", MagicMock(username="testbot")),
        patch("bot.handlers.touch_user"),
        patch("bot.handlers.incr_messages"),
        patch("bot.handlers.get_mode", return_value={"mode": "admin_login"}),
        patch("bot.handlers._handle_admin_login") as mock_login,
        patch("bot.handlers.ask_ai") as mock_ask,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import handle_message

        handle_message(make_message(text="s3cret"))
        mock_login.assert_called_once()
        mock_ask.assert_not_called()  # not treated as a conspectus


def test_show_admin_stats_formats_all_fields():
    stats = {
        "total_users": 12,
        "active_today": 3,
        "active_week": 8,
        "total_messages": 140,
        "total_conspectuses": 30,
    }
    with (
        patch("bot.handlers.get_admin_stats", return_value=stats),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _show_admin_stats

        _show_admin_stats(456)
        sent = mock_bot.send_message.call_args[0][1]
        for value in ("12", "3", "8", "140", "30"):
            assert value in sent
