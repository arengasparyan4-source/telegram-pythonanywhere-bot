from unittest.mock import MagicMock, patch

# ── ai.generate_flashcards / _parse_flashcards ──────────────────────────────

VALID_CARDS_JSON = """
[
  {"q": "Ի՞նչ է ֆոտոսինթեզը", "a": "Բույսերի սնունդ ստեղծելու գործընթացը"},
  {"q": "Ինչի՞ց է առաջանում", "a": "Արևի լույսից, ջրից և CO2-ից"}
]
"""


def test_generate_flashcards_parses_valid_json():
    with patch("bot.ai.generate", return_value=VALID_CARDS_JSON):
        from bot.ai import generate_flashcards

        cards = generate_flashcards(123, "some conspectus text")
        assert len(cards) == 2
        assert cards[0]["q"] == "Ի՞նչ է ֆոտոսինթեզը"
        assert cards[0]["a"] == "Բույսերի սնունդ ստեղծելու գործընթացը"


def test_generate_flashcards_strips_code_fence():
    fenced = "```json\n" + VALID_CARDS_JSON.strip() + "\n```"
    with patch("bot.ai.generate", return_value=fenced):
        from bot.ai import generate_flashcards

        assert len(generate_flashcards(123, "x")) == 2


def test_generate_flashcards_returns_empty_on_garbage():
    with patch("bot.ai.generate", return_value="sorry, no JSON here"):
        from bot.ai import generate_flashcards

        assert generate_flashcards(123, "x") == []


def test_generate_flashcards_drops_malformed_and_caps():
    mixed = """
    [
      {"q": "ok", "a": "yes"},
      {"q": "", "a": "empty q"},
      {"q": "no answer", "a": ""},
      {"q": "second ok", "a": "also yes"}
    ]
    """
    with patch("bot.ai.generate", return_value=mixed):
        from bot.ai import generate_flashcards

        cards = generate_flashcards(123, "x", num_cards=1)
        assert len(cards) == 1
        assert cards[0]["q"] == "ok"


# ── handlers: _start_flashcards + callback ──────────────────────────────────


def _call(data="cards:start", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


def test_start_flashcards_without_conspectus_prompts_for_topic():
    with (
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _start_flashcards

        _start_flashcards(456, 123)
        sent = mock_bot.send_message.call_args[0][1]
        assert "Նախ" in sent


def test_start_flashcards_generation_failure_message():
    with (
        patch("bot.handlers.get_last_conspectus", return_value={"topic": "t", "text": "body"}),
        patch("bot.handlers.generate_flashcards", return_value=[]),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _start_flashcards

        _start_flashcards(456, 123)
        sent = mock_bot.send_message.call_args[0][1]
        assert "Չստացվեց" in sent


def test_start_flashcards_sends_each_card_formatted():
    cards = [
        {"q": "Հարց 1", "a": "Պատասխան 1"},
        {"q": "Հարց 2", "a": "Պատասխան 2"},
    ]
    with (
        patch("bot.handlers.get_last_conspectus", return_value={"topic": "t", "text": "body"}),
        patch("bot.handlers.generate_flashcards", return_value=cards),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.time.sleep"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _start_flashcards

        _start_flashcards(456, 123)
        texts = [c[0][1] for c in mock_bot.send_message.call_args_list]
        # Intro + one message per card.
        assert any("flashcard" in t.lower() for t in texts)
        card_msgs = [t for t in texts if t.startswith("❓")]
        assert len(card_msgs) == 2
        assert "❓ Հարց 1\n✅ Պատասխան 1" in card_msgs


def test_cb_flashcards_routes():
    with (
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers._start_flashcards") as mock_start,
    ):
        from bot.handlers import cb_flashcards

        cb_flashcards(_call())
        mock_start.assert_called_once_with(456, 123)
        mock_bot.answer_callback_query.assert_called_once()
