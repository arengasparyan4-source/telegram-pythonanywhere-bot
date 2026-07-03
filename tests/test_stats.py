from unittest.mock import MagicMock, patch


# ── bot/stats.py module ──────────────────────────────────────────────────────
def test_get_stats_stateless_returns_zeros():
    with patch("bot.stats.store", None):
        from bot.stats import get_stats

        assert get_stats(7) == {
            "topics": 0,
            "conspectuses": 0,
            "quizzes": 0,
            "flashcards": 0,
        }


def test_incr_uses_store_incr_with_right_keys():
    fake_store = MagicMock()
    with patch("bot.stats.store", fake_store):
        from bot.stats import (
            incr_conspectuses,
            incr_flashcards,
            incr_quizzes,
            incr_topics,
        )

        incr_topics(7)
        incr_conspectuses(7)
        incr_quizzes(7)
        incr_flashcards(7)
        keys = [c[0][0] for c in fake_store.incr.call_args_list]
        assert keys == [
            "stat:topics:7",
            "stat:conspectus:7",
            "stat:quiz:7",
            "stat:cards:7",
        ]


def test_get_stats_reads_counters():
    fake_store = MagicMock()
    values = {
        "stat:topics:7": "12",
        "stat:conspectus:7": "8",
        "stat:quiz:7": "3",
        "stat:cards:7": "5",
    }
    fake_store.get.side_effect = lambda k: values.get(k)
    with patch("bot.stats.store", fake_store):
        from bot.stats import get_stats

        s = get_stats(7)
        assert s == {"topics": 12, "conspectuses": 8, "quizzes": 3, "flashcards": 5}


def test_incr_stateless_is_noop():
    with patch("bot.stats.store", None):
        from bot.stats import incr_topics

        incr_topics(7)  # must not raise


# ── handlers: /stats command + increments ────────────────────────────────────
def _msg(user_id=123, chat_id=456):
    m = MagicMock()
    m.from_user.id = user_id
    m.chat.id = chat_id
    return m


def test_cmd_stats_formats_armenian_summary():
    with (
        patch(
            "bot.handlers.get_stats",
            return_value={"topics": 12, "conspectuses": 8, "quizzes": 3, "flashcards": 5},
        ),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_stats

        cmd_stats(_msg())
        sent = mock_bot.send_message.call_args[0][1]
        assert "📊 <b>Քո վիճակագրությունը</b>" in sent
        assert "📚 Թեմաներ — <b>12</b>" in sent
        assert "📝 Կոնսպեկտներ — <b>8</b>" in sent
        assert "🧠 Flashcard սեսիաներ — <b>5</b>" in sent
        assert "✅ Quiz-եր — <b>3</b>" in sent
        assert mock_bot.send_message.call_args.kwargs.get("parse_mode") == "HTML"


def test_finish_quiz_increments_quiz_counter():
    state = {"questions": [{"q": "q", "options": ["a", "b"], "correct": 0, "explanation": ""}], "idx": 1, "score": 1}
    with (
        patch("bot.handlers.get_quiz", return_value=state),
        patch("bot.handlers.clear_quiz"),
        patch("bot.handlers.incr_quizzes") as mock_incr,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _finish_quiz

        _finish_quiz(456, 123, state)
        mock_incr.assert_called_once_with(123)


def test_flashcards_increment_counter():
    cards = [{"q": "a", "a": "b"}]
    with (
        patch("bot.handlers.get_last_conspectus", return_value={"topic": "t", "text": "body"}),
        patch("bot.handlers.generate_flashcards", return_value=cards),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.time.sleep"),
        patch("bot.handlers.incr_flashcards") as mock_incr,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import _start_flashcards

        _start_flashcards(456, 123)
        mock_incr.assert_called_once_with(123)
