import os
import secrets as _secrets_mod
import subprocess as _subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_WEBHOOK_SECRET_FILE = _PROJECT_ROOT / ".webhook_secret"


def _get_commit_sha() -> str:
    """Return the short SHA of the deployed commit, or an empty string.

    Computed once at module import — so the value reflects the worker's
    actual code, not whatever `git pull` did since boot. The auto-deploy
    flow touches the WSGI file on pull, which spawns a fresh worker on
    the next request with the new SHA. This makes /about a reliable
    "what version is live right now" probe.
    """
    try:
        result = _subprocess.run(
            ["git", "-C", str(_PROJECT_ROOT), "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (_subprocess.SubprocessError, OSError):
        pass
    return ""


COMMIT_SHA = _get_commit_sha()


def _bootstrap_webhook_secret(file_path: Path = _WEBHOOK_SECRET_FILE) -> str:
    """Return WEBHOOK_SECRET from env if set; otherwise read/generate a
    persistent random secret in `file_path`.

    This makes the webhook signed-by-default: a fresh PA deploy with no
    manual `openssl rand` step still rejects forged updates because the
    bot auto-generates and persists a 64-hex-char secret on first run,
    then registers it with Telegram via the boot-time `register_webhook()`.

    Precedence: env var > on-disk file > newly generated. Filesystem
    errors fall back to the empty string so a read-only mount can't
    crash worker boot — the webhook just stays unsigned in that case.
    """
    env_value = os.environ.get("WEBHOOK_SECRET", "").strip()
    if env_value:
        return env_value
    try:
        if file_path.exists():
            existing = file_path.read_text().strip()
            # Empty or whitespace-only file: treat as missing and regenerate,
            # otherwise we'd silently disable webhook auth.
            if existing:
                return existing
        new_secret = _secrets_mod.token_hex(32)
        file_path.write_text(new_secret)
        try:
            os.chmod(file_path, 0o600)
        except OSError:
            pass  # best-effort tightening; Windows / odd mounts can skip
        print(f"Generated webhook secret at {file_path} (auto-bootstrap)")
        return new_secret
    except OSError as e:
        print(f"Could not persist webhook secret ({e}); webhook will be unsigned")
        return ""


# Telegram
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"].strip()
WEBHOOK_SECRET = _bootstrap_webhook_secret()

# When set, the bot auto-registers this URL as the Telegram webhook on
# worker boot and after every /api/deploy. Leave unset for local
# polling (run_local.py). Example value on PA:
#   WEBHOOK_URL=https://<your-pa-username>.pythonanywhere.com/api/webhook
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()

# AI provider
AI_API_KEY = os.environ["AI_API_KEY"].strip()
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://api.cerebras.ai/v1").strip()
MODEL = os.environ.get("AI_MODEL", "gpt-oss-120b").strip()

# Hugging Face provider (optional) — when set, users can switch via /model
HF_SPACE_ID = os.environ.get("HF_SPACE_ID", "").strip()
HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()  # optional, for private spaces
DEFAULT_PROVIDER = "main"

# Voice input (fully free, degrades gracefully in bot/voice.py).
#
# Transcription of incoming voice messages uses the local openai-whisper
# library — no API key, runs on-device (needs ffmpeg on PATH). WHISPER_MODEL
# is the model *size*: "tiny" / "base" / "small" / "medium" / "large".
# Bigger = more accurate but slower and heavier on RAM/disk. "base" is a
# good balance for Armenian on modest hardware. The bot replies with plain
# text only — there is no voice output.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base").strip()

# Storage — optional. When SQLITE_PATH is unset the bot runs in
# stateless mode: history / rate limiting / preferences / dedupe all
# degrade gracefully (the consumer modules in bot/ check `store is
# None` at the top of every function and return safe defaults).
SQLITE_PATH = os.environ.get("SQLITE_PATH", "").strip()

# Label shown by the /about command. Defaults to "PythonAnywhere" since
# that is the documented deployment target. Override to suit your host.
HOSTING_LABEL = os.environ.get("HOSTING_LABEL", "PythonAnywhere").strip()

# Auto-deploy webhook secret. When set, /api/deploy accepts requests
# that present this value in the X-Deploy-Secret header and runs
# `git pull` + WSGI reload. When unset, /api/deploy returns 403 — the
# endpoint is fail-closed.
DEPLOY_SECRET = os.environ.get("DEPLOY_SECRET", "").strip()

# Password gating the /admin statistics command. Loaded from the environment
# only — NEVER hardcode a real password here. When unset, /admin is
# fail-closed: it refuses every login attempt and shows no stats.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
# How long a successful /admin login is remembered before the password
# must be entered again.
ADMIN_SESSION_TTL = 3600  # admin session lasts 1 hour (seconds)

# App
SYSTEM_PROMPT = (
    "You are an educational assistant that helps schoolchildren study any subject from their textbooks. "
    "When the student gives you a textbook title or topic, research it thoroughly and accurately. "
    "Summarize the material into a clear, well-structured conspectus (study notes) highlighting the most interesting facts and important details. "
    "Write in a way that is engaging and easy for a child to understand and retell in their own words. "
    "Keep your response focused and appropriately concise for a chat interface. "
    "Always reply in the same language the student is writing in (for example Armenian, Russian, or English), "
    "matching their language naturally for the entire reply. "
    "Speak warmly and conversationally, like a friendly tutor talking with a child — never robotic, stiff, or generic.\n\n"
    # Formatting: Telegram HTML only. The bot sends every reply with
    # parse_mode=HTML, so Markdown symbols would show up as literal
    # characters and unsupported tags would break rendering.
    "FORMATTING: Format your reply using Telegram HTML tags ONLY. "
    "Use <b>bold</b> for the title and section headings and to highlight key terms, "
    "<i>italic</i> for gentle emphasis, and <code>code</code> for terms, names, and definitions. "
    "NEVER use Markdown symbols like *, _, #, or backticks — Telegram will show them as plain characters. "
    "Only use these Telegram-supported tags: <b>, <i>, <u>, <s>, <code>, <pre>, <a>, <blockquote>; do not use any other tags or attributes. "
    "If you need a literal < , > or & character inside the text, write it as &lt; , &gt; or &amp; so it displays correctly.\n\n"
    # Conspectus layout: a fixed, scannable structure.
    "CONSPECTUS STRUCTURE: Make study notes structured and visually clean. "
    "Start with a <b>bold title</b> line for the topic. Then give a few clearly separated sections, each introduced by an "
    "emoji-prefixed <b>bold heading</b> (for example: 📖 <b>Սահմանում</b>, 🔑 <b>Կարևոր փաստեր</b>, ✨ <b>Հետաքրքիր մանրամասներ</b>, 🌍 <b>Ինչու է սա կարևոր</b>). "
    "Under each heading use short bullet lines (starting with • ), with the key term in <b>bold</b>. "
    "Leave a blank line between sections so the notes are easy to scan.\n\n"
    # Language quality.
    "LANGUAGE QUALITY: Always write grammatically correct text in the student's language. "
    "When you write in Armenian, use proper Armenian grammar, declensions (հոլովներ) and verb conjugations (խոնարհումներ), and natural word order. "
    "Never mix in foreign scripts (Chinese, Japanese, Korean, Arabic, etc.) or unrelated symbols — keep the whole reply in one clean language."
)

# Appended to the system prompt only when the student has no prior
# conversation history (a brand-new user). Until they establish a
# language, the bot greets and replies in Armenian by default.
NEW_USER_HINT = (
    "This is the very beginning of the conversation and the student has not established a language yet. "
    "Reply in Armenian (հայերեն) unless they clearly write in another language, and welcome them warmly."
)
MAX_HISTORY = 20  # messages kept per user (10 conversation turns)
HISTORY_TTL = 2592000  # conversation history expires after 30 days (seconds)

# Quiz mode (Feature 1). After a conspectus the student can take a short
# multiple-choice quiz generated from that conspectus to check understanding.
QUIZ_NUM_QUESTIONS = 4  # how many questions to generate per quiz
QUIZ_TTL = 3600  # an in-progress quiz expires after 1 hour (seconds)

# Flashcard mode. After a conspectus the student can pull a short deck of
# question/answer cards generated from that conspectus, sent one by one.
FLASHCARD_NUM = 5  # how many flashcards to generate per session

# Transient conversation modes (bot/session.py): /plan awaiting subjects,
# /ask free-Q&A mode, and the "guess the word" game. Expires so a forgotten
# mode doesn't trap the student in a non-default flow.
MODE_TTL = 3600  # a pending conversation mode expires after 1 hour (seconds)

# Number of true/false statements or guess-the-word rounds per /game session.
GAME_NUM_ROUNDS = 5
GAME_TTL = 3600  # an in-progress game expires after 1 hour (seconds)
# The most recent conspectus is cached per user so /quiz, the inline
# buttons, and PDF export can act on it without re-asking the AI.
CONSPECTUS_TTL = HISTORY_TTL  # cached conspectus expires alongside history
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "250"))  # max messages per user per day

# Comma-separated whitelist of Telegram users. Each entry is either a
# username (with or without leading @) or a numeric user_id. Empty
# (default) means everyone can talk to the bot. When non-empty, the
# bot stays silent for anyone not in the list — silence instead of a
# rejection message so scanners don't get confirmation the bot exists.
#
# Example: ALLOWED_USERS=@alice,bob,123456789
ALLOWED_USERS = [
    u.strip().lstrip("@")
    for u in os.environ.get("ALLOWED_USERS", "").split(",")
    if u.strip()
]
MAX_MSG_LEN = 4096  # Telegram's character limit per message
# Provider call budget. Total worst case =
# AI_RETRIES * AI_REQUEST_TIMEOUT + sum of backoff sleeps. With
# retries=2 and timeout=25s plus 1s backoff: 25 + 1 + 25 = 51s.
AI_REQUEST_TIMEOUT = 25  # seconds, applied per-attempt to OpenAI-compatible calls
AI_RETRIES = 2  # total attempts (not extra retries) — 2 means one retry on failure
# HF Gradio request timeout. Without this a hung `predict()` would occupy the
# PA worker indefinitely; combined with the dedupe pre-claim, Telegram's
# retries get silently dropped for ~10 min. Tuned to give ArmGPT enough
# headroom for cold-start jitter while still freeing the worker before
# Telegram's webhook timeout (~60s).
HF_REQUEST_TIMEOUT = 50
