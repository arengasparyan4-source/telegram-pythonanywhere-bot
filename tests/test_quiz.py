from unittest.mock import MagicMock, patch

# ── ai.generate_quiz / _parse_quiz ──────────────────────────────────────────

VALID_QUIZ_JSON = """
[
  {"q": "Ո՞ր թվականին", "options": ["1991", "1988", "2000", "1945"],
   "correct": 0, "explanation": "Հայաստանը անկախացավ 1991-ին։"},
  {"q": "Մայրաքաղաքը՞", "options": ["Գյումրի", "Երևան"],
   "correct": 1, "explanation": "Երևանն է մայրաքաղաքը։"}
]
"""


def test_generate_quiz_parses_valid_json():
    with patch("bot.ai.generate", return_value=VALID_QUIZ_JSON):
        from bot.ai import generate_quiz

        questions = generate_quiz(123, "some conspectus text")
        assert len(questions) == 2
        assert questions[0]["q"] == "Ո՞ր թվականին"
        assert questions[0]["correct"] == 0
        assert questions[1]["options"] == ["Գյումրի", "Երևան"]


def test_generate_quiz_strips_code_fence():
    fenced = "```json\n" + VALID_QUIZ_JSON.strip() + "\n```"
    with patch("bot.ai.generate", return_value=fenced):
        from bot.ai import generate_quiz

        questions = generate_quiz(123, "x")
        assert len(questions) == 2


def test_generate_quiz_returns_empty_on_garbage():
    with patch("bot.ai.generate", return_value="sorry, I can't do that"):
        from bot.ai import generate_quiz

        assert generate_quiz(123, "x") == []


def test_generate_quiz_drops_malformed_questions():
    mixed = """
    [
      {"q": "ok", "options": ["a", "b"], "correct": 1, "explanation": "e"},
      {"q": "bad index", "options": ["a", "b"], "correct": 5, "explanation": "e"},
      {"q": "", "options": ["a", "b"], "correct": 0, "explanation": "e"},
      {"q": "too few", "options": ["only"], "correct": 0, "explanation": "e"}
    ]
    """
    with patch("bot.ai.generate", return_value=mixed):
        from bot.ai import generate_quiz

        questions = generate_quiz(123, "x")
        assert len(questions) == 1
        assert questions[0]["q"] == "ok"


def test_generate_quiz_respects_num_questions_cap():
    big = "[" + ",".join(
        f'{{"q": "q{i}", "options": ["a", "b"], "correct": 0, "explanation": "e"}}'
        for i in range(10)
    ) + "]"
    with patch("bot.ai.generate", return_value=big):
        from bot.ai import generate_quiz

        assert len(generate_quiz(123, "x", num_questions=3)) == 3


# ── quiz state module ───────────────────────────────────────────────────────

SAMPLE_QUESTIONS = [
    {"q": "q1", "options": ["a", "b"], "correct": 0, "explanation": "e1"},
]


def test_quiz_state_save_and_get():
    fake_store = MagicMock()
    saved = {}
    fake_store.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    fake_store.get.side_effect = lambda k: saved.get(k)
    with patch("bot.quiz.store", fake_store):
        from bot.quiz import get_quiz, save_quiz

        assert save_quiz(7, SAMPLE_QUESTIONS) is True
        state = get_quiz(7)
        assert state["idx"] == 0
        assert state["score"] == 0
        assert state["questions"] == SAMPLE_QUESTIONS


def test_quiz_state_stateless_mode():
    with patch("bot.quiz.store", None):
        from bot.quiz import get_quiz, save_quiz

        assert save_quiz(7, SAMPLE_QUESTIONS) is False
        assert get_quiz(7) is None


def test_quiz_update_and_clear():
    fake_store = MagicMock()
    saved = {}
    fake_store.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    fake_store.get.side_effect = lambda k: saved.get(k)
    fake_store.delete.side_effect = lambda k: saved.pop(k, None)
    with patch("bot.quiz.store", fake_store):
        from bot.quiz import clear_quiz, get_quiz, save_quiz, update_quiz

        save_quiz(7, SAMPLE_QUESTIONS)
        state = get_quiz(7)
        state["idx"] = 1
        state["score"] = 1
        update_quiz(7, state)
        assert get_quiz(7)["score"] == 1
        clear_quiz(7)
        assert get_quiz(7) is None


# ── conspectus cache ────────────────────────────────────────────────────────


def test_conspectus_save_and_get():
    fake_store = MagicMock()
    saved = {}
    fake_store.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    fake_store.get.side_effect = lambda k: saved.get(k)
    with patch("bot.conspectus.store", fake_store):
        from bot.conspectus import get_last_conspectus, save_last_conspectus

        save_last_conspectus(7, "Topic", "Notes body")
        consp = get_last_conspectus(7)
        assert consp == {"topic": "Topic", "text": "Notes body"}


def test_conspectus_stateless_mode():
    with patch("bot.conspectus.store", None):
        from bot.conspectus import get_last_conspectus, save_last_conspectus

        save_last_conspectus(7, "Topic", "Notes")  # no-op, no raise
        assert get_last_conspectus(7) is None


# ── handlers: /quiz + callbacks ─────────────────────────────────────────────


def _call(data="quiz:start", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


def test_start_quiz_without_conspectus_prompts_for_topic():
    with (
        patch("bot.handlers.store", MagicMock()),
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _start_quiz

        _start_quiz(456, 123)
        sent = mock_bot.send_message.call_args[0][1]
        assert "Նախ" in sent


def test_start_quiz_stateless_mode_tells_user():
    with (
        patch("bot.handlers.store", None),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _start_quiz

        _start_quiz(456, 123)
        sent = mock_bot.send_message.call_args[0][1]
        assert "հիշողություն" in sent


def test_start_quiz_generates_and_sends_first_question():
    questions = [
        {"q": "q1", "options": ["a", "b"], "correct": 0, "explanation": "e1"},
        {"q": "q2", "options": ["c", "d"], "correct": 1, "explanation": "e2"},
    ]
    with (
        patch("bot.handlers.store", MagicMock()),
        patch("bot.handlers.get_last_conspectus", return_value={"topic": "t", "text": "body"}),
        patch("bot.handlers.generate_quiz", return_value=questions),
        patch("bot.handlers.save_quiz") as mock_save,
        patch("bot.handlers.get_quiz", return_value={"questions": questions, "idx": 0, "score": 0}),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _start_quiz

        _start_quiz(456, 123)
        mock_save.assert_called_once_with(123, questions, "t")
        # A question message was sent containing the progress counter.
        texts = [c[0][1] for c in mock_bot.send_message.call_args_list]
        assert any("Հարց 1/2" in t for t in texts)


def test_quiz_generation_failure_message():
    with (
        patch("bot.handlers.store", MagicMock()),
        patch("bot.handlers.get_last_conspectus", return_value={"topic": "t", "text": "body"}),
        patch("bot.handlers.generate_quiz", return_value=[]),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _start_quiz

        _start_quiz(456, 123)
        sent = mock_bot.send_message.call_args[0][1]
        assert "Չստացվեց" in sent


def test_handle_quiz_answer_correct():
    state = {
        "questions": [{"q": "q1", "options": ["a", "b"], "correct": 0, "explanation": "Բացատրություն"}],
        "idx": 0,
        "score": 0,
    }
    with (
        patch("bot.handlers.get_quiz", return_value=state),
        patch("bot.handlers.update_quiz") as mock_update,
        patch("bot.handlers.clear_quiz"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _handle_quiz_answer

        _handle_quiz_answer(456, 123, "quizans:0:0")
        # Score advanced and state persisted.
        assert state["score"] == 1
        assert state["idx"] == 1
        mock_update.assert_called_once()
        first_msg = mock_bot.send_message.call_args_list[0][0][1]
        assert "Ճիշտ է" in first_msg


def test_handle_quiz_answer_incorrect_shows_correct_option():
    state = {
        "questions": [{"q": "q1", "options": ["ճիշտ", "սխալ"], "correct": 0, "explanation": "e"}],
        "idx": 0,
        "score": 0,
    }
    with (
        patch("bot.handlers.get_quiz", return_value=state),
        patch("bot.handlers.update_quiz"),
        patch("bot.handlers.clear_quiz"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _handle_quiz_answer

        _handle_quiz_answer(456, 123, "quizans:0:1")
        assert state["score"] == 0
        first_msg = mock_bot.send_message.call_args_list[0][0][1]
        assert "ճիշտ" in first_msg  # the correct option text is surfaced


def test_handle_quiz_answer_ignores_stale_question():
    state = {
        "questions": [
            {"q": "q1", "options": ["a", "b"], "correct": 0, "explanation": "e"},
            {"q": "q2", "options": ["a", "b"], "correct": 0, "explanation": "e"},
        ],
        "idx": 1,
        "score": 0,
    }
    with (
        patch("bot.handlers.get_quiz", return_value=state),
        patch("bot.handlers.update_quiz") as mock_update,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _handle_quiz_answer

        # Tap on question 0 while we're on question 1 — should be ignored.
        _handle_quiz_answer(456, 123, "quizans:0:0")
        mock_update.assert_not_called()
        mock_bot.send_message.assert_not_called()


def test_finish_quiz_reports_score_and_clears():
    state = {
        "questions": [{"q": "q1", "options": ["a", "b"], "correct": 0, "explanation": "e"}],
        "idx": 1,
        "score": 1,
    }
    with (
        patch("bot.handlers.get_quiz", return_value=state),
        patch("bot.handlers.clear_quiz") as mock_clear,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _send_quiz_question

        # idx (1) past the last question -> finish path
        _send_quiz_question(456, 123)
        mock_clear.assert_called_once_with(123)
        sent = mock_bot.send_message.call_args[0][1]
        assert "1/1" in sent


def test_cb_quiz_routes_start_and_answer():
    with (
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers._start_quiz") as mock_start,
        patch("bot.handlers._handle_quiz_answer") as mock_answer,
    ):
        from bot.handlers import cb_quiz

        cb_quiz(_call(data="quiz:start"))
        mock_start.assert_called_once_with(456, 123)

        cb_quiz(_call(data="quizans:0:1"))
        mock_answer.assert_called_once_with(456, 123, "quizans:0:1")
        # Both callbacks were acknowledged.
        assert mock_bot.answer_callback_query.call_count == 2
