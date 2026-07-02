"""Voice-input tests: local Whisper transcription -> plain-text reply.

Covers the full inbound flow end-to-end with mocks:
  1. receive a Telegram voice note -> download
  2. transcribe it with (local) Whisper
  3. answer with ask_ai and reply as plain text, with the Armenian
     transcription confirmation appended
plus the graceful-degradation paths (disabled, transcription fails).
There is no voice output — the bot never sends audio back.
"""

from unittest.mock import MagicMock, patch


def make_voice_message(user_id=123, chat_id=456, file_id="file-1"):
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.from_user.username = "kid"
    msg.chat.id = chat_id
    msg.chat.type = "private"
    msg.voice.file_id = file_id
    return msg


# ── bot/voice.py units ──────────────────────────────────────────────────────
def test_whisper_enabled_when_lib_present():
    # conftest mocks the `whisper` module, so the import succeeds.
    from bot import voice

    assert voice.whisper_enabled() is True


def test_transcribe_returns_stripped_text():
    from bot import voice

    model = MagicMock()
    model.transcribe.return_value = {"text": "  բարև ինչպես ես  "}
    with (
        patch("bot.voice.whisper_enabled", return_value=True),
        patch("bot.voice._get_whisper", return_value=model),
    ):
        assert voice.transcribe(b"oggbytes") == "բարև ինչպես ես"
    # The bytes must be handed to whisper via a real file path.
    assert isinstance(model.transcribe.call_args.args[0], str)


def test_transcribe_disabled_returns_none():
    from bot import voice

    with patch("bot.voice.whisper_enabled", return_value=False):
        assert voice.transcribe(b"x") is None


def test_transcribe_empty_result_returns_none():
    from bot import voice

    model = MagicMock()
    model.transcribe.return_value = {"text": "   "}
    with (
        patch("bot.voice.whisper_enabled", return_value=True),
        patch("bot.voice._get_whisper", return_value=model),
    ):
        assert voice.transcribe(b"x") is None


def test_transcribe_swallows_errors():
    from bot import voice

    with (
        patch("bot.voice.whisper_enabled", return_value=True),
        patch("bot.voice._get_whisper", side_effect=RuntimeError("boom")),
    ):
        assert voice.transcribe(b"x") is None


# ── handle_voice() full flow ────────────────────────────────────────────────
def test_handle_voice_transcribes_and_replies_with_text():
    from bot.handlers import handle_voice

    mock_bot = MagicMock()
    with (
        patch("bot.handlers.bot", mock_bot),
        patch("bot.handlers.keep_typing", MagicMock()),
        patch("bot.handlers.whisper_enabled", return_value=True),
        patch("bot.handlers.transcribe", return_value="ինչ է ֆոտոսինթեզը"),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.ask_ai", return_value="Ֆոտոսինթեզը գործընթաց է"),
        patch("bot.handlers.get_provider", return_value="main"),
        patch("bot.handlers.save_last_conspectus") as mock_save,
        patch("bot.handlers.send_reply") as mock_send_reply,
    ):
        handle_voice(make_voice_message())

    # No audio is ever sent back — text output only.
    mock_bot.send_voice.assert_not_called()
    mock_save.assert_called_once()
    mock_send_reply.assert_called_once()
    text = mock_send_reply.call_args.args[1]
    # Reply carries the AI answer plus the Armenian transcript confirmation.
    assert "Ֆոտոսինթեզը գործընթաց է" in text
    assert "🎤 Դու ասացիր՝ «ինչ է ֆոտոսինթեզը»" in text


def test_handle_voice_disabled_sends_notice():
    from bot.handlers import handle_voice

    mock_bot = MagicMock()
    with (
        patch("bot.handlers.bot", mock_bot),
        patch("bot.handlers.whisper_enabled", return_value=False),
        patch("bot.handlers.transcribe") as mock_tr,
    ):
        handle_voice(make_voice_message())

    mock_tr.assert_not_called()
    mock_bot.send_message.assert_called_once()
    assert "միացված չէ" in mock_bot.send_message.call_args.args[1]


def test_handle_voice_transcription_failure_sends_notice():
    from bot.handlers import handle_voice

    mock_bot = MagicMock()
    with (
        patch("bot.handlers.bot", mock_bot),
        patch("bot.handlers.keep_typing", MagicMock()),
        patch("bot.handlers.whisper_enabled", return_value=True),
        patch("bot.handlers.transcribe", return_value=None),
        patch("bot.handlers.ask_ai") as mock_ask,
    ):
        handle_voice(make_voice_message())

    mock_ask.assert_not_called()
    mock_bot.send_message.assert_called_once()


def test_handle_voice_hf_provider_replies_text_without_keyboard():
    from bot.handlers import handle_voice

    mock_bot = MagicMock()
    with (
        patch("bot.handlers.bot", mock_bot),
        patch("bot.handlers.keep_typing", MagicMock()),
        patch("bot.handlers.whisper_enabled", return_value=True),
        patch("bot.handlers.transcribe", return_value="հարց"),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.ask_ai", return_value="պատասխան"),
        patch("bot.handlers.get_provider", return_value="hf"),
        patch("bot.handlers.save_last_conspectus") as mock_save,
        patch("bot.handlers.send_reply") as mock_send_reply,
    ):
        handle_voice(make_voice_message())

    # hf output isn't a conspectus: no caching, no inline keyboard.
    mock_save.assert_not_called()
    mock_bot.send_voice.assert_not_called()
    mock_send_reply.assert_called_once()
    assert mock_send_reply.call_args.kwargs.get("reply_markup") is None
    text = mock_send_reply.call_args.args[1]
    assert "պատասխան" in text and "🎤 Դու ասացիր՝ «հարց»" in text
