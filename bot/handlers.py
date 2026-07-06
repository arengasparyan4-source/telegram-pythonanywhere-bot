import hmac
import html
import io
import os
import time
from datetime import datetime
from urllib.parse import quote_plus
from telebot import types
from bot.clients import bot, BOT_INFO, store
from bot.config import (
    ADMIN_PASSWORD,
    COMMIT_SHA,
    GAME_NUM_ROUNDS,
    HF_SPACE_ID,
    HOSTING_LABEL,
    MODEL,
    RATE_LIMIT,
)
from bot.ai import (
    answer_question,
    ask_ai,
    define_word,
    expand_conspectus,
    explain_simply,
    generate_flashcards,
    generate_homework,
    generate_mindmap,
    generate_challenge,
    generate_exam,
    generate_quiz,
    generate_quiz_hint,
    generate_story,
    generate_study_plan,
    generate_summary,
    generate_truefalse,
    generate_why_matters,
    generate_word_game,
    pronounce_term,
    suggest_video_search,
)
from bot.achievements import check_and_award, get_badges
from bot.activity import record_activity
from bot.challenges import (
    clear_challenge_time,
    get_challenge_time,
    set_challenge_time,
)
from bot.conspectus import get_last_conspectus, save_last_conspectus
from bot.drawings import record_drawing
from bot.games import clear_game, get_game, save_game, update_game
from bot.grade import clear_grade, get_grade, set_grade
from bot.helpers import is_allowed, keep_typing, send_reply, should_respond
from bot.history import (
    add_class_answer,
    add_favorite,
    add_score,
    clear_duel,
    clear_group_question,
    clear_history,
    get_admin_stats,
    get_duel,
    get_favorites,
    get_group_question,
    get_leaderboard,
    incr_messages,
    save_duel,
    is_admin,
    get_due_reviews,
    list_weakspots,
    mark_reviewed,
    record_study,
    record_weak_answer,
    set_group_question,
    set_language,
    start_admin_session,
    touch_user,
)
from bot.i18n import help_lines, t
from bot.jokes import jokes_disabled, set_jokes_disabled
from bot.parent import build_report, link_child
from bot.pdf import build_conspectus_pdf
from bot.preferences import get_provider, set_provider
from bot.quiz import clear_quiz, get_quiz, save_quiz, update_quiz
from bot.rate_limit import is_rate_limited
from bot.session import clear_mode, get_mode, set_mode
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
from bot.summary import note_message
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
    # First contact counts as a unique user, even before any message is sent.
    touch_user(message.from_user.id)
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
    user_id = message.from_user.id
    lines = list(help_lines(user_id))
    if HF_SPACE_ID:
        lines.append(t(user_id, "help_model"))
    bot.send_message(
        message.chat.id,
        t(user_id, "help_title") + "\n" + "\n".join(lines),
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
        reply_markup=_conspectus_keyboard(message.from_user.id),
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
def _conspectus_keyboard(user_id: int):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(t(user_id, "btn_quiz"), callback_data="quiz:start"))
    kb.add(types.InlineKeyboardButton(t(user_id, "btn_cards"), callback_data="cards:start"))
    kb.add(types.InlineKeyboardButton(t(user_id, "btn_mindmap"), callback_data="mindmap:show"))
    kb.add(types.InlineKeyboardButton(t(user_id, "btn_story"), callback_data="story:show"))
    kb.add(types.InlineKeyboardButton(t(user_id, "btn_why"), callback_data="why:show"))
    kb.add(types.InlineKeyboardButton(t(user_id, "btn_video"), callback_data="video:show"))
    kb.add(
        types.InlineKeyboardButton(t(user_id, "btn_homework"), callback_data="homework:show")
    )
    kb.add(types.InlineKeyboardButton(t(user_id, "btn_simple"), callback_data="simple:show"))
    kb.add(types.InlineKeyboardButton(t(user_id, "btn_save"), callback_data="fav:save"))
    kb.row(
        types.InlineKeyboardButton(t(user_id, "btn_more"), callback_data="consp:more"),
        types.InlineKeyboardButton(t(user_id, "btn_new"), callback_data="consp:new"),
    )
    kb.add(types.InlineKeyboardButton(t(user_id, "btn_pdf"), callback_data="pdf:export"))
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
    send_reply(message, reply, reply_markup=_conspectus_keyboard(user_id))
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


# ── Interface language (Feature 7) ───────────────────────────────────────────
def _language_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🇦🇲 Հայերեն", callback_data="lang:hy"))
    kb.add(types.InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"))
    kb.add(types.InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"))
    return kb


@bot.message_handler(commands=["language"], func=is_allowed)
def cmd_language(message):
    bot.send_message(
        message.chat.id,
        t(message.from_user.id, "lang_choose"),
        reply_markup=_language_keyboard(),
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("lang:"))
def cb_language(call):
    bot.answer_callback_query(call.id)
    lang = call.data.split(":", 1)[1]
    if not set_language(call.from_user.id, lang):
        bot.send_message(
            call.message.chat.id,
            "Լեզվի ընտրությունը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    # Confirm in the newly chosen language.
    bot.send_message(
        call.message.chat.id,
        t(call.from_user.id, "lang_set"),
        parse_mode="HTML",
    )


# ── Favorite topics (Feature 8) ──────────────────────────────────────────────
def _regenerate_from_topic(chat_id: int, user_id: int, topic: str, message) -> None:
    """Regenerate a conspectus for a saved favorite topic and send it."""
    try:
        with keep_typing(chat_id):
            reply = ask_ai(user_id, topic)
    except Exception as e:
        print(f"Favorite regeneration error: {e}")
        bot.send_message(
            chat_id,
            "Ինչ-որ բան այնպես չգնաց։ Խնդրում եմ՝ փորձիր նորից։",
            parse_mode="HTML",
        )
        return
    save_last_conspectus(user_id, topic, reply)
    incr_topics(user_id)
    incr_conspectuses(user_id)
    record_activity(user_id)
    send_reply(message, reply, reply_markup=_conspectus_keyboard(user_id))
    _award_new_badges(chat_id, user_id)


@bot.message_handler(commands=["favorites"], func=is_allowed)
def cmd_favorites(message):
    favs = get_favorites(message.from_user.id)
    if not favs:
        bot.send_message(
            message.chat.id,
            "⭐ Դեռ սիրելի թեմաներ չունես։ Կոնսպեկտի տակ սեղմիր «⭐ Պահել» "
            "կոճակը՝ թեման այստեղ պահելու համար 🙂",
            parse_mode="HTML",
        )
        return
    kb = types.InlineKeyboardMarkup()
    for i, topic in enumerate(favs):
        kb.add(types.InlineKeyboardButton(f"⭐ {topic[:50]}", callback_data=f"fav:show:{i}"))
    bot.send_message(
        message.chat.id,
        "⭐ <b>Քո սիրելի թեմաները</b>\nՍեղմիր որևէ մեկը՝ նորից կոնսպեկտ ստանալու համար 👇",
        reply_markup=kb,
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("fav:"))
def cb_favorites(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if call.data == "fav:save":
        consp = get_last_conspectus(user_id)
        if not consp:
            bot.send_message(
                chat_id,
                "Դեռ պահելու թեմա չկա 🙂 Նախ ուղարկիր թեման։",
                parse_mode="HTML",
            )
            return
        if add_favorite(user_id, consp["topic"]):
            bot.send_message(
                chat_id,
                f"⭐ Պահեցի «<b>{html.escape(consp['topic'])}</b>» թեման սիրելիների մեջ։ "
                "Տես բոլորը՝ /favorites",
                parse_mode="HTML",
            )
        else:
            bot.send_message(
                chat_id,
                "Այս թեման արդեն սիրելիների մեջ է ⭐ (կամ հիշողությունն անջատված է)։",
                parse_mode="HTML",
            )
        return
    if call.data.startswith("fav:show:"):
        try:
            idx = int(call.data[len("fav:show:") :])
        except ValueError:
            return
        favs = get_favorites(user_id)
        if 0 <= idx < len(favs):
            _regenerate_from_topic(chat_id, user_id, favs[idx], call.message)


# ── Weak spots (Feature 9) ───────────────────────────────────────────────────
@bot.message_handler(commands=["weakspots"], func=is_allowed)
def cmd_weakspots(message):
    topics = list_weakspots(message.from_user.id)
    if not topics:
        bot.send_message(
            message.chat.id,
            "🎯 Առայժմ թույլ կողմեր չկան 👍 Անցիր վիկտորինաներ (/quiz), և եթե ինչ-որ "
            "թեմա դժվար լինի, այն կհայտնվի այստեղ՝ կրկնելու համար։",
            parse_mode="HTML",
        )
        return
    kb = types.InlineKeyboardMarkup()
    for i, topic in enumerate(topics):
        kb.add(
            types.InlineKeyboardButton(f"🎯 {topic[:50]}", callback_data=f"weak:show:{i}")
        )
    bot.send_message(
        message.chat.id,
        "🎯 <b>Քո թույլ կողմերը</b>\nԱյս թեմաները դեռ դժվար են։ Սեղմիր որևէ մեկը՝ "
        "կրկնելու համար, հետո անցիր /quiz՝ դրանք «մարելու» համար 👇",
        reply_markup=kb,
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("weak:"))
def cb_weakspots(call):
    bot.answer_callback_query(call.id)
    if not call.data.startswith("weak:show:"):
        return
    try:
        idx = int(call.data[len("weak:show:") :])
    except ValueError:
        return
    topics = list_weakspots(call.from_user.id)
    if 0 <= idx < len(topics):
        _regenerate_from_topic(
            call.message.chat.id, call.from_user.id, topics[idx], call.message
        )


# ── Spaced repetition (Feature 7) ────────────────────────────────────────────
# /review lists the topics whose spaced-repetition review is due now (schedule
# in bot/history.py: due after 1 → 3 → 7 days, advancing a stage per review).
# record_study() is called from handle_message / handle_voice whenever a fresh
# conspectus is generated, so every studied topic enters the schedule. Tapping
# a due topic marks it reviewed (advancing its stage) and re-shows its
# conspectus so the student can revise on the spot.
@bot.message_handler(commands=["review"], func=is_allowed)
def cmd_review(message):
    topics = get_due_reviews(message.from_user.id)
    if not topics:
        bot.send_message(
            message.chat.id,
            "🧠 Հիմա կրկնելու թեմա չկա 👍 Ուղարկիր դասագրքի անունը կամ թեման, "
            "և մի քանի օրից ես կհիշեցնեմ, որ ժամանակն է կրկնել այն։",
            parse_mode="HTML",
        )
        return
    kb = types.InlineKeyboardMarkup()
    for i, topic in enumerate(topics):
        kb.add(
            types.InlineKeyboardButton(
                f"🧠 {topic[:50]}", callback_data=f"review:show:{i}"
            )
        )
    bot.send_message(
        message.chat.id,
        "🧠 <b>Կրկնության ժամանակն է</b>\nԱյս թեմաներն արժե հիմա կրկնել՝ որ լավ "
        "հիշվեն։ Սեղմիր որևէ մեկը՝ նորից անցնելու համար 👇",
        reply_markup=kb,
        parse_mode="HTML",
    )


@bot.callback_query_handler(
    func=lambda c: bool(c.data) and c.data.startswith("review:")
)
def cb_review(call):
    bot.answer_callback_query(call.id)
    if not call.data.startswith("review:show:"):
        return
    try:
        idx = int(call.data[len("review:show:") :])
    except ValueError:
        return
    topics = get_due_reviews(call.from_user.id)
    if 0 <= idx < len(topics):
        # Advance the spaced-repetition stage first (so a re-shown topic isn't
        # immediately due again), then re-show its conspectus for revision.
        mark_reviewed(call.from_user.id, topics[idx])
        _regenerate_from_topic(
            call.message.chat.id, call.from_user.id, topics[idx], call.message
        )


# ── Admin statistics (/admin) ────────────────────────────────────────────────
# Password-gated, bot-wide usage dashboard. The password lives only in the
# ADMIN_PASSWORD env var; a correct entry starts a time-limited admin session
# (bot/history.py) so it isn't re-typed on every /admin. Deliberately NOT
# listed in /help — it's an operator tool, not a student command.
def _show_admin_stats(chat_id: int) -> None:
    s = get_admin_stats()
    bot.send_message(
        chat_id,
        "🔐 <b>Ադմինի վիճակագրություն</b>\n\n"
        f"👥 Օգտատերեր (ընդամենը)՝ <b>{s['total_users']}</b>\n"
        f"🟢 Ակտիվ այսօր (վերջին 24ժ)՝ <b>{s['active_today']}</b>\n"
        f"📆 Ակտիվ այս շաբաթ (վերջին 7 օր)՝ <b>{s['active_week']}</b>\n"
        f"💬 Մշակված հաղորդագրություններ՝ <b>{s['total_messages']}</b>\n"
        f"📝 Ստեղծված կոնսպեկտներ՝ <b>{s['total_conspectuses']}</b>",
        parse_mode="HTML",
    )


def _password_ok(text: str) -> bool:
    """Constant-time password check. Always False when no password is set."""
    if not ADMIN_PASSWORD:
        return False
    return hmac.compare_digest((text or "").strip().encode(), ADMIN_PASSWORD.encode())


@bot.message_handler(commands=["admin"], func=is_allowed)
def cmd_admin(message):
    user_id = message.from_user.id
    if not ADMIN_PASSWORD:
        # Fail-closed: no password configured means the feature is off.
        bot.send_message(message.chat.id, "Ադմինի ռեժիմն անջատված է 🙂", parse_mode="HTML")
        return
    if is_admin(user_id):
        # Live session — skip the password prompt.
        _show_admin_stats(message.chat.id)
        return
    if not set_mode(user_id, "admin_login"):
        bot.send_message(
            message.chat.id,
            "Ադմինի ռեժիմը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        message.chat.id, "🔐 Մուտքագրիր ադմինի գաղտնաբառը՝", parse_mode="HTML"
    )


def _handle_admin_login(message, text: str) -> None:
    """Verify the typed admin password and either open or reject the session."""
    user_id = message.from_user.id
    clear_mode(user_id)
    # Best-effort: delete the message containing the typed password so it
    # doesn't linger in the chat history.
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass
    if _password_ok(text):
        start_admin_session(user_id)
        bot.send_message(message.chat.id, "✅ Մուտքը հաջողվեց։", parse_mode="HTML")
        _show_admin_stats(message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "❌ Սխալ գաղտնաբառ։ Մուտքը մերժված է։",
            parse_mode="HTML",
        )


# ── Group / class mode (Feature 4) ───────────────────────────────────────────
# The bot works in class group chats. To read students' answers, replies to
# the bot's question are always delivered by Telegram; to also read plain
# (non-reply) messages, group privacy mode must be DISABLED in BotFather:
#   BotFather → /setprivacy → <this bot> → Disable
# In groups the bot stays quiet unless it's a command, a reply to the bot, an
# @mention, or an answer to an active /askclass question — so it never spams.
def _is_group(message) -> bool:
    return getattr(message.chat, "type", "") in ("group", "supergroup")


def _display_name(user) -> str:
    return (
        getattr(user, "first_name", None)
        or getattr(user, "username", None)
        or f"user{getattr(user, 'id', '')}"
    )


def _mentions_bot(message) -> bool:
    return f"@{BOT_INFO.username}" in (message.text or "")


def _is_reply_to_bot(message) -> bool:
    reply = getattr(message, "reply_to_message", None)
    return bool(
        reply
        and getattr(reply, "from_user", None)
        and reply.from_user.id == BOT_INFO.id
    )


def _is_group_admin(chat_id: int, user_id: int) -> bool:
    """True if the user is the group's creator or an administrator.

    Best-effort: on any API error (e.g. the bot can't query members) we
    fail closed and treat the user as a non-admin.
    """
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return getattr(member, "status", "") in ("creator", "administrator")
    except Exception as e:
        print(f"get_chat_member error: {e}")
        return False


@bot.message_handler(commands=["askclass"], func=is_allowed)
def cmd_askclass(message):
    if not _is_group(message):
        bot.send_message(
            message.chat.id,
            "Այս հրամանն աշխատում է միայն խմբային զրույցում 👥",
            parse_mode="HTML",
        )
        return
    if not _is_group_admin(message.chat.id, message.from_user.id):
        bot.send_message(
            message.chat.id,
            "Միայն ուսուցիչը (խմբի ադմինը) կարող է հարց տալ դասարանին 🙂",
            parse_mode="HTML",
        )
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        bot.send_message(
            message.chat.id,
            "Գրիր հարցը՝ <code>/askclass հարցը</code>",
            parse_mode="HTML",
        )
        return
    question = parts[1].strip()
    if not set_group_question(message.chat.id, question, message.from_user.id):
        bot.send_message(
            message.chat.id,
            "Խմբային ռեժիմը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        message.chat.id,
        f"👥 <b>Հարց դասարանին</b>\n\n{html.escape(question)}\n\n"
        "Պատասխանելու համար <b>պատասխանի՛ր (reply)</b> այս հաղորդագրությանը 🙂",
        parse_mode="HTML",
    )


@bot.message_handler(commands=["answers"], func=is_allowed)
def cmd_answers(message):
    if not _is_group(message):
        bot.send_message(
            message.chat.id,
            "Այս հրամանն աշխատում է միայն խմբային զրույցում 👥",
            parse_mode="HTML",
        )
        return
    if not _is_group_admin(message.chat.id, message.from_user.id):
        bot.send_message(
            message.chat.id,
            "Միայն ուսուցիչը կարող է տեսնել պատասխանները 🙂",
            parse_mode="HTML",
        )
        return
    data = get_group_question(message.chat.id)
    if not data:
        bot.send_message(
            message.chat.id, "Ակտիվ հարց չկա 🙂", parse_mode="HTML"
        )
        return
    answers = data.get("answers", [])
    lines = [f"👥 <b>Հարց.</b> {html.escape(data['question'])}", ""]
    if not answers:
        lines.append("Դեռ պատասխաններ չկան։")
    else:
        lines.append(f"📥 <b>Ստացված պատասխաններ ({len(answers)})</b>՝")
        lines += [
            f"• <b>{html.escape(str(a['name']))}</b>՝ {html.escape(str(a['text']))}"
            for a in answers
        ]
    clear_group_question(message.chat.id)
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML")


def _handle_group_message(message, text: str) -> bool:
    """Handle a non-command text message in a group.

    Returns True if consumed (answer collected, or ignored to avoid spam),
    False to fall through to normal AI handling (only when the bot is
    @mentioned or the message replies to the bot).
    """
    chat_id = message.chat.id
    if get_group_question(chat_id):
        # A class question is live — treat this as a student's answer.
        name = _display_name(message.from_user)
        add_class_answer(chat_id, message.from_user.id, name, text)
        bot.send_message(
            chat_id,
            f"✅ Ստացա քո պատասխանը, <b>{html.escape(name)}</b> 🙂",
            parse_mode="HTML",
        )
        return True
    # No active question: engage only when directly addressed.
    if _is_reply_to_bot(message) or _mentions_bot(message):
        return False
    return True  # ignore ordinary group chatter


# ── Leaderboard (Feature 5) ──────────────────────────────────────────────────
@bot.message_handler(commands=["leaderboard"], func=is_allowed)
def cmd_leaderboard(message):
    board = get_leaderboard(message.chat.id)
    if not board:
        bot.send_message(
            message.chat.id,
            "🏆 Դեռ միավորներ չկան։ Անցիր վիկտորինաներ, խաղեր կամ /duel՝ "
            "միավորներ վաստակելու համար 🙂",
            parse_mode="HTML",
        )
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>Առաջատարների աղյուսակ</b>", ""]
    for i, (name, points) in enumerate(board[:20]):
        prefix = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{prefix} <b>{html.escape(str(name))}</b> — {points}")
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML")


# ── Duel: two-player quiz race (Feature 6) ───────────────────────────────────
# One duel per chat, keyed by chat_id in bot/history.py. Both players answer
# the SAME questions in synchronized rounds: a round advances only once every
# participant has answered it, then the correct option is revealed. Winner is
# highest score, ties broken by total answer time. Dropouts are handled by
# /endduel (finalizes with current scores) and by the state's TTL.
def _start_duel(chat_id: int, starter, topic: str, source: str) -> None:
    if get_duel(chat_id):
        bot.send_message(
            chat_id,
            "Այս զրույցում արդեն ակտիվ մենամարտ կա 🙂 Ավարտիր այն /endduel-ով։",
            parse_mode="HTML",
        )
        return
    try:
        with keep_typing(chat_id):
            questions = generate_quiz(starter.id, source)
    except Exception as e:
        print(f"Duel generation error: {e}")
        questions = []
    if not questions:
        bot.send_message(
            chat_id,
            "Չստացվեց պատրաստել մենամարտը։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    now = int(time.time())
    state = {
        "topic": topic,
        "questions": questions,
        "status": "waiting",
        "cur": 0,
        "round_ts": now,
        "starter": starter.id,
        "players": {
            str(starter.id): {
                "name": _display_name(starter),
                "score": 0,
                "answered": [],
                "time": 0,
            }
        },
    }
    if not save_duel(chat_id, state):
        bot.send_message(
            chat_id,
            "Մենամարտը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🤝 Միանալ", callback_data="duel:join"))
    bot.send_message(
        chat_id,
        f"🤝 <b>Մենամարտ՝ {html.escape(topic)}</b>\n\n"
        f"<b>{html.escape(_display_name(starter))}</b>-ը մարտահրավեր է նետում։ "
        "Ո՞վ է միանում 👇 (կամ գրիր /join)",
        reply_markup=kb,
        parse_mode="HTML",
    )


def _join_duel(chat_id: int, user) -> None:
    state = get_duel(chat_id)
    if not state or state["status"] != "waiting":
        bot.send_message(
            chat_id, "Միանալու ակտիվ մենամարտ չկա 🙂", parse_mode="HTML"
        )
        return
    uid = str(user.id)
    if uid in state["players"]:
        bot.send_message(chat_id, "Դու արդեն մասնակից ես 🙂", parse_mode="HTML")
        return
    if len(state["players"]) >= 2:
        bot.send_message(chat_id, "Մենամարտն արդեն լրացված է 🙂", parse_mode="HTML")
        return
    state["players"][uid] = {
        "name": _display_name(user),
        "score": 0,
        "answered": [],
        "time": 0,
    }
    state["status"] = "active"
    state["round_ts"] = int(time.time())
    save_duel(chat_id, state)
    bot.send_message(
        chat_id,
        f"<b>{html.escape(_display_name(user))}</b>-ը միացավ։ Սկսում ենք 🤝",
        parse_mode="HTML",
    )
    _send_duel_question(chat_id, state)


def _send_duel_question(chat_id: int, state: dict) -> None:
    cur, questions = state["cur"], state["questions"]
    q = questions[cur]
    kb = types.InlineKeyboardMarkup()
    for i, opt in enumerate(q["options"]):
        kb.add(types.InlineKeyboardButton(opt, callback_data=f"duelans:{cur}:{i}"))
    bot.send_message(
        chat_id,
        f"🤝 <b>Հարց {cur + 1}/{len(questions)}</b>\n\n{html.escape(q['q'])}",
        reply_markup=kb,
        parse_mode="HTML",
    )


def _handle_duel_answer(chat_id: int, user, data: str) -> None:
    state = get_duel(chat_id)
    if not state or state["status"] != "active":
        return
    try:
        _, qidx_s, opt_s = data.split(":")
        qidx, opt = int(qidx_s), int(opt_s)
    except ValueError:
        return
    uid = str(user.id)
    if uid not in state["players"]:
        return  # a non-participant tapped the buttons — ignore
    if qidx != state["cur"]:
        return  # stale tap on a past round
    player = state["players"][uid]
    if qidx in player["answered"]:
        return  # this player already answered the current question
    player["answered"].append(qidx)
    now = int(time.time())
    player["time"] = player.get("time", 0) + max(0, now - state.get("round_ts", now))
    q = state["questions"][qidx]
    if opt == q["correct"]:
        player["score"] += 1
    bot.send_message(
        chat_id,
        f"✅ <b>{html.escape(player['name'])}</b>-ը պատասխանեց",
        parse_mode="HTML",
    )
    # Advance only when every participant has answered this round.
    if all(qidx in p["answered"] for p in state["players"].values()):
        correct_text = q["options"][q["correct"]]
        bot.send_message(
            chat_id,
            f"➡️ Ճիշտ պատասխանը՝ «<b>{html.escape(correct_text)}</b>»",
            parse_mode="HTML",
        )
        state["cur"] += 1
        state["round_ts"] = int(time.time())
        if state["cur"] >= len(state["questions"]):
            _finish_duel(chat_id, state)
        else:
            save_duel(chat_id, state)
            _send_duel_question(chat_id, state)
    else:
        save_duel(chat_id, state)


def _finish_duel(chat_id: int, state: dict) -> None:
    players = state["players"]
    # Rank by score desc, then by total answer time asc (faster wins ties).
    ranked = sorted(
        players.items(), key=lambda kv: (-kv[1]["score"], kv[1].get("time", 0))
    )
    clear_duel(chat_id)
    lines = ["🤝 <b>Մենամարտն ավարտվեց։</b>", ""]
    for _uid, p in ranked:
        lines.append(f"• <b>{html.escape(p['name'])}</b> — {p['score']} միավոր")
    lines.append("")
    if len(ranked) >= 2 and ranked[0][1]["score"] == ranked[1][1]["score"]:
        lines.append("Ոչ-ոքի՛ 🤝 Երկուսդ էլ հիանալի էիք։")
    else:
        win_uid, win = ranked[0]
        lines.append(f"🏆 Հաղթող՝ <b>{html.escape(win['name'])}</b> 🎉")
        # Reward the winner on the chat's leaderboard.
        add_score(chat_id, int(win_uid), win["name"], 3)
    bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")


@bot.message_handler(commands=["duel"], func=is_allowed)
def cmd_duel(message):
    chat_id, user_id = message.chat.id, message.from_user.id
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        topic = parts[1].strip()
        _start_duel(chat_id, message.from_user, topic, topic)
        return
    consp = get_last_conspectus(user_id)
    if consp:
        _start_duel(chat_id, message.from_user, consp["topic"], consp["text"])
        return
    if not set_mode(user_id, "duel_topic"):
        bot.send_message(
            chat_id,
            "Մենամարտը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        chat_id,
        "🤝 Ո՞ր թեմայով մենամարտենք։ Գրիր թեման, և ես կպատրաստեմ հարցերը 🙂",
        parse_mode="HTML",
    )


@bot.message_handler(commands=["join"], func=is_allowed)
def cmd_join(message):
    _join_duel(message.chat.id, message.from_user)


@bot.message_handler(commands=["endduel"], func=is_allowed)
def cmd_endduel(message):
    state = get_duel(message.chat.id)
    if not state:
        bot.send_message(
            message.chat.id, "Ակտիվ մենամարտ չկա 🙂", parse_mode="HTML"
        )
        return
    if state["status"] == "waiting":
        clear_duel(message.chat.id)
        bot.send_message(
            message.chat.id, "Մենամարտը չեղարկվեց 🙂", parse_mode="HTML"
        )
        return
    # Active duel ended early (e.g. a player dropped out): settle on scores.
    _finish_duel(message.chat.id, state)


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("duel"))
def cb_duel(call):
    bot.answer_callback_query(call.id)
    if call.data == "duel:join":
        _join_duel(call.message.chat.id, call.from_user)
    elif call.data.startswith("duelans:"):
        _handle_duel_answer(call.message.chat.id, call.from_user, call.data)


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
    save_quiz(user_id, questions, consp["topic"])
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
    # Feature 2: a hint button that guides without revealing the answer.
    kb.add(types.InlineKeyboardButton("💡 Հուշում", callback_data="qhint"))
    bot.send_message(
        chat_id,
        f"❓ <b>Հարց {idx + 1}/{len(questions)}</b>\n\n{html.escape(q['q'])}",
        reply_markup=kb,
        parse_mode="HTML",
    )


def _send_quiz_hint(chat_id: int, user_id: int) -> None:
    """Give a hint for the quiz question currently being asked (Feature 2)."""
    state = get_quiz(user_id)
    if not state:
        return
    idx, questions = state["idx"], state["questions"]
    if idx >= len(questions):
        return
    q = questions[idx]
    try:
        with keep_typing(chat_id):
            hint = generate_quiz_hint(user_id, q["q"], q["options"])
    except Exception as e:
        print(f"Quiz hint error: {e}")
        hint = ""
    if not (hint and hint.strip()):
        bot.send_message(
            chat_id, "Չստացվեց հուշում տալ։ Փորձիր նորից 🙂", parse_mode="HTML"
        )
        return
    bot.send_message(chat_id, f"💡 <b>Հուշում.</b> {html.escape(hint)}", parse_mode="HTML")


@bot.callback_query_handler(func=lambda c: c.data == "qhint")
def cb_quiz_hint(call):
    bot.answer_callback_query(call.id)
    _send_quiz_hint(call.message.chat.id, call.from_user.id)


def _handle_quiz_answer(chat_id: int, user_id: int, data: str) -> bool:
    """Grade a tapped option, give Armenian feedback, advance the quiz.

    Returns True if the answer was correct (so the caller can award a
    leaderboard point), False otherwise or on a stale/invalid tap.
    """
    state = get_quiz(user_id)
    if not state:
        return False
    try:
        _, qidx_s, opt_s = data.split(":")
        qidx, opt = int(qidx_s), int(opt_s)
    except ValueError:
        return False
    # Ignore taps on an old question (e.g. the student scrolled up and
    # re-tapped a previous question's buttons).
    if qidx != state["idx"]:
        return False
    q = state["questions"][qidx]
    correct = q["correct"]
    explanation = q.get("explanation", "")
    is_correct = opt == correct
    if is_correct:
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
    # Feature 9: attribute right/wrong to the quiz's topic so persistently
    # missed topics surface in /weakspots (and clear once mastered).
    record_weak_answer(user_id, state.get("topic", ""), is_correct)
    state["idx"] += 1
    update_quiz(user_id, state)
    _send_quiz_question(chat_id, user_id)
    return is_correct


def _award_point(chat_id: int, user) -> None:
    """Give a user one leaderboard point in the current chat (Feature 5)."""
    add_score(chat_id, user.id, _display_name(user), 1)


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
        if _handle_quiz_answer(chat_id, user_id, call.data):
            _award_point(chat_id, call.from_user)


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


# ── Video suggestion (Feature 10) ────────────────────────────────────────────
# The "🎥 Վիդեո" button under a conspectus suggests an educational YouTube
# search for the topic. We do NOT scrape or call the YouTube API — we ask the
# model for good child-friendly search terms and build a plain search URL the
# student can tap. Falls back to the raw topic if the model doesn't answer.
def _send_video_suggestion(chat_id: int, user_id: int, message) -> None:
    consp = get_last_conspectus(user_id)
    if not consp:
        bot.send_message(
            chat_id,
            "Նախ ուղարկիր դասագրքի անունը կամ թեման, որ պատրաստեմ կոնսպեկտ, "
            "հետո կառաջարկեմ վիդեո 🎥",
            parse_mode="HTML",
        )
        return
    try:
        with keep_typing(chat_id):
            query = suggest_video_search(user_id, consp["topic"])
    except Exception as e:
        print(f"Video suggestion error: {e}")
        query = consp["topic"]
    url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
    send_reply(
        message,
        f"🎥 <b>Վիդեո՝ {html.escape(consp['topic'])}</b>\n\n"
        f"Որոնիր YouTube-ում՝ <b>{html.escape(query)}</b>\n\n"
        f'<a href="{html.escape(url)}">▶️ Բացիր որոնումը YouTube-ում</a>',
    )


@bot.callback_query_handler(
    func=lambda c: bool(c.data) and c.data.startswith("video:")
)
def cb_video(call):
    bot.answer_callback_query(call.id)
    _send_video_suggestion(call.message.chat.id, call.from_user.id, call.message)


# ── Homework exercises (Feature 1) ───────────────────────────────────────────
def _send_homework(chat_id: int, user_id: int, message) -> None:
    """Generate practical exercises from the last conspectus and send them."""
    consp = get_last_conspectus(user_id)
    if not consp:
        bot.send_message(
            chat_id,
            "Նախ ուղարկիր դասագրքի անունը կամ թեման, որ պատրաստեմ կոնսպեկտ, "
            "հետո կտամ տնային առաջադրանք 📝",
            parse_mode="HTML",
        )
        return
    try:
        with keep_typing(chat_id):
            homework = generate_homework(user_id, consp["topic"], consp["text"])
    except Exception as e:
        print(f"Homework generation error: {e}")
        homework = ""
    if not (homework and homework.strip()):
        bot.send_message(
            chat_id,
            "Չստացվեց պատրաստել առաջադրանքը։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    send_reply(message, f"📝 <b>Տնային առաջադրանք</b>\n\n{homework}")


@bot.callback_query_handler(
    func=lambda c: bool(c.data) and c.data.startswith("homework:")
)
def cb_homework(call):
    bot.answer_callback_query(call.id)
    _send_homework(call.message.chat.id, call.from_user.id, call.message)


# ── Explain simply / like I'm 5 (Feature 2) ──────────────────────────────────
def _send_simple(chat_id: int, user_id: int, message) -> None:
    """Re-explain the last conspectus's topic in the simplest possible way."""
    consp = get_last_conspectus(user_id)
    if not consp:
        bot.send_message(
            chat_id,
            "Նախ ուղարկիր դասագրքի անունը կամ թեման, որ պատրաստեմ կոնսպեկտ, "
            "հետո կբացատրեմ ամենապարզ ձևով 🔍",
            parse_mode="HTML",
        )
        return
    try:
        with keep_typing(chat_id):
            simple = explain_simply(user_id, consp["topic"], consp["text"])
    except Exception as e:
        print(f"Simple-explain generation error: {e}")
        simple = ""
    if not (simple and simple.strip()):
        bot.send_message(
            chat_id,
            "Չստացվեց պատրաստել բացատրությունը։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    send_reply(message, f"🔍 <b>Պարզ բացատրություն</b>\n\n{simple}")


@bot.callback_query_handler(
    func=lambda c: bool(c.data) and c.data.startswith("simple:")
)
def cb_simple(call):
    bot.answer_callback_query(call.id)
    _send_simple(call.message.chat.id, call.from_user.id, call.message)


# ── Game mode (Feature 4) ────────────────────────────────────────────────────
# Two AI-generated games. "tf" (Ճիշտ/Սխալ) is button-driven like the quiz;
# "word" (Գուշակիր բառը) shows a hint and reads the student's typed guess via
# the "game_word" conversation mode. Score is tracked in bot/games.py state.
def _game_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Ճիշտ/Սխալ", callback_data="game:tf"))
    kb.add(types.InlineKeyboardButton("🔤 Գուշակիր բառը", callback_data="game:word"))
    return kb


@bot.message_handler(commands=["game"], func=is_allowed)
def cmd_game(message):
    if store is None:
        bot.send_message(
            message.chat.id,
            "Խաղերը հասանելի են միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        message.chat.id,
        "🎮 <b>Խաղ ռեժիմ</b>\n\nԸնտրիր խաղը 👇",
        reply_markup=_game_keyboard(),
        parse_mode="HTML",
    )


def _start_game(chat_id: int, user_id: int, kind: str, source: str) -> None:
    """Generate a game of ``kind`` from ``source`` text and ask the first round."""
    try:
        with keep_typing(chat_id):
            if kind == "tf":
                rounds = generate_truefalse(user_id, source, GAME_NUM_ROUNDS)
            else:
                rounds = generate_word_game(user_id, source, GAME_NUM_ROUNDS)
    except Exception as e:
        print(f"Game generation error: {e}")
        rounds = []
    if not rounds or not save_game(user_id, kind, rounds):
        clear_mode(user_id)
        bot.send_message(
            chat_id,
            "Չստացվեց պատրաստել խաղը։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    bot.send_message(chat_id, "🎮 Խաղը սկսվեց։ Հաջողությո՛ւն 🍀", parse_mode="HTML")
    _send_game_round(chat_id, user_id)


def _send_game_round(chat_id: int, user_id: int) -> None:
    """Send the current game round, or finish if the deck is exhausted."""
    state = get_game(user_id)
    if not state:
        return
    idx, rounds = state["idx"], state["rounds"]
    if idx >= len(rounds):
        _finish_game(chat_id, user_id, state)
        return
    r = rounds[idx]
    header = f"🎮 {idx + 1}/{len(rounds)}"
    if state["kind"] == "tf":
        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton("✅ Ճիշտ", callback_data=f"tfans:{idx}:1"),
            types.InlineKeyboardButton("❌ Սխալ", callback_data=f"tfans:{idx}:0"),
        )
        bot.send_message(
            chat_id,
            f"{header}\n\n{html.escape(r['s'])}\n\nՃի՞շտ է, թե՞ սխալ։",
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:  # word
        set_mode(user_id, "game_word")
        bot.send_message(
            chat_id,
            f"{header}\n\n🔤 <b>Գուշակիր բառը</b>\nԱկնարկ՝ {html.escape(r['hint'])}\n\n"
            "Գրիր քո տարբերակը 🙂",
            parse_mode="HTML",
        )


def _handle_tf_answer(chat_id: int, user_id: int, data: str) -> bool:
    """Grade a tapped True/False button and advance the game.

    Returns True if the tap was a correct answer (so the caller can award a
    leaderboard point), False otherwise or on a stale/invalid tap.
    """
    state = get_game(user_id)
    if not state or state["kind"] != "tf":
        return False
    try:
        _, idx_s, val_s = data.split(":")
        idx, said_true = int(idx_s), int(val_s) == 1
    except ValueError:
        return False
    if idx != state["idx"]:
        return False  # stale tap on an earlier round
    r = state["rounds"][idx]
    why = r.get("why", "")
    is_correct = said_true == r["ok"]
    if is_correct:
        state["score"] += 1
        bot.send_message(
            chat_id, f"✅ <b>Ճիշտ է։</b> {html.escape(why)}".rstrip(), parse_mode="HTML"
        )
    else:
        truth = "ճիշտ" if r["ok"] else "սխալ"
        bot.send_message(
            chat_id,
            f"❌ Իրականում այդ պնդումը <b>{truth}</b> է։ {html.escape(why)}".rstrip(),
            parse_mode="HTML",
        )
    state["idx"] += 1
    update_game(user_id, state)
    _send_game_round(chat_id, user_id)
    return is_correct


def _handle_word_guess(message, text: str) -> bool:
    """Check the student's typed guess in a "guess the word" game.

    Returns True (message consumed) whenever a word game is active; False so
    the message falls through to normal handling if there is no game.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    state = get_game(user_id)
    if not state or state["kind"] != "word":
        clear_mode(user_id)
        return False
    clear_mode(user_id)  # this guess consumes the mode; next round re-sets it
    idx = state["idx"]
    r = state["rounds"][idx]
    word = r["word"]
    if _normalize_guess(text) == _normalize_guess(word):
        state["score"] += 1
        _award_point(chat_id, message.from_user)
        bot.send_message(
            chat_id, f"✅ <b>Ճիշտ է՝ {html.escape(word)}</b> 🎉", parse_mode="HTML"
        )
    else:
        bot.send_message(
            chat_id,
            f"❌ Ճիշտ պատասխանն էր՝ «<b>{html.escape(word)}</b>»։",
            parse_mode="HTML",
        )
    state["idx"] += 1
    update_game(user_id, state)
    _send_game_round(chat_id, user_id)
    return True


def _normalize_guess(s: str) -> str:
    """Case/space/punctuation-insensitive form for comparing word guesses."""
    return "".join(ch for ch in (s or "").lower().strip() if ch.isalnum())


def _finish_game(chat_id: int, user_id: int, state: dict) -> None:
    score, total = state["score"], len(state["rounds"])
    clear_game(user_id)
    clear_mode(user_id)
    record_activity(user_id)
    bot.send_message(
        chat_id,
        f"🎮 <b>Խաղն ավարտվեց։</b> Դու հավաքեցիր <b>{score}/{total}</b> միավոր 🎉",
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("game:"))
def cb_game(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    kind = "tf" if call.data == "game:tf" else "word"
    consp = get_last_conspectus(user_id)
    if consp:
        _start_game(chat_id, user_id, kind, consp["text"])
        return
    # No conspectus yet — ask the student for a topic to build the game on.
    if not set_mode(user_id, "game_topic", {"kind": kind}):
        bot.send_message(
            chat_id,
            "Խաղերը հասանելի են միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        chat_id,
        "Ո՞ր թեմայով խաղանք։ Գրիր թեման, և ես կպատրաստեմ խաղը 🙂",
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("tfans:"))
def cb_tf_answer(call):
    bot.answer_callback_query(call.id)
    if _handle_tf_answer(call.message.chat.id, call.from_user.id, call.data):
        _award_point(call.message.chat.id, call.from_user)


# ── Daily challenge (Feature 5) ──────────────────────────────────────────────
def _send_challenge_now(chat_id: int, user_id: int) -> None:
    """Generate one educational challenge and send it right away."""
    try:
        with keep_typing(chat_id):
            text = generate_challenge(user_id)
    except Exception as e:
        print(f"Challenge generation error: {e}")
        text = ""
    if not (text and text.strip()):
        bot.send_message(
            chat_id,
            "Չստացվեց պատրաստել մարտահրավերը։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    bot.send_message(chat_id, f"🏅 <b>Օրվա մարտահրավեր</b>\n\n{text}", parse_mode="HTML")


@bot.message_handler(commands=["challenge"], func=is_allowed)
def cmd_challenge(message):
    user_id = message.from_user.id
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1:
        # No argument: send a challenge right now.
        _send_challenge_now(message.chat.id, user_id)
        return
    arg = parts[1].strip().lower()
    if arg in ("off", "անջատել"):
        clear_challenge_time(user_id)
        bot.send_message(
            message.chat.id, "🔕 Օրվա մարտահրավերն անջատված է։", parse_mode="HTML"
        )
        return
    hhmm = normalize_time(arg)
    if not hhmm:
        bot.send_message(
            message.chat.id,
            "Սխալ ձևաչափ։ Գրիր՝ /challenge (հիմա ստանալու համար), "
            "/challenge 09:00 (ամեն օր ստանալու համար) կամ /challenge off։",
            parse_mode="HTML",
        )
        return
    if not set_challenge_time(user_id, hhmm):
        bot.send_message(
            message.chat.id,
            "Ամենօրյա մարտահրավերը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        message.chat.id,
        f"🏅 Ամեն օր ժամը <b>{html.escape(hhmm)}</b>-ին կուղարկեմ քեզ նոր մարտահրավեր 🙂",
        parse_mode="HTML",
    )


# ── Ask me anything (Feature 6) ──────────────────────────────────────────────
def _ask_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🚪 Ավարտել հարցերը", callback_data="ask:stop"))
    return kb


@bot.message_handler(commands=["ask"], func=is_allowed)
def cmd_ask(message):
    if not set_mode(message.from_user.id, "ask"):
        bot.send_message(
            message.chat.id,
            "Հարցերի ռեժիմը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        message.chat.id,
        "🤔 <b>Հարցրու ինձ ինչ ուզես</b>\n\n"
        "Գրիր ցանկացած հարց ցանկացած թեմայով, և ես կպատասխանեմ պարզ ու հասկանալի։ "
        "Ավարտելու համար սեղմիր կոճակը ներքևում 👇",
        reply_markup=_ask_keyboard(),
        parse_mode="HTML",
    )


def _handle_ask(message, text: str) -> None:
    """Answer a question while the student is in free Q&A mode."""
    try:
        with keep_typing(message.chat.id):
            answer = answer_question(message.from_user.id, text)
    except Exception as e:
        print(f"Ask-mode generation error: {e}")
        answer = ""
    if not (answer and answer.strip()):
        bot.send_message(
            message.chat.id,
            "Չստացվեց պատասխանել։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    # Keep the student in ask-mode (refresh its TTL) and re-show the exit button.
    set_mode(message.from_user.id, "ask")
    send_reply(message, answer, reply_markup=_ask_keyboard())


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("ask:"))
def cb_ask(call):
    bot.answer_callback_query(call.id)
    if call.data == "ask:stop":
        clear_mode(call.from_user.id)
        bot.send_message(
            call.message.chat.id,
            "✅ Ավարտեցինք հարցերի ռեժիմը։ Ուղարկիր թեմա՝ նոր կոնսպեկտ ստանալու համար 🙂",
            parse_mode="HTML",
        )


# ── Auto summary (Feature 8) ─────────────────────────────────────────────────
# After a long study session the bot offers a "📌 Ամփոփում" recap (the offer is
# posted from handle_message every SUMMARY_EVERY messages, tracked in
# bot/summary.py). Tapping the button — or running /summary anytime — recaps
# the recent conversation via ask_ai/generate_summary.
def _summary_offer_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📌 Ամփոփում", callback_data="summary:make"))
    return kb


def _offer_summary(chat_id: int) -> None:
    """Post the optional 'want a recap?' prompt with the summary button."""
    bot.send_message(
        chat_id,
        "📌 Մենք արդեն շատ բան անցանք 🙂 Ուզո՞ւմ ես այս սեսիայի կարճ ամփոփումը։",
        reply_markup=_summary_offer_keyboard(),
        parse_mode="HTML",
    )


def _send_summary(chat_id: int, user_id: int, message) -> None:
    """Generate and send a recap of the student's recent study session."""
    try:
        with keep_typing(chat_id):
            summary = generate_summary(user_id)
    except Exception as e:
        print(f"Summary generation error: {e}")
        summary = ""
    if not (summary and summary.strip()):
        bot.send_message(
            chat_id,
            "Դեռ ամփոփելու բան չկա 🙂 Ուղարկիր թեմա, և մի քիչ սովորելուց հետո "
            "կպատրաստեմ ամփոփում։",
            parse_mode="HTML",
        )
        return
    send_reply(message, f"📌 <b>Այս սեսիայի ամփոփումը</b>\n\n{summary}")


@bot.message_handler(commands=["summary"], func=is_allowed)
def cmd_summary(message):
    _send_summary(message.chat.id, message.from_user.id, message)


@bot.callback_query_handler(
    func=lambda c: bool(c.data) and c.data.startswith("summary:")
)
def cb_summary(call):
    bot.answer_callback_query(call.id)
    _send_summary(call.message.chat.id, call.from_user.id, call.message)


# ── Exam prep (Feature 1 / smart-learning) ───────────────────────────────────
@bot.message_handler(commands=["exam"], func=is_allowed)
def cmd_exam(message):
    if not set_mode(message.from_user.id, "exam"):
        bot.send_message(
            message.chat.id,
            "Քննության պատրաստությունը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        message.chat.id,
        "🎓 <b>Քննության պատրաստություն</b>\n\n"
        "Գրիր թեման կամ առարկան, և ես կպատրաստեմ ամբողջական կրկնության դաս՝ "
        "հիմնական կետեր, 10 վարժանք և պատրաստության ստուգում 🙂",
        parse_mode="HTML",
    )


def _make_exam(message, topic: str) -> None:
    """Generate and send a full exam-prep session for the given topic."""
    try:
        with keep_typing(message.chat.id):
            exam = generate_exam(message.from_user.id, topic)
    except Exception as e:
        print(f"Exam generation error: {e}")
        exam = ""
    if not (exam and exam.strip()):
        bot.send_message(
            message.chat.id,
            "Չստացվեց պատրաստել դասը։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    send_reply(message, f"🎓 <b>{html.escape(topic)}</b>\n\n{exam}")


# ── Dictionary (Feature 3 / smart-learning) ──────────────────────────────────
def _define_word(message, word: str) -> None:
    """Explain a word and send it."""
    try:
        with keep_typing(message.chat.id):
            explanation = define_word(message.from_user.id, word)
    except Exception as e:
        print(f"Word definition error: {e}")
        explanation = ""
    if not (explanation and explanation.strip()):
        bot.send_message(
            message.chat.id,
            "Չստացվեց բացատրել բառը։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    # Feature 11: offer a pronunciation guide for the looked-up word.
    send_reply(message, f"📖 {explanation}", reply_markup=_pron_keyboard(word))


@bot.message_handler(commands=["word"], func=is_allowed)
def cmd_word(message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        # Inline form: /word <the word> — define it right away.
        _define_word(message, parts[1].strip())
        return
    if not set_mode(message.from_user.id, "word_lookup"):
        bot.send_message(
            message.chat.id,
            "Բառարանը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        message.chat.id,
        "📖 <b>Բառարան</b>\n\nԳրիր դժվար բառը, և ես կբացատրեմ պարզ լեզվով՝ "
        "օրինակով 🙂",
        parse_mode="HTML",
    )


# ── Pronunciation (Feature 11) ───────────────────────────────────────────────
# A "🗣 Արտասանություն" option that spells out phonetically how to say a hard
# term, written in Armenian letters. Reachable two ways: the button attached to
# every /word definition (the word rides along in callback_data), and the
# /pronounce command (inline «/pronounce <term>» or a prompt + one-shot mode).
def _pron_keyboard(word: str):
    """Inline keyboard with a pronounce button for ``word``.

    The word travels in callback_data; Telegram caps that at 64 bytes, so for
    an unusually long term we simply omit the button (None) rather than send an
    invalid keyboard — /pronounce still handles arbitrary-length terms.
    """
    data = f"pron:{word}"
    if len(data.encode("utf-8")) > 64:
        return None
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🗣 Արտասանություն", callback_data=data))
    return kb


def _pronounce(chat_id: int, user_id: int, term: str, message) -> None:
    """Generate and send a phonetic pronunciation guide for ``term``."""
    try:
        with keep_typing(chat_id):
            guide = pronounce_term(user_id, term)
    except Exception as e:
        print(f"Pronunciation error: {e}")
        guide = ""
    if not (guide and guide.strip()):
        bot.send_message(
            chat_id,
            "Չստացվեց արտասանությունը։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    send_reply(message, f"🗣 <b>{html.escape(term)}</b>\n\n{guide}")


@bot.message_handler(commands=["pronounce"], func=is_allowed)
def cmd_pronounce(message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        # Inline form: /pronounce <term> — pronounce it right away.
        _pronounce(message.chat.id, message.from_user.id, parts[1].strip(), message)
        return
    if not set_mode(message.from_user.id, "pronounce_lookup"):
        bot.send_message(
            message.chat.id,
            "Արտասանության օգնականը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        message.chat.id,
        "🗣 <b>Արտասանություն</b>\n\nԳրիր դժվար բառը կամ տերմինը, և ես ցույց "
        "կտամ, թե ինչպես այն արտասանել 🙂",
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("pron:"))
def cb_pronounce(call):
    bot.answer_callback_query(call.id)
    # Everything after the prefix is the word — do NOT split on ':' (a term may
    # contain one). The tapping user is call.from_user, not the bot that owns
    # call.message, so read the user id from the callback.
    term = call.data[len("pron:") :].strip()
    if term:
        _pronounce(call.message.chat.id, call.from_user.id, term, call.message)


# ── Study plan (Feature 3) ───────────────────────────────────────────────────
@bot.message_handler(commands=["plan"], func=is_allowed)
def cmd_plan(message):
    if not set_mode(message.from_user.id, "plan"):
        bot.send_message(
            message.chat.id,
            "Ուսումնական պլանը հասանելի է միայն հիշողություն միացված ռեժիմում 🙂",
            parse_mode="HTML",
        )
        return
    bot.send_message(
        message.chat.id,
        "📅 <b>Ուսումնական պլան</b>\n\n"
        "Գրիր, թե ի՛նչ առարկաներ կամ թեմաներ պետք է սովորես (կարող ես մեկ "
        "հաղորդագրության մեջ թվարկել քանիսն ուզում ես), և ես կկազմեմ քեզ համար "
        "շաբաթական պլան 🙂",
        parse_mode="HTML",
    )


def _make_study_plan(message, subjects: str) -> None:
    """Generate and send a weekly study plan from the student's subject list."""
    try:
        with keep_typing(message.chat.id):
            plan = generate_study_plan(message.from_user.id, subjects)
    except Exception as e:
        print(f"Study-plan generation error: {e}")
        plan = ""
    if not (plan and plan.strip()):
        bot.send_message(
            message.chat.id,
            "Չստացվեց կազմել պլանը։ Փորձիր նորից մի փոքր ուշ։",
            parse_mode="HTML",
        )
        return
    send_reply(message, f"📅 <b>Քո շաբաթական պլանը</b>\n\n{plan}")


def _route_pending_mode(message, text: str, mode: dict) -> bool:
    """Handle a text message that belongs to an active multi-step flow.

    Returns True if the message was consumed by a flow (so the caller should
    stop), False to fall through to normal conspectus handling.
    """
    name = mode.get("mode")
    if name == "admin_login":
        _handle_admin_login(message, text)
        return True
    if name == "ask":
        _handle_ask(message, text)
        return True
    if name == "exam":
        clear_mode(message.from_user.id)
        _make_exam(message, text)
        return True
    if name == "word_lookup":
        clear_mode(message.from_user.id)
        _define_word(message, text)
        return True
    if name == "pronounce_lookup":
        clear_mode(message.from_user.id)
        _pronounce(message.chat.id, message.from_user.id, text, message)
        return True
    if name == "plan":
        clear_mode(message.from_user.id)
        _make_study_plan(message, text)
        return True
    if name == "game_topic":
        clear_mode(message.from_user.id)
        _start_game(message.chat.id, message.from_user.id, mode.get("kind", "tf"), text)
        return True
    if name == "game_word":
        return _handle_word_guess(message, text)
    if name == "duel_topic":
        clear_mode(message.from_user.id)
        _start_duel(message.chat.id, message.from_user, text, text)
        return True
    return False


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
    # Track the user + count the message for the /admin dashboard.
    touch_user(message.from_user.id)
    incr_messages()
    # In group chats, only engage on answers / mentions / replies (Feature 4).
    if _is_group(message) and _handle_group_message(message, text):
        return
    if is_rate_limited(message.from_user.id):
        limit_msg = f"Դու հասել ես օրական {RATE_LIMIT} հաղորդագրության սահմանին։ Փորձիր նորից վաղը 🙂"
        bot.send_message(message.chat.id, limit_msg, parse_mode="HTML")
        _log(message, "out", f"[rate limited] {limit_msg}")
        return
    # Some flows (/plan, /ask, "guess the word") interpret the next message
    # specially instead of as a new conspectus request.
    mode = get_mode(message.from_user.id)
    if mode and _route_pending_mode(message, text, mode):
        return
    # Feature 8: count this study message; True every SUMMARY_EVERY-th one, when
    # we then offer a recap after the reply.
    offer_summary = note_message(message.from_user.id)
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
            # Feature 7: enter this topic into the spaced-repetition schedule.
            record_study(message.from_user.id, text)
            send_reply(
                message,
                reply,
                reply_markup=_conspectus_keyboard(message.from_user.id),
            )
            _award_new_badges(message.chat.id, message.from_user.id)
            # Feature 8: after a long session, offer a recap of what was studied.
            if offer_summary:
                _offer_summary(message.chat.id)
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


# ── Draw the topic (Feature 12) ──────────────────────────────────────────────
# The child can send a drawing (photo) of what they studied. The bot doesn't
# analyze the image (no vision required) — it just responds warmly and records
# that the student took part (bot/drawings.py). In group chats it stays quiet
# unless directly addressed, so it doesn't react to every photo (mirrors the
# group-mode spam guard in Feature 4).
@bot.message_handler(content_types=["photo"], func=is_allowed)
def handle_photo(message):
    if _is_group(message) and not (
        _is_reply_to_bot(message) or _mentions_bot(message)
    ):
        return
    user_id = message.from_user.id
    chat_id = message.chat.id
    _log(message, "in", "[photo]")
    touch_user(user_id)
    count = record_drawing(user_id)
    text = (
        "🎨 Վա՜յ, ի՜նչ հիանալի նկար 👏 Շատ ապրե՛ս, որ նկարում ես սովորածդ․ "
        "այդպես թեմաներն ավելի լավ են հիշվում 🌟"
    )
    if count > 1:
        text += f"\n\nԴու արդեն կիսվել ես <b>{count}</b> նկարով 🎉"
    bot.send_message(chat_id, text, parse_mode="HTML")
    _log(message, "out", text)


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
    # Track the user + count the message for the /admin dashboard.
    touch_user(user_id)
    incr_messages()

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
            # Feature 7: enter this topic into the spaced-repetition schedule.
            record_study(user_id, transcript)
            send_reply(
                message, full_reply, reply_markup=_conspectus_keyboard(user_id)
            )
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
