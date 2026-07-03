import html
import io
import os
import time
from datetime import datetime
from telebot import types
from bot.clients import bot, BOT_INFO, store
from bot.config import COMMIT_SHA, HF_SPACE_ID, HOSTING_LABEL, MODEL, RATE_LIMIT
from bot.ai import (
    ask_ai,
    expand_conspectus,
    generate_flashcards,
    generate_mindmap,
    generate_quiz,
    generate_story,
    generate_why_matters,
)
from bot.achievements import check_and_award, get_badges
from bot.activity import record_activity
from bot.conspectus import get_last_conspectus, save_last_conspectus
from bot.grade import clear_grade, get_grade, set_grade
from bot.helpers import is_allowed, keep_typing, send_reply, should_respond
from bot.history import clear_history
from bot.jokes import jokes_disabled, set_jokes_disabled
from bot.parent import build_report, link_child
from bot.pdf import build_conspectus_pdf
from bot.preferences import get_provider, set_provider
from bot.quiz import clear_quiz, get_quiz, save_quiz, update_quiz
from bot.rate_limit import is_rate_limited
from bot.reminders import (
    REPEAT_HEADER,
    clear_reminder,
    get_reminder,
    normalize_time,
    set_reminder,
)
from bot.stats import (
    get_stats,
    incr_conspectuses,
    incr_flashcards,
    incr_quizzes,
    incr_topics,
)
from bot.voice import transcribe, whisper_enabled

# Verbose console logging for local dev and teaching. Enabled by
# BOT_VERBOSE_LOG=1 (run_local.py sets this automatically). Prints one
# line per inbound/outbound message so kids and teachers can see the
# conversation flow in their terminal while the bot is running.
VERBOSE_LOG = os.environ.get("BOT_VERBOSE_LOG", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def _log(message, direction: str, text: str) -> None:
    """Print a one-line trace of a message in verbose mode.

    direction is "in" (user → bot) or "out" (bot → user). Text is
    truncated to 500 characters so long AI replies don't flood the
    terminal. Newlines are collapsed for single-line readability.
    """
    if not VERBOSE_LOG:
        return
    user = message.from_user
    user_name = (
        f"@{user.username}" if user.username else (user.first_name or f"user:{user.id}")
    )
    bot_name = f"@{BOT_INFO.username}"
    snippet = (text or "").replace("\n", " ").replace("\r", " ")
    if len(snippet) > 500:
        snippet = snippet[:500] + "..."
    if direction == "in":
        sender, receiver = user_name, bot_name
    else:
        sender, receiver = bot_name, user_name
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {sender} → {receiver}: {snippet}", flush=True)


@bot.message_handler(commands=["start"], func=is_allowed)
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        "<b>Բարև 👋 Ես քո ուսումնական օգնականն եմ։</b> Գրիր ինձ քո դասագրքի անունը կամ թեման, "
        "և ես կպատրաստեմ քեզ համար հետաքրքիր ու հեշտ կոնսպեկտ։\n\n"
        "Խորհուրդ՝ /grade հրամանով նշիր քո դասարանը, որ բացատրությունները հենց քեզ համար լինեն 🙂\n\n"
        "Հրամանների ցանկը տեսնելու համար գրիր /help։",
        parse_mode="HTML",
    )


@bot.message_handler(commands=["help"], func=is_allowed)
def cmd_help(message):
    lines = [
        "/start — սկսել զրույցը բոտի հետ",
        "/help — տեսնել հրամանների ցանկը և օգնության ինֆորմացիա",
        "/quiz — կարճ վիկտորինա վերջին կոնսպեկտի հիման վրա",
        "/pdf — ստանալ վերջին կոնսպեկտը PDF ֆայլով",
        "/stats — տեսնել քո ուսումնական վիճակագրությունը",
        "/achievements — տեսնել քո վաստակած նշանները",
        "/repeat — կրկնել վերջին կոնսպեկտը",
        "/remind — դնել օրական հիշեցում (օր․՝ /remind 18:00)",
        "/parent — ծնողի շաբաթական հաշվետվություն (/parent &lt;երեխայի ID&gt;)",
        "/grade — ընտրել դասարանը, որ բացատրությունները հարմարեցնեմ քեզ",
        "/reset — մաքրել մեր նախորդ զրույցի պատմությունը և սկսել նորից",
        "/about — իմանալ ավելին այս բոտի մասին",
        "/sha — ցույց տալ բոտի ընթացիկ git commit SHA-ն",
    ]
    if HF_SPACE_ID:
        lines.append("/model — փոխել AI մատակարարը")
    bot.send_message(
        message.chat.id,
        "<b>Հրամանների ցանկ</b>\n" + "\n".join(lines),
        parse_mode="HTML",
    )


@bot.message_handler(commands=["reset"], func=is_allowed)
def cmd_reset(message):
    clear_history(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "Մեր նախորդ զրույցը մաքրված է։ Սկսենք նորից 🙂",
        parse_mode="HTML",
    )


@bot.message_handler(commands=["about"], func=is_allowed)
def cmd_about(message):
    if HF_SPACE_ID:
        provider = get_provider(message.from_user.id)
        model_line = f"{MODEL} (main)" if provider == "main" else f"{HF_SPACE_ID} (hf)"
    else:
        model_line = MODEL
    storage_line = "SQLite" if store is not None else "առանց հիշողության"
    lines = [
        f"<b>Մոդել:</b> {html.escape(model_line)}",
        f"<b>Հիշողություն:</b> {storage_line}",
        f"<b>Հոսթինգ:</b> {html.escape(HOSTING_LABEL)}",
    ]
    if COMMIT_SHA:
        lines.append(f"<b>Տարբերակ:</b> <code>{html.escape(COMMIT_SHA)}</code>")
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML")


@bot.message_handler(commands=["stats"], func=is_allowed)
def cmd_stats(message):
    s = get_stats(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "📊 <b>Քո վիճակագրությունը</b>\n"
        f"📚 Թեմաներ — <b>{s['topics']}</b>\n"
        f"📝 Կոնսպեկտներ — <b>{s['conspectuses']}</b>\n"
        f"🧠 Flashcard սեսիաներ — <b>{s['flashcards']}</b>\n"
        f"✅ Quiz-եր — <b>{s['quizzes']}</b>",
        parse_mode="HTML",
    )


def _award_new_badges(chat_id: int, user_id: int) -> None:
    """Award any newly-earned badges and congratulate the user for each."""
    for badge in check_and_award(user_id):
        bot.send_message(
            chat_id,
            f"🎉 Շնորհավո՛ր։ Դու վաստակեցիր նշան՝ <b>{html.escape(str(badge))}</b>",
            parse_mode="HTML",
        )


@bot.message_handler(commands=["achievements"], func=is_allowed)
def cmd_achievements(message):
    badges = get_badges(message.from_user.id)
    if not badges:
        bot.send_message(
            message.chat.id,
            "🏅 Դու դեռ նշաններ չունես։ Սովորիր, անցիր վիկտորինաներ ու հավաքիր դրանք 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        message.chat.id,
        "🏅 <b>Քո նշանները</b>\n"
        + "\n".join(f"• {html.escape(str(b))}" for b in badges),
        parse_mode="HTML",
    )


@bot.message_handler(commands=["parent"], func=is_allowed)
def cmd_parent(message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1 or not parts[1].strip():
        bot.send_message(
            message.chat.id,
            "👨‍👩‍👧 <b>Ծնողի ռեժիմ</b>։ Ուղարկիր՝ /parent &lt;երեխայի ID&gt;\n"
            "Օրինակ՝ /parent 123456789\n\n"
            "Երեխայի ID-ն նրա Telegram-ի թվային նույնացուցիչն է։",
            parse_mode="HTML",
        )
        return
    try:
        child_id = int(parts[1].strip())
    except ValueError:
        bot.send_message(
            message.chat.id,
            "Երեխայի ID-ն պետք է լինի թիվ։ Օրինակ՝ /parent 123456789",
            parse_mode="HTML",
        )
        return
    if store is None:
        bot.send_message(
            message.chat.id,
            "Ծնողի ռեժիմը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    link_child(message.from_user.id, child_id)
    send_reply(message, build_report(child_id))


@bot.message_handler(commands=["repeat"], func=is_allowed)
def cmd_repeat(message):
    consp = get_last_conspectus(message.from_user.id)
    if not consp:
        bot.send_message(
            message.chat.id,
            "Դեռ կրկնելու թեմա չկա 🙂 Ուղարկիր դասագրքի անունը կամ թեման։",
            parse_mode="HTML",
        )
        return
    send_reply(
        message,
        f"{REPEAT_HEADER}\n\n{consp['text']}",
        reply_markup=_conspectus_keyboard(),
    )


@bot.message_handler(commands=["remind"], func=is_allowed)
def cmd_remind(message):
    user_id = message.from_user.id
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1:
        current = get_reminder(user_id)
        if current:
            bot.send_message(
                message.chat.id,
                f"⏰ Քո օրական հիշեցումը դրված է ժամը <b>{html.escape(str(current))}</b>-ին։\n"
                "Անջատելու համար գրիր /remind off։",
                parse_mode="HTML",
            )
        else:
            bot.send_message(
                message.chat.id,
                "Հիշեցում դրված չէ։ Օրինակ՝ /remind 18:00\n"
                "Ամեն օր այդ ժամին կուղարկեմ քո վերջին կոնսպեկտը 🙂",
                parse_mode="HTML",
            )
        return
    arg = parts[1].strip().lower()
    if arg in ("off", "անջատել"):
        clear_reminder(user_id)
        bot.send_message(
            message.chat.id, "🔕 Հիշեցումն անջատված է։", parse_mode="HTML"
        )
        return
    hhmm = normalize_time(arg)
    if not hhmm:
        bot.send_message(
            message.chat.id,
            "Սխալ ձևաչափ։ Գրիր ժամը այսպես՝ /remind 18:00 (24-ժամյա ձևաչափով)։",
            parse_mode="HTML",
        )
        return
    if not set_reminder(user_id, hhmm):
        bot.send_message(
            message.chat.id,
            "Հիշեցումը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        message.chat.id,
        f"⏰ Հիշեցումը դրված է ամեն օր ժամը <b>{html.escape(str(hhmm))}</b>-ին։ Կուղարկեմ քո վերջին կոնսպեկտը 🙂",
        parse_mode="HTML",
    )


# ── Joke + facts (three messages in sequence) ───────────────────────────────
# Sent as three separate messages with a short pause between them so it reads
# like a little burst of chat rather than one wall of text. Each ask_ai() call
# shares the user's conversation history, so the fun fact and historical fact
# stay on the joke's topic, and every message mirrors the user's language
# (Armenian by default for new users).
@bot.message_handler(commands=["stopjoke"], func=is_allowed)
def cmd_stopjoke(message):
    set_jokes_disabled(message.from_user.id, True)
    bot.send_message(
        message.chat.id,
        "Կատակները անջատված են։ Կարող ես նորից միացնել /joke հրամանով։",
        parse_mode="HTML",
    )


@bot.message_handler(commands=["joke"], func=is_allowed)
def cmd_joke(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    # /joke doubles as the re-enable toggle: while jokes are off, the first
    # /joke turns them back on and stops there, so the next /joke tells one.
    if jokes_disabled(user_id):
        set_jokes_disabled(user_id, False)
        bot.send_message(
            chat_id,
            "Կատակները անջատված են։ Գրիր /joke նորից միացնելու համար։",
            parse_mode="HTML",
        )
        return
    steps = (
        "Tell one short, clean, funny joke. Always reply in Armenian by "
        "default, but if the user's last message was in a different language, "
        "reply in that language instead. One joke only, no extra text.",
        "Now share one interesting, fun fact related to the topic of the joke "
        "you just told. Keep it to one or two sentences, in the user's language.",
        "Now share one surprising or little-known historical fact on the same "
        "theme. Keep it to one or two sentences, in the user's language.",
    )
    for i, prompt in enumerate(steps):
        with keep_typing(chat_id):
            reply = ask_ai(user_id, prompt)
        bot.send_message(chat_id, reply, parse_mode="HTML")
        _log(message, "out", reply)
        if i < len(steps) - 1:
            time.sleep(1.5)


@bot.message_handler(commands=["sha"], func=is_allowed)
def cmd_sha(message):
    sha = COMMIT_SHA or "unknown"
    bot.send_message(
        message.chat.id,
        f"Live SHA: <code>{html.escape(sha)}</code>",
        parse_mode="HTML",
    )


if HF_SPACE_ID:

    @bot.message_handler(commands=["model"], func=is_allowed)
    def cmd_model(message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) == 1:
            current = get_provider(message.from_user.id)
            bot.send_message(
                message.chat.id,
                f"Ընթացիկ մատակարարը՝ <b>{html.escape(str(current))}</b>\n\n"
                "Տարբերակները՝\n"
                "/model main — Cerebras (արագ, բազմալեզու, հիշողությամբ)\n"
                "/model hf — ArmGPT (միայն հայերեն, դանդաղ, առանց հիշողության)",
                parse_mode="HTML",
            )
            return
        choice = parts[1].strip().lower()
        if choice not in ("main", "hf"):
            bot.send_message(
                message.chat.id,
                "Սխալ ընտրություն։ Օգտագործիր՝ /model main կամ /model hf",
                parse_mode="HTML",
            )
            return
        if not set_provider(message.from_user.id, choice):
            bot.send_message(
                message.chat.id,
                "Չստացվեց պահպանել նախընտրությունը։ Փորձիր մի փոքր ուշ։",
                parse_mode="HTML",
            )
            return
        if choice == "hf":
            bot.send_message(
                message.chat.id,
                "Անցանք hf-ի (ArmGPT)։\n\n"
                "Ուշադրություն՝ սա փոքրիկ մոդել է, որը սովորել է միայն հայերեն տեքստերի վրա։ "
                "Այն կշարունակի այն, ինչ գրում ես, այլ ոչ թե կպատասխանի հարցերին, "
                "և չի հասկանում անգլերեն։ Պատասխանները տևում են ~30-60 վայրկյան և հիշողություն չկա։",
                parse_mode="HTML",
            )
        else:
            bot.send_message(
                message.chat.id,
                "Անցանք հիմնական մատակարարին։",
                parse_mode="HTML",
            )


# ── Conspectus inline keyboard ──────────────────────────────────────────────
# Shown under every conspectus. Feature 1 adds the quiz button; Feature 2
# adds "more detail" / "different topic"; Feature 4 extends it further.
def _conspectus_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📝 Կարճ վիկտորինա", callback_data="quiz:start"))
    kb.add(types.InlineKeyboardButton("🧠 Flashcards", callback_data="cards:start"))
    kb.add(types.InlineKeyboardButton("🗺 Mind Map", callback_data="mindmap:show"))
    kb.add(types.InlineKeyboardButton("📖 Պատմություն", callback_data="story:show"))
    kb.add(types.InlineKeyboardButton("🌍 Ինչու է կարևոր?", callback_data="why:show"))
    kb.row(
        types.InlineKeyboardButton("🔍 Ավելի մանրամասն", callback_data="consp:more"),
        types.InlineKeyboardButton("📚 Ուրիշ թեմա", callback_data="consp:new"),
    )
    kb.add(types.InlineKeyboardButton("📄 PDF", callback_data="pdf:export"))
    return kb


# ── Conspectus buttons (Feature 2) ──────────────────────────────────────────
def _more_detail(chat_id: int, user_id: int, message) -> None:
    """Regenerate a deeper version of the user's last conspectus."""
    consp = get_last_conspectus(user_id)
    if not consp:
        bot.send_message(
            chat_id,
            "Չգտա նախորդ կոնսպեկտը 🙂 Ուղարկիր թեման նորից, որ պատրաստեմ։",
            parse_mode="HTML",
        )
        return
    try:
        with keep_typing(chat_id):
            reply = expand_conspectus(user_id, consp["topic"], consp["text"])
    except Exception as e:
        print(f"More-detail generation error: {e}")
        bot.send_message(
            chat_id,
            "Ինչ-որ բան այնպես չգնաց։ Խնդրում եմ՝ փորձիր նորից։",
            parse_mode="HTML",
        )
        return
    # Cache the expanded version so a follow-up quiz / further expansion
    # builds on the deeper notes, then re-show the keyboard.
    save_last_conspectus(user_id, consp["topic"], reply)
    incr_conspectuses(user_id)
    record_activity(user_id)
    send_reply(message, reply, reply_markup=_conspectus_keyboard())
    _award_new_badges(chat_id, user_id)


def _prompt_new_topic(chat_id: int) -> None:
    bot.send_message(
        chat_id,
        "Լավ 🙂 Գրիր նոր դասագրքի անունը կամ թեման, և ես կպատրաստեմ նոր կոնսպեկտ։",
        parse_mode="HTML",
    )


# ── PDF export (Feature 4) ──────────────────────────────────────────────────
def _export_pdf(chat_id: int, user_id: int) -> None:
    """Render the user's last conspectus to a PDF and send it as a document."""
    consp = get_last_conspectus(user_id)
    if not consp:
        bot.send_message(
            chat_id,
            "Դեռ կոնսպեկտ չկա 🙂 Ուղարկիր թեման, որ պատրաստեմ, հետո կտամ PDF-ով։",
            parse_mode="HTML",
        )
        return
    try:
        with keep_typing(chat_id):
            pdf_bytes = build_conspectus_pdf(consp["topic"], consp["text"])
    except Exception as e:
        print(f"PDF generation error: {e}")
        bot.send_message(
            chat_id,
            "Չստացվեց պատրաստել PDF-ը։ Խնդրում եմ՝ փորձիր նորից։",
            parse_mode="HTML",
        )
        return
    document = io.BytesIO(pdf_bytes)
    document.name = "konspekt.pdf"
    bot.send_document(
        chat_id,
        document,
        visible_file_name="konspekt.pdf",
        caption=f"📄 {consp['topic'][:200]}",
    )


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("consp:"))
def cb_conspectus(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if call.data == "consp:more":
        _more_detail(chat_id, user_id, call.message)
    elif call.data == "consp:new":
        _prompt_new_topic(chat_id)


# ── Grade level selection (Feature 3) ───────────────────────────────────────
def _grade_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("1–4 (կրտսեր)", callback_data="grade:set:1-4"))
    kb.add(types.InlineKeyboardButton("5–9 (միջին)", callback_data="grade:set:5-9"))
    kb.add(types.InlineKeyboardButton("10–12 (ավագ)", callback_data="grade:set:10-12"))
    kb.add(
        types.InlineKeyboardButton(
            "Առանց սահմանափակման", callback_data="grade:clear"
        )
    )
    return kb


@bot.message_handler(commands=["grade"], func=is_allowed)
def cmd_grade(message):
    current = get_grade(message.from_user.id)
    if current:
        head = (
            f"Քո ընտրած դասարանն է՝ <b>{html.escape(str(current))}</b>։\n\n"
            "Ուզում ես փոխե՞լ։ Ընտրիր ստորև 👇"
        )
    else:
        head = "Ընտրիր քո դասարանը, որ բացատրություններն ու վիկտորինաները հարմարեցնեմ քեզ 👇"
    bot.send_message(
        message.chat.id, head, reply_markup=_grade_keyboard(), parse_mode="HTML"
    )


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("grade:"))
def cb_grade(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if call.data == "grade:clear":
        clear_grade(user_id)
        bot.send_message(
            chat_id,
            "Հանեցի դասարանի սահմանափակումը 🙂 Կբացատրեմ ընդհանուր ոճով։",
            parse_mode="HTML",
        )
        return
    if call.data.startswith("grade:set:"):
        grade = call.data[len("grade:set:") :]
        if set_grade(user_id, grade):
            bot.send_message(
                chat_id,
                f"Հիանալի 👍 Այսուհետ կբացատրեմ <b>{html.escape(grade)}</b> դասարանի մակարդակով։",
                parse_mode="HTML",
            )
        else:
            bot.send_message(
                chat_id,
                "Չստացվեց պահպանել ընտրությունը։ "
                "Հնարավոր է՝ հիշողությունը միացված չէ 🙂",
                parse_mode="HTML",
            )


# ── Quiz mode (Feature 1) ───────────────────────────────────────────────────
def _start_quiz(chat_id: int, user_id: int) -> None:
    """Generate a quiz from the user's last conspectus and ask question 1."""
    if store is None:
        bot.send_message(
            chat_id,
            "Վիկտորինան հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    consp = get_last_conspectus(user_id)
    if not consp:
        bot.send_message(
            chat_id,
            "Նախ ուղարկիր դասագրքի անունը կամ թեման, որ պատրաստեմ կոնսպեկտ, "
            "հետո կարող ենք վիկտորինա անել 🙂",
            parse_mode="HTML",
        )
        return
    try:
        with keep_typing(chat_id):
            questions = generate_quiz(user_id, consp["text"])
    except Exception as e:
        print(f"Quiz generation error: {e}")
        questions = []
    if not questions:
        bot.send_message(
            chat_id,
            "Չստացվեց պատրաստել վիկտորինան։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    save_quiz(user_id, questions)
    bot.send_message(chat_id, "Եկ ստուգենք, թե ինչ հիշեցիր 📝", parse_mode="HTML")
    _send_quiz_question(chat_id, user_id)


def _send_quiz_question(chat_id: int, user_id: int) -> None:
    """Send the current question with one inline button per option."""
    state = get_quiz(user_id)
    if not state:
        return
    idx = state["idx"]
    questions = state["questions"]
    if idx >= len(questions):
        _finish_quiz(chat_id, user_id, state)
        return
    q = questions[idx]
    kb = types.InlineKeyboardMarkup()
    for opt_i, opt in enumerate(q["options"]):
        kb.add(types.InlineKeyboardButton(opt, callback_data=f"quizans:{idx}:{opt_i}"))
    bot.send_message(
        chat_id,
        f"❓ <b>Հարց {idx + 1}/{len(questions)}</b>\n\n{html.escape(q['q'])}",
        reply_markup=kb,
        parse_mode="HTML",
    )


def _handle_quiz_answer(chat_id: int, user_id: int, data: str) -> None:
    """Grade a tapped option, give Armenian feedback, advance the quiz."""
    state = get_quiz(user_id)
    if not state:
        return
    try:
        _, qidx_s, opt_s = data.split(":")
        qidx, opt = int(qidx_s), int(opt_s)
    except ValueError:
        return
    # Ignore taps on an old question (e.g. the student scrolled up and
    # re-tapped a previous question's buttons).
    if qidx != state["idx"]:
        return
    q = state["questions"][qidx]
    correct = q["correct"]
    explanation = q.get("explanation", "")
    if opt == correct:
        state["score"] += 1
        bot.send_message(
            chat_id,
            f"✅ <b>Ճիշտ է։</b> {html.escape(explanation)}".rstrip(),
            parse_mode="HTML",
        )
    else:
        correct_text = q["options"][correct]
        bot.send_message(
            chat_id,
            f"❌ Ճիշտ պատասխանն է՝ «<b>{html.escape(correct_text)}</b>»։ {html.escape(explanation)}".rstrip(),
            parse_mode="HTML",
        )
    state["idx"] += 1
    update_quiz(user_id, state)
    _send_quiz_question(chat_id, user_id)


def _finish_quiz(chat_id: int, user_id: int, state: dict) -> None:
    score = state["score"]
    total = len(state["questions"])
    clear_quiz(user_id)
    incr_quizzes(user_id)
    record_activity(user_id)
    bot.send_message(
        chat_id,
        f"🎉 <b>Վերջ։</b> Դու հավաքեցիր <b>{score}/{total}</b> միավոր։ Լավ աշխատանք էր 👏",
        parse_mode="HTML",
    )
    _award_new_badges(chat_id, user_id)


@bot.message_handler(commands=["quiz"], func=is_allowed)
def cmd_quiz(message):
    _start_quiz(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["pdf"], func=is_allowed)
def cmd_pdf(message):
    _export_pdf(message.chat.id, message.from_user.id)


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("pdf:"))
def cb_pdf(call):
    bot.answer_callback_query(call.id)
    _export_pdf(call.message.chat.id, call.from_user.id)


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("quiz"))
def cb_quiz(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if call.data == "quiz:start":
        _start_quiz(chat_id, user_id)
    elif call.data.startswith("quizans:"):
        _handle_quiz_answer(chat_id, user_id, call.data)


# ── Flashcard mode ───────────────────────────────────────────────────────────
def _start_flashcards(chat_id: int, user_id: int) -> None:
    """Generate a deck from the user's last conspectus and send it card by card.

    Each card is its own message (❓ question / ✅ answer) with a 1s pause so
    the deck reads like a paced study session rather than one wall of text.
    """
    consp = get_last_conspectus(user_id)
    if not consp:
        bot.send_message(
            chat_id,
            "Նախ ուղարկիր դասագրքի անունը կամ թեման, որ պատրաստեմ կոնսպեկտ, "
            "հետո կսարքեմ flashcard-ներ 🙂",
            parse_mode="HTML",
        )
        return
    try:
        with keep_typing(chat_id):
            cards = generate_flashcards(user_id, consp["text"])
    except Exception as e:
        print(f"Flashcard generation error: {e}")
        cards = []
    if not cards:
        bot.send_message(
            chat_id,
            "Չստացվեց պատրաստել flashcard-ները։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    bot.send_message(chat_id, "🧠 <b>Ահա քո flashcard-ները՝</b>", parse_mode="HTML")
    for i, card in enumerate(cards):
        bot.send_message(
            chat_id,
            f"❓ <b>{html.escape(card['q'])}</b>\n✅ {html.escape(card['a'])}",
            parse_mode="HTML",
        )
        if i < len(cards) - 1:
            time.sleep(1)
    incr_flashcards(user_id)
    record_activity(user_id)
    _award_new_badges(chat_id, user_id)


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("cards:"))
def cb_flashcards(call):
    bot.answer_callback_query(call.id)
    _start_flashcards(call.message.chat.id, call.from_user.id)


# ── Mind map ─────────────────────────────────────────────────────────────────
def _send_mindmap(chat_id: int, user_id: int) -> None:
    """Generate a text mind map of the last conspectus and send it.

    Sent as plain text (no Markdown) so the tree connectors and indentation
    render exactly as generated instead of being reflowed or interpreted.
    """
    consp = get_last_conspectus(user_id)
    if not consp:
        bot.send_message(
            chat_id,
            "Նախ ուղարկիր դասագրքի անունը կամ թեման, որ պատրաստեմ կոնսպեկտ, "
            "հետո կսարքեմ mind map 🙂",
            parse_mode="HTML",
        )
        return
    try:
        with keep_typing(chat_id):
            mindmap = generate_mindmap(user_id, consp["topic"], consp["text"])
    except Exception as e:
        print(f"Mind map generation error: {e}")
        mindmap = ""
    if not (mindmap and mindmap.strip()):
        bot.send_message(
            chat_id,
            "Չստացվեց պատրաստել mind map-ը։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    # Sent as plain text (no parse_mode) so the tree connectors and
    # indentation render exactly as generated instead of being reflowed.
    bot.send_message(chat_id, mindmap)


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("mindmap:"))
def cb_mindmap(call):
    bot.answer_callback_query(call.id)
    _send_mindmap(call.message.chat.id, call.from_user.id)


# ── Story mode ───────────────────────────────────────────────────────────────
def _send_story(chat_id: int, user_id: int, message) -> None:
    """Retell the last conspectus as a short story and send it."""
    consp = get_last_conspectus(user_id)
    if not consp:
        bot.send_message(
            chat_id,
            "Նախ ուղարկիր դասագրքի անունը կամ թեման, որ պատրաստեմ կոնսպեկտ, "
            "հետո կպատմեմ այն որպես պատմություն 📖",
            parse_mode="HTML",
        )
        return
    try:
        with keep_typing(chat_id):
            story = generate_story(user_id, consp["topic"], consp["text"])
    except Exception as e:
        print(f"Story generation error: {e}")
        story = ""
    if not (story and story.strip()):
        bot.send_message(
            chat_id,
            "Չստացվեց պատրաստել պատմությունը։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    send_reply(message, f"📖 {story}")


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("story:"))
def cb_story(call):
    bot.answer_callback_query(call.id)
    _send_story(call.message.chat.id, call.from_user.id, call.message)


# ── "Why does this matter?" ──────────────────────────────────────────────────
def _send_why_matters(chat_id: int, user_id: int, message) -> None:
    """Explain why the last conspectus's topic matters in real life."""
    consp = get_last_conspectus(user_id)
    if not consp:
        bot.send_message(
            chat_id,
            "Նախ ուղարկիր դասագրքի անունը կամ թեման, որ պատրաստեմ կոնսպեկտ, "
            "հետո կբացատրեմ՝ ինչու է դա կարևոր 🌍",
            parse_mode="HTML",
        )
        return
    try:
        with keep_typing(chat_id):
            why = generate_why_matters(user_id, consp["topic"], consp["text"])
    except Exception as e:
        print(f"Why-matters generation error: {e}")
        why = ""
    if not (why and why.strip()):
        bot.send_message(
            chat_id,
            "Չստացվեց պատրաստել բացատրությունը։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    send_reply(message, f"🌍 <b>Ինչու է սա կարևոր՝</b>\n\n{why}")


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("why:"))
def cb_why_matters(call):
    bot.answer_callback_query(call.id)
    _send_why_matters(call.message.chat.id, call.from_user.id, call.message)


@bot.message_handler(content_types=["text"], func=is_allowed)
def handle_message(message):
    if not should_respond(message):
        return
    text = (message.text or "").replace(f"@{BOT_INFO.username}", "").strip()
    if not text:
        # Edited messages, forwards, or stickers-with-empty-caption can
        # arrive with no usable text. Don't burn rate-limit / AI calls on them.
        return
    _log(message, "in", text)
    if is_rate_limited(message.from_user.id):
        limit_msg = f"Դու հասել ես օրական {RATE_LIMIT} հաղորդագրության սահմանին։ Փորձիր նորից վաղը 🙂"
        bot.send_message(message.chat.id, limit_msg, parse_mode="HTML")
        _log(message, "out", f"[rate limited] {limit_msg}")
        return
    try:
        with keep_typing(message.chat.id):
            reply = ask_ai(message.from_user.id, text)
        # Only the main (chat) provider produces a conspectus we can quiz
        # on or expand. ArmGPT (hf) is a bare completion model — treat its
        # output as a plain reply with no buttons or caching.
        if get_provider(message.from_user.id) == "main":
            save_last_conspectus(message.from_user.id, text, reply)
            incr_topics(message.from_user.id)
            incr_conspectuses(message.from_user.id)
            record_activity(message.from_user.id)
            send_reply(message, reply, reply_markup=_conspectus_keyboard())
            _award_new_badges(message.chat.id, message.from_user.id)
        else:
            send_reply(message, reply)
        _log(message, "out", reply)
    except Exception as e:
        print(f"Error in handle_message: {e}")
        bot.send_message(
            message.chat.id,
            "Ինչ-որ բան այնպես չգնաց։ Խնդրում եմ՝ փորձիր նորից։",
            parse_mode="HTML",
        )
        _log(message, "out", f"[error] {e}")


# ── Voice messages ──────────────────────────────────────────────────────────
# A Telegram voice note is transcribed with local Whisper and answered like a
# normal text message. The reply is plain text (no voice output); the
# transcription confirmation is appended in Armenian.
@bot.message_handler(content_types=["voice"], func=is_allowed)
def handle_voice(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not whisper_enabled():
        bot.send_message(
            chat_id,
            "Ձայնային հաղորդագրությունների ճանաչումը միացված չէ այս բոտում 🙂",
            parse_mode="HTML",
        )
        return

    # Download the voice file from Telegram.
    try:
        file_info = bot.get_file(message.voice.file_id)
        audio_bytes = bot.download_file(file_info.file_path)
    except Exception as e:
        print(f"Voice download error: {e}")
        bot.send_message(
            chat_id,
            "Չստացվեց ներբեռնել ձայնային հաղորդագրությունը։ Փորձիր նորից 🙂",
            parse_mode="HTML",
        )
        return

    # Transcribe, then treat the text exactly like a typed message.
    with keep_typing(chat_id):
        transcript = transcribe(audio_bytes)
    if not transcript:
        bot.send_message(
            chat_id,
            "Ներողություն, չկարողացա հասկանալ ձայնագրությունը։ Փորձիր նորից 🙂",
            parse_mode="HTML",
        )
        return
    _log(message, "in", f"[voice] {transcript}")

    if is_rate_limited(user_id):
        limit_msg = f"Դու հասել ես օրական {RATE_LIMIT} հաղորդագրության սահմանին։ Փորձիր նորից վաղը 🙂"
        bot.send_message(chat_id, limit_msg, parse_mode="HTML")
        _log(message, "out", f"[rate limited] {limit_msg}")
        return

    try:
        with keep_typing(chat_id):
            reply = ask_ai(user_id, transcript)
        # Reply (already HTML-formatted by the model) plus the transcription
        # confirmation. The transcript is user speech, so escape it — a stray
        # < or & would otherwise break HTML parsing of the whole message.
        full_reply = (
            f"{reply}\n\n🎤 <i>Դու ասացիր՝ «{html.escape(transcript)}»</i>"
        )
        # Same as handle_message: only the main provider yields a conspectus
        # worth caching / quizzing / showing the inline keyboard for.
        if get_provider(user_id) == "main":
            save_last_conspectus(user_id, transcript, reply)
            incr_topics(user_id)
            incr_conspectuses(user_id)
            record_activity(user_id)
            send_reply(message, full_reply, reply_markup=_conspectus_keyboard())
            _award_new_badges(chat_id, user_id)
        else:
            send_reply(message, full_reply)
        _log(message, "out", reply)
    except Exception as e:
        print(f"Error in handle_voice: {e}")
        bot.send_message(
            chat_id,
            "Ինչ-որ բան այնպես չգնաց։ Խնդրում եմ՝ փորձիր նորից։",
            parse_mode="HTML",
        )
        _log(message, "out", f"[error] {e}")
