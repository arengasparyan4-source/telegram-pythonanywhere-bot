"""Voice input: local Whisper transcription (no TTS, no paid APIs).

Fully free and fully degrading — voice never breaks normal chat:
  * Incoming voice notes are transcribed on-device by the local
    openai-whisper library (no API key — needs ffmpeg on PATH).
The bot replies with plain text only; there is no voice output.
When a package is missing or any step fails, ``transcribe`` returns None
and the caller falls back to a friendly notice.

whisper is imported lazily so a missing package can never crash worker
boot (or the tests, which don't install it). The model is loaded once on
first use and cached.
"""

import os
import tempfile

from bot.config import WHISPER_MODEL

# Loaded on first transcription and cached. None until then.
_whisper_model = None


def whisper_enabled() -> bool:
    """True when incoming voice messages can be transcribed."""
    try:
        import whisper  # noqa: F401

        return True
    except Exception:
        return False


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        import whisper

        _whisper_model = whisper.load_model(WHISPER_MODEL)
    return _whisper_model


# ── Transcription (local openai-whisper) ────────────────────────────────────
def transcribe(audio_bytes: bytes, filename: str = "voice.ogg") -> str | None:
    """Transcribe Telegram voice audio to text. None on any failure.

    openai-whisper reads from a file path (it shells out to ffmpeg to
    decode the audio), so the incoming bytes are written to a temp file
    that is always cleaned up.
    """
    if not whisper_enabled():
        return None
    tmp_path = None
    try:
        suffix = os.path.splitext(filename)[1] or ".ogg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        result = _get_whisper().transcribe(tmp_path)
        text = (result.get("text") or "").strip()
        return text or None
    except Exception as e:
        print(f"Whisper transcription error: {e}")
        return None
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
