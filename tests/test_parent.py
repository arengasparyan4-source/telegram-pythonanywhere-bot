import json
from unittest.mock import MagicMock, patch


def _dict_store():
    saved = {}
    s = MagicMock()
    s.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    s.get.side_effect = lambda k: saved.get(k)
    return s, saved


# ── bot/parent.py ────────────────────────────────────────────────────────────
def test_link_child_and_get_children():
    s, saved = _dict_store()
    with patch("bot.parent.store", s):
        from bot.parent import get_children, link_child

        assert link_child(1, 100) is True
        assert link_child(1, 200) is True
        assert link_child(1, 100) is True  # idempotent
        assert sorted(get_children(1)) == [100, 200]
        assert json.loads(saved["parent:1"]) == [100, 200]


def test_link_child_stateless():
    with patch("bot.parent.store", None):
        from bot.parent import get_children, link_child

        assert link_child(1, 100) is False
        assert get_children(1) == []


def test_build_report_includes_all_sections():
    with (
        patch("bot.parent.get_stats", return_value={"topics": 12, "conspectuses": 8, "quizzes": 3, "flashcards": 5}),
        patch("bot.parent.days_active_last_n", return_value=4),
        patch("bot.parent.get_badges", return_value=["🥇 Առաջին կոնսպեկտ"]),
    ):
        from bot.parent import build_report

        report = build_report(100)
        assert "ID: 100" in report
        assert "📚 Ուսումնասիրած թեմաներ — 12" in report
        assert "📝 Կոնսպեկտներ — 8" in report
        assert "✅ Անցած վիկտորինաներ — 3" in report
        assert "🧠 Flashcard սեսիաներ — 5" in report
        assert "📅 Ակտիվ օրեր (վերջին 7 օր) — 4" in report
        assert "🥇 Առաջին կոնսպեկտ" in report


def test_build_report_no_badges():
    with (
        patch("bot.parent.get_stats", return_value={"topics": 0, "conspectuses": 0, "quizzes": 0, "flashcards": 0}),
        patch("bot.parent.days_active_last_n", return_value=0),
        patch("bot.parent.get_badges", return_value=[]),
    ):
        from bot.parent import build_report

        assert "դեռ չկան" in build_report(100)


# ── handlers: /parent ────────────────────────────────────────────────────────
def _msg(text="/parent", user_id=123, chat_id=456):
    m = MagicMock()
    m.text = text
    m.from_user.id = user_id
    m.chat.id = chat_id
    return m


def test_cmd_parent_usage_when_no_arg():
    with patch("bot.handlers.bot") as mock_bot:
        from bot.handlers import cmd_parent

        cmd_parent(_msg(text="/parent"))
        assert "երեխայի ID" in mock_bot.send_message.call_args[0][1]


def test_cmd_parent_rejects_non_numeric():
    with patch("bot.handlers.bot") as mock_bot:
        from bot.handlers import cmd_parent

        cmd_parent(_msg(text="/parent abc"))
        assert "թիվ" in mock_bot.send_message.call_args[0][1]


def test_cmd_parent_stateless():
    with (
        patch("bot.handlers.store", None),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_parent

        cmd_parent(_msg(text="/parent 999"))
        assert "հիշողություն" in mock_bot.send_message.call_args[0][1]


def test_cmd_parent_links_and_sends_report():
    with (
        patch("bot.handlers.store", MagicMock()),
        patch("bot.handlers.link_child") as mock_link,
        patch("bot.handlers.build_report", return_value="REPORT BODY") as mock_report,
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cmd_parent

        cmd_parent(_msg(text="/parent 999", user_id=123))
        mock_link.assert_called_once_with(123, 999)
        mock_report.assert_called_once_with(999)
        assert mock_send.call_args[0][1] == "REPORT BODY"
