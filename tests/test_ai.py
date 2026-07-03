from unittest.mock import patch


# ── sanitize_reply ──────────────────────────────────────────────────────────


def test_sanitize_reply_strips_foreign_scripts():
    from bot.ai import sanitize_reply

    # Chinese, Japanese, Korean, Arabic removed.
    assert sanitize_reply("水") == ""
    assert sanitize_reply("こんにちは") == ""
    assert sanitize_reply("안녕") == ""
    assert sanitize_reply("مرحبا") == ""


def test_sanitize_reply_preserves_armenian_emoji_and_box_drawing():
    from bot.ai import sanitize_reply

    # Armenian + emoji + subscript survive; the Chinese char is dropped.
    assert sanitize_reply("Բարև 世界 👋") == "Բարև  👋"
    # Mind-map tree connectors and indentation are preserved byte-for-byte.
    tree = "🌍 Թեմա\n  ├── 📌 Ենթաթեմա\n  └── մանրամասն"
    assert sanitize_reply(tree) == tree
    # Russian, English, digits, HTML tags, and punctuation are untouched.
    html_text = "<b>Привет</b> H₂O — test 123!"
    assert sanitize_reply(html_text) == html_text


def test_ask_ai_sanitizes_reply():
    with (
        patch("bot.ai.generate", return_value="Ответ 你好 done"),
        patch("bot.ai.get_history", return_value=[]),
        patch("bot.ai.save_history") as mock_save,
    ):
        from bot.ai import ask_ai

        reply = ask_ai(123, "hi")
        # Chinese removed from both the returned text and the saved history.
        assert "你好" not in reply
        assert reply == "Ответ  done"
        saved_history = mock_save.call_args[0][1]
        assert "你好" not in saved_history[1]["content"]


def test_ask_ai_returns_reply():
    with (
        patch("bot.ai.generate", return_value="Hello there!"),
        patch("bot.ai.get_history", return_value=[]),
        patch("bot.ai.save_history"),
    ):
        from bot.ai import ask_ai

        reply = ask_ai(123, "hi")
        assert reply == "Hello there!"


def test_ask_ai_saves_history():
    with (
        patch("bot.ai.generate", return_value="reply"),
        patch("bot.ai.get_history", return_value=[]),
        patch("bot.ai.save_history") as mock_save,
    ):
        from bot.ai import ask_ai

        ask_ai(123, "hi")
        mock_save.assert_called_once()
        saved_history = mock_save.call_args[0][1]
        assert saved_history[0] == {"role": "user", "content": "hi"}
        assert saved_history[1]["role"] == "assistant"


def test_ask_ai_passes_user_id_to_generate():
    with (
        patch("bot.ai.generate", return_value="hi") as mock_gen,
        patch("bot.ai.get_history", return_value=[]),
        patch("bot.ai.save_history"),
    ):
        from bot.ai import ask_ai

        ask_ai(456, "hello")
        assert mock_gen.call_args[0][0] == 456
