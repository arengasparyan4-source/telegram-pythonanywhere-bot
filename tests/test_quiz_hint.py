from unittest.mock import MagicMock, patch


def _call(data="qhint", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


# ── ai.generate_quiz_hint ────────────────────────────────────────────────────
def test_generate_quiz_hint_returns_text_and_hides_answer_instruction():
    with patch("bot.ai.generate", return_value="Մտածիր ջրի վիճակների մասին։") as g:
        from bot.ai import generate_quiz_hint

        out = generate_quiz_hint(123, "Ի՞նչ է գոլորշիացումը", ["a", "b", "c"])
        assert out == "Մտածիր ջրի վիճակների մասին։"
        prompt = g.call_args[0][1][-1]["content"]
        assert "Ի՞նչ է գոլորշիացումը" in prompt
        # The prompt forbids revealing the answer.
        assert "Do NOT reveal" in prompt


# ── handlers: hint flow ──────────────────────────────────────────────────────
def test_send_quiz_hint_uses_current_question():
    state = {
        "questions": [
            {"q": "q1", "options": ["a", "b"], "correct": 0, "explanation": "e"},
            {"q": "q2", "options": ["c", "d"], "correct": 1, "explanation": "e"},
        ],
        "idx": 1,
        "score": 0,
    }
    with (
        patch("bot.handlers.get_quiz", return_value=state),
        patch("bot.handlers.generate_quiz_hint", return_value="Հուշում") as mock_hint,
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_quiz_hint

        _send_quiz_hint(456, 123)
        # Hint is generated for the CURRENT question (idx 1 → q2).
        mock_hint.assert_called_once_with(123, "q2", ["c", "d"])
        assert "Հուշում" in mock_bot.send_message.call_args[0][1]


def test_send_quiz_hint_no_active_quiz():
    with (
        patch("bot.handlers.get_quiz", return_value=None),
        patch("bot.handlers.generate_quiz_hint") as mock_hint,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_quiz_hint

        _send_quiz_hint(456, 123)
        mock_hint.assert_not_called()
        mock_bot.send_message.assert_not_called()


def test_cb_quiz_hint_routes():
    with (
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers._send_quiz_hint") as mock_send,
    ):
        from bot.handlers import cb_quiz_hint

        cb_quiz_hint(_call("qhint"))
        mock_send.assert_called_once_with(456, 123)
        mock_bot.answer_callback_query.assert_called_once()
