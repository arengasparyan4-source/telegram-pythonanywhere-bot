"""Voice features: Whisper transcription + ElevenLabs voice clone & TTS.

Optional and fully degrading — voice never breaks normal chat:
  * Transcribing incoming voice notes needs OPENAI_API_KEY (Whisper).
  * Cloning a user's voice and replying with it needs ELEVENLABS_API_KEY.
When a key is unset, the SDK is missing, or any API call fails, the
relevant helper returns None and the caller falls back to text.

Per-user state lives in the shared KV store, mirroring preferences.py /
grade.py / jokes.py:
  voice_id:{user_id}     ElevenLabs voice id of the user's clone (persistent)
  voice_await:{user_id}  short-lived flag: next voice message is a clone sample

The API SDKs are imported lazily inside the client factories so a
missing package or unset key can never crash worker boot (or the tests,
which don't install elevenlabs).
"""

import io

from bot.clients import store
from bot.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_MODEL,
    OPENAI_API_KEY,
    VOICE_SAMPLE_WAIT_TTL,
    WHISPER_BASE_URL,
    WHISPER_MODEL,
)

# Built on first use and cached. None until then.
_whisper_client = None
_eleven_client = None


def whisper_enabled() -> bool:
    """True when incoming voice messages can be transcribed."""
    return bool(OPENAI_API_KEY)


def elevenlabs_enabled() -> bool:
    """True when voice cloning + cloned-voice replies are available."""
    return bool(ELEVENLABS_API_KEY)


def _get_whisper():
    global _whisper_client
    if _whisper_client is None:
        from openai import OpenAI

        _whisper_client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=WHISPER_BASE_URL or None,
        )
    return _whisper_client


def _get_eleven():
    global _eleven_client
    if _eleven_client is None:
        from elevenlabs.client import ElevenLabs

        _eleven_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    return _eleven_client


# ── Transcription (OpenAI Whisper) ──────────────────────────────────────────
def transcribe(audio_bytes: bytes, filename: str = "voice.ogg") -> str | None:
    """Transcribe Telegram voice audio to text. None on any failure."""
    if not whisper_enabled():
        return None
    try:
        result = _get_whisper().audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=(filename, audio_bytes),
        )
        text = (getattr(result, "text", "") or "").strip()
        return text or None
    except Exception as e:
        print(f"Whisper transcription error: {e}")
        return None


# ── Voice cloning (ElevenLabs Instant Voice Clone) ──────────────────────────
def clone_voice(user_id: int, audio_bytes: bytes) -> str | None:
    """Create an ElevenLabs Instant Voice Clone; return its voice_id or None."""
    if not elevenlabs_enabled():
        return None
    try:
        sample = io.BytesIO(audio_bytes)
        sample.name = f"sample-{user_id}.ogg"
        voice = _ivc_create(_get_eleven(), name=f"tg-user-{user_id}", files=[sample])
        return getattr(voice, "voice_id", None)
    except Exception as e:
        print(f"ElevenLabs clone error: {e}")
        return None


def _ivc_create(client, name, files):
    """Call the SDK's clone endpoint, tolerant of SDK version drift.

    The method has moved across releases: client.clone -> voices.add ->
    voices.ivc.create. Try newest first, fall back to older shapes.
    """
    voices = getattr(client, "voices", None)
    if voices is not None and hasattr(voices, "ivc"):
        return voices.ivc.create(name=name, files=files)
    if voices is not None and hasattr(voices, "add"):
        return voices.add(name=name, files=files)
    return client.clone(name=name, files=files)


# ── Text-to-speech with the cloned voice ────────────────────────────────────
def synthesize(text: str, voice_id: str) -> bytes | None:
    """Render text to speech in the user's cloned voice. None on failure."""
    if not elevenlabs_enabled():
        return None
    try:
        audio = _get_eleven().text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=ELEVENLABS_MODEL,
            output_format="mp3_44100_128",
        )
        # convert() may return raw bytes or an iterator of byte chunks.
        if isinstance(audio, (bytes, bytearray)):
            return bytes(audio)
        return b"".join(audio)
    except Exception as e:
        print(f"ElevenLabs TTS error: {e}")
        return None


# ── Per-user voice state (shared KV store) ──────────────────────────────────
def get_voice_id(user_id: int) -> str | None:
    """Return the user's cloned voice_id, or None if unset/unavailable."""
    if store is None:
        return None
    try:
        return store.get(f"voice_id:{user_id}") or None
    except Exception as e:
        print(f"Store read error (voice_id): {e}")
        return None


def set_voice_id(user_id: int, voice_id: str) -> bool:
    """Persist the user's cloned voice_id. Returns True on success."""
    if store is None:
        return False
    try:
        store.set(f"voice_id:{user_id}", voice_id)
        return True
    except Exception as e:
        print(f"Store write error (voice_id): {e}")
        return False


def set_awaiting_sample(user_id: int) -> bool:
    """Flag that the user's next voice message is a clone sample (TTL'd)."""
    if store is None:
        return False
    try:
        store.set(f"voice_await:{user_id}", "1", ex=VOICE_SAMPLE_WAIT_TTL)
        return True
    except Exception as e:
        print(f"Store write error (voice_await): {e}")
        return False


def is_awaiting_sample(user_id: int) -> bool:
    """True if we're waiting for this user's /recordvoice sample."""
    if store is None:
        return False
    try:
        return store.get(f"voice_await:{user_id}") == "1"
    except Exception as e:
        print(f"Store read error (voice_await): {e}")
        return False


def clear_awaiting_sample(user_id: int) -> None:
    """Clear the awaiting-sample flag (sample received or cancelled)."""
    if store is None:
        return
    try:
        store.delete(f"voice_await:{user_id}")
    except Exception as e:
        print(f"Store delete error (voice_await): {e}")
