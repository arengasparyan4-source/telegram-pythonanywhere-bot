"""Interface-language strings for the bot's own UI (Feature 7).

The AI's replies always mirror the language the *student writes in*; this
module is only for the bot's OWN chrome — the /help menu, command
confirmations, and inline-button labels — which follow the FIXED interface
language the student picked with /language (stored in bot/history.py).

`t(user_id, key, **fmt)` returns the string for the user's language, falling
back to Armenian (the default) for any key/language not translated yet, so a
missing translation degrades to Armenian rather than crashing.

Only the high-traffic menu surfaces are translated into all three languages;
everything else stays Armenian by default. New keys can be added incrementally.
"""

from bot.history import DEFAULT_LANGUAGE, get_language

# key -> {lang -> string}. Missing (key, lang) falls back to Armenian.
_STRINGS: dict[str, dict[str, str]] = {
    "help_title": {
        "hy": "📋 <b>Հրամանների ցանկ</b>",
        "ru": "📋 <b>Список команд</b>",
        "en": "📋 <b>Command list</b>",
    },
    "help_model": {
        "hy": "/model — փոխել AI մատակարարը",
        "ru": "/model — сменить AI-провайдера",
        "en": "/model — switch the AI provider",
    },
    "lang_choose": {
        "hy": "🌐 <b>Ինտերֆեյսի լեզու</b>\n\nԸնտրիր լեզուն 👇",
        "ru": "🌐 <b>Язык интерфейса</b>\n\nВыбери язык 👇",
        "en": "🌐 <b>Interface language</b>\n\nChoose a language 👇",
    },
    "lang_set": {
        "hy": "✅ Ինտերֆեյսի լեզուն դրված է՝ <b>Հայերեն</b>։",
        "ru": "✅ Язык интерфейса установлен: <b>Русский</b>.",
        "en": "✅ Interface language set to <b>English</b>.",
    },
    # Conspectus inline-keyboard button labels.
    "btn_quiz": {"hy": "📝 Կարճ վիկտորինա", "ru": "📝 Викторина", "en": "📝 Quiz"},
    "btn_cards": {"hy": "🧠 Flashcards", "ru": "🧠 Карточки", "en": "🧠 Flashcards"},
    "btn_mindmap": {
        "hy": "🗺 Mind Map",
        "ru": "🗺 Интеллект-карта",
        "en": "🗺 Mind Map",
    },
    "btn_story": {"hy": "📖 Պատմություն", "ru": "📖 История", "en": "📖 Story"},
    "btn_why": {
        "hy": "🌍 Ինչու է կարևոր?",
        "ru": "🌍 Почему это важно?",
        "en": "🌍 Why it matters?",
    },
    "btn_homework": {
        "hy": "📝 Տնային առաջադրանք",
        "ru": "📝 Домашнее задание",
        "en": "📝 Homework",
    },
    "btn_simple": {
        "hy": "🔍 Պարզ բացատրիր",
        "ru": "🔍 Объясни просто",
        "en": "🔍 Explain simply",
    },
    "btn_save": {
        "hy": "⭐ Պահել",
        "ru": "⭐ Сохранить",
        "en": "⭐ Save",
    },
    "btn_more": {
        "hy": "🔍 Ավելի մանրամասն",
        "ru": "🔍 Подробнее",
        "en": "🔍 More detail",
    },
    "btn_new": {"hy": "📚 Ուրիշ թեմա", "ru": "📚 Другая тема", "en": "📚 New topic"},
    "btn_pdf": {"hy": "📄 PDF", "ru": "📄 PDF", "en": "📄 PDF"},
}

# The /help command body, as an ordered list of lines per language. Kept
# separate from _STRINGS because it's a list, not a single string.
_HELP_LINES: dict[str, list[str]] = {
    "hy": [
        "/start — սկսել զրույցը բոտի հետ",
        "/help — տեսնել հրամանների ցանկը",
        "/quiz — կարճ վիկտորինա վերջին կոնսպեկտի հիման վրա",
        "/exam — քննության պատրաստության դաս 🎓",
        "/pdf — ստանալ վերջին կոնսպեկտը PDF ֆայլով",
        "/stats — տեսնել քո ուսումնական վիճակագրությունը",
        "/achievements — տեսնել քո վաստակած նշանները",
        "/repeat — կրկնել վերջին կոնսպեկտը",
        "/plan — կազմել շաբաթական ուսումնական պլան",
        "/game — խաղալ ուսումնական խաղեր 🎮",
        "/challenge — օրվա մարտահրավեր (/challenge 09:00 ամեն օր)",
        "/ask — հարցրու ինձ ինչ ուզես 🤔",
        "/favorites — սիրելի թեմաներ ⭐",
        "/weakspots — թույլ կողմեր 🎯",
        "/remind — դնել օրական հիշեցում (օր․՝ /remind 18:00)",
        "/parent — ծնողի շաբաթական հաշվետվություն (/parent &lt;երեխայի ID&gt;)",
        "/grade — ընտրել դասարանը, որ բացատրությունները հարմարեցնեմ քեզ",
        "/language — ընտրել ինտերֆեյսի լեզուն 🌐",
        "/reset — մաքրել մեր զրույցի պատմությունը և սկսել նորից",
        "/about — իմանալ ավելին այս բոտի մասին",
        "/sha — ցույց տալ բոտի ընթացիկ git commit SHA-ն",
    ],
    "ru": [
        "/start — начать общение с ботом",
        "/help — показать список команд",
        "/quiz — короткая викторина по последнему конспекту",
        "/exam — подготовка к экзамену 🎓",
        "/pdf — получить последний конспект в PDF",
        "/stats — посмотреть свою учебную статистику",
        "/achievements — посмотреть свои значки",
        "/repeat — повторить последний конспект",
        "/plan — составить недельный учебный план",
        "/game — сыграть в учебные игры 🎮",
        "/challenge — задание дня (/challenge 09:00 каждый день)",
        "/ask — спроси меня о чём угодно 🤔",
        "/favorites — избранные темы ⭐",
        "/weakspots — слабые места 🎯",
        "/remind — ежедневное напоминание (напр.: /remind 18:00)",
        "/parent — недельный отчёт для родителя (/parent &lt;ID ребёнка&gt;)",
        "/grade — выбрать класс, чтобы подстроить объяснения",
        "/language — выбрать язык интерфейса 🌐",
        "/reset — очистить историю беседы и начать заново",
        "/about — подробнее об этом боте",
        "/sha — показать текущий git-коммит бота",
    ],
    "en": [
        "/start — start chatting with the bot",
        "/help — show the command list",
        "/quiz — short quiz on your last conspectus",
        "/exam — exam-prep review session 🎓",
        "/pdf — get your last conspectus as a PDF",
        "/stats — see your study statistics",
        "/achievements — see the badges you've earned",
        "/repeat — repeat your last conspectus",
        "/plan — build a weekly study plan",
        "/game — play educational games 🎮",
        "/challenge — challenge of the day (/challenge 09:00 daily)",
        "/ask — ask me anything 🤔",
        "/favorites — favorite topics ⭐",
        "/weakspots — weak spots 🎯",
        "/remind — set a daily reminder (e.g. /remind 18:00)",
        "/parent — weekly report for a parent (/parent &lt;child ID&gt;)",
        "/grade — pick a grade so I tailor explanations",
        "/language — choose the interface language 🌐",
        "/reset — clear our conversation history and start over",
        "/about — learn more about this bot",
        "/sha — show the bot's current git commit SHA",
    ],
}


def t(user_id: int, key: str, **fmt) -> str:
    """Return the localized string for ``key`` in the user's language.

    Falls back to Armenian for any untranslated (key, language). ``fmt`` is
    applied with str.format when provided.
    """
    lang = get_language(user_id)
    table = _STRINGS.get(key, {})
    s = table.get(lang) or table.get(DEFAULT_LANGUAGE) or ""
    return s.format(**fmt) if fmt else s


def help_lines(user_id: int) -> list[str]:
    """Return the /help command lines in the user's interface language."""
    lang = get_language(user_id)
    return _HELP_LINES.get(lang) or _HELP_LINES[DEFAULT_LANGUAGE]
