import json
import re

from bot.config import (
    FLASHCARD_NUM,
    NEW_USER_HINT,
    QUIZ_NUM_QUESTIONS,
    SYSTEM_PROMPT,
)
from bot.grade import get_grade
from bot.history import get_history, save_history
from bot.providers import generate

# Unicode script blocks unrelated to Armenian/Russian/English study help.
# This is a DENYLIST (not an allowlist) so emoji, box-drawing tree connectors
# (├── └── │), math/currency symbols, and punctuation are PRESERVED — only
# foreign scripts the model occasionally leaks are removed. It runs on every
# AI reply before it is sent. On already-clean text it matches nothing and
# returns the string unchanged, so verbatim outputs (e.g. mind-map trees) are
# byte-identical.
_FOREIGN_SCRIPT_RE = re.compile(
    "["
    "぀-ヿ"  # Hiragana + Katakana (Japanese)
    "㐀-䶿"  # CJK Extension A
    "一-鿿"  # CJK Unified Ideographs (Chinese / Kanji)
    "豈-﫿"  # CJK Compatibility Ideographs
    "　-〿"  # CJK symbols & punctuation
    "가-힯"  # Hangul syllables (Korean)
    "ᄀ-ᇿ"  # Hangul Jamo
    "؀-ۿ"  # Arabic
    "ݐ-ݿ"  # Arabic Supplement
    "ﭐ-﷿"  # Arabic Presentation Forms-A
    "ﹰ-﻿"  # Arabic Presentation Forms-B
    "֐-׿"  # Hebrew
    "฀-๿"  # Thai
    "ऀ-ॿ"  # Devanagari
    "]+"
)


def sanitize_reply(text: str) -> str:
    """Strip unrelated foreign scripts (CJK / Arabic / Hebrew / Thai / …) from
    an AI reply, preserving Armenian, Russian, English, digits, punctuation,
    emoji, and box-drawing characters. A no-op on clean text."""
    return _FOREIGN_SCRIPT_RE.sub("", text)


def _grade_clause(user_id: int) -> str:
    """Return an instruction tuning complexity to the user's grade band.

    Empty string when the student hasn't set a grade (the default), so
    the prompt is unchanged and behavior matches the pre-Feature-3 bot.
    """
    grade = get_grade(user_id)
    if not grade:
        return ""
    return (
        f" The student is in school grades {grade}. Adjust the complexity, vocabulary, "
        "sentence length, and depth of your explanation to suit a child at that grade level."
    )


def _build_system_prompt(user_id: int, is_new_user: bool = False) -> str:
    """Assemble the educational system prompt with optional grade + new-user hints."""
    prompt = SYSTEM_PROMPT + _grade_clause(user_id)
    if is_new_user:
        prompt = f"{prompt} {NEW_USER_HINT}"
    return prompt


def ask_ai(user_id: int, user_message: str) -> str:
    history = get_history(user_id)
    # No prior turns means this is a brand-new user — nudge the model to
    # default to Armenian until the student establishes a language.
    is_new_user = not history
    history.append({"role": "user", "content": user_message})

    system_prompt = _build_system_prompt(user_id, is_new_user)

    messages = [{"role": "system", "content": system_prompt}]
    messages += history

    reply = sanitize_reply(generate(user_id, messages))

    history.append({"role": "assistant", "content": reply})
    save_history(user_id, history)
    return reply


def expand_conspectus(user_id: int, topic: str, previous_text: str) -> str:
    """Regenerate a deeper, more detailed conspectus on the same topic.

    Used by the "Ավելի մանրամասն" (more detail) inline button. The
    previous notes are passed back to the model so it builds on them
    rather than starting over, and it's told to keep the conspectus's
    own language so we don't lose the student's language. This is a
    one-shot call that does not touch conversation history.
    """
    instruction = (
        f"Earlier you wrote this conspectus (study notes) on the topic «{topic}»:\n\n"
        f"{previous_text}\n\n"
        "Now write a deeper, more detailed version of these notes on the same topic. "
        "Add more interesting facts, examples, and clear explanations, while keeping it "
        "engaging and easy for a child to understand and retell. "
        "Reply in the SAME language as the conspectus above."
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(user_id)},
        {"role": "user", "content": instruction},
    ]
    return sanitize_reply(generate(user_id, messages))


def _strip_code_fence(text: str) -> str:
    """Strip a leading/trailing Markdown code fence the model may add.

    Models often wrap JSON in ```json ... ``` even when told not to.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    return text


def _parse_quiz(raw: str, num_questions: int) -> list:
    """Validate the model's JSON into a clean list of question dicts.

    Returns [] on any parse/shape problem so the caller can fall back to
    a friendly "couldn't build a quiz" message rather than crashing.
    Each accepted question has a non-empty prompt, 2-6 string options,
    and a correct index within range.
    """
    if not raw:
        return []
    try:
        data = json.loads(_strip_code_fence(raw))
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    questions = []
    for item in data:
        if not isinstance(item, dict):
            continue
        q = item.get("q")
        options = item.get("options")
        correct = item.get("correct")
        explanation = item.get("explanation", "")
        if not isinstance(q, str) or not q.strip():
            continue
        if not isinstance(options, list) or not (2 <= len(options) <= 6):
            continue
        if not all(isinstance(o, str) and o.strip() for o in options):
            continue
        # JSON has no int/bool distinction issue here, but guard bools.
        if isinstance(correct, bool) or not isinstance(correct, int):
            continue
        if not (0 <= correct < len(options)):
            continue
        questions.append(
            {
                "q": sanitize_reply(q.strip()),
                "options": [sanitize_reply(o.strip()) for o in options],
                "correct": correct,
                "explanation": sanitize_reply(str(explanation).strip()),
            }
        )
        if len(questions) >= num_questions:
            break
    return questions


def generate_quiz(
    user_id: int, conspectus_text: str, num_questions: int = QUIZ_NUM_QUESTIONS
) -> list:
    """Generate a multiple-choice quiz from a conspectus.

    Questions are drawn ONLY from the provided conspectus text (not the
    full textbook) so they check what the student just read. The model is
    asked to answer in the conspectus's own language and to return strict
    JSON; `_parse_quiz` validates it. Returns a list of question dicts, or
    [] if generation/parsing failed.
    """
    instruction = (
        f"Based ONLY on the following study notes, write exactly {num_questions} simple "
        "multiple-choice questions that check whether a child understood and remembers the "
        "material. Each question must have exactly 4 short options with exactly one correct "
        "answer. Write the questions, options, and explanations in the SAME language as the "
        "study notes. Keep everything simple and age-appropriate."
        + _grade_clause(user_id)
        + " "
        'Return ONLY valid JSON and nothing else: a list of objects, each with keys '
        '"q" (string), "options" (array of 4 strings), "correct" (0-based integer index of '
        'the correct option), and "explanation" (a short sentence explaining the answer). '
        "Do not wrap the JSON in code fences.\n\n"
        f"Study notes:\n{conspectus_text}"
    )
    messages = [
        {
            "role": "system",
            "content": "You are a quiz generator for schoolchildren. You output only strict JSON.",
        },
        {"role": "user", "content": instruction},
    ]
    raw = generate(user_id, messages)
    return _parse_quiz(raw, num_questions)


def _parse_flashcards(raw: str, num_cards: int) -> list:
    """Validate the model's JSON into a clean list of {"q", "a"} dicts.

    Returns [] on any parse/shape problem so the caller can fall back to a
    friendly "couldn't build flashcards" message rather than crashing. Each
    accepted card needs a non-empty question and answer string.
    """
    if not raw:
        return []
    try:
        data = json.loads(_strip_code_fence(raw))
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    cards = []
    for item in data:
        if not isinstance(item, dict):
            continue
        q = item.get("q")
        a = item.get("a")
        if not isinstance(q, str) or not q.strip():
            continue
        if not isinstance(a, str) or not a.strip():
            continue
        cards.append({"q": sanitize_reply(q.strip()), "a": sanitize_reply(a.strip())})
        if len(cards) >= num_cards:
            break
    return cards


def generate_flashcards(
    user_id: int, conspectus_text: str, num_cards: int = FLASHCARD_NUM
) -> list:
    """Generate question/answer flashcards from a conspectus.

    Cards are drawn ONLY from the provided conspectus text so they revise
    exactly what the student just read. The model answers in the
    conspectus's own language and returns strict JSON; `_parse_flashcards`
    validates it. Returns a list of {"q", "a"} dicts, or [] on failure.
    """
    instruction = (
        f"Based ONLY on the following study notes, write exactly {num_cards} short "
        "flashcards that help a child revise the material. Each flashcard is a "
        "question and its concise answer. Write the questions and answers in the "
        "SAME language as the study notes. Keep everything simple and age-appropriate."
        + _grade_clause(user_id)
        + " "
        'Return ONLY valid JSON and nothing else: a list of objects, each with keys '
        '"q" (the question string) and "a" (the answer string). '
        "Do not wrap the JSON in code fences.\n\n"
        f"Study notes:\n{conspectus_text}"
    )
    messages = [
        {
            "role": "system",
            "content": "You are a flashcard generator for schoolchildren. You output only strict JSON.",
        },
        {"role": "user", "content": instruction},
    ]
    raw = generate(user_id, messages)
    return _parse_flashcards(raw, num_cards)


def _parse_truefalse(raw: str, num_rounds: int) -> list:
    """Validate the model's JSON into a list of {"s", "ok", "why"} rounds.

    Each round is a statement (`s`), whether it is true (`ok`, bool), and a
    short explanation (`why`). Returns [] on any parse/shape problem so the
    caller can fall back to a friendly message rather than crashing.
    """
    if not raw:
        return []
    try:
        data = json.loads(_strip_code_fence(raw))
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    rounds = []
    for item in data:
        if not isinstance(item, dict):
            continue
        s = item.get("s")
        ok = item.get("ok")
        why = item.get("why", "")
        if not isinstance(s, str) or not s.strip():
            continue
        if not isinstance(ok, bool):
            continue
        rounds.append(
            {
                "s": sanitize_reply(s.strip()),
                "ok": ok,
                "why": sanitize_reply(str(why).strip()),
            }
        )
        if len(rounds) >= num_rounds:
            break
    return rounds


def generate_truefalse(user_id: int, source: str, num_rounds: int) -> list:
    """Generate a true/false game from a topic or conspectus text.

    Returns a list of {"s", "ok", "why"} rounds, roughly half true and half
    false, in the source's language. [] on generation/parse failure.
    """
    instruction = (
        f"Create exactly {num_rounds} simple TRUE/FALSE statements to test a "
        "child's knowledge about the topic/notes below. Make roughly half true "
        "and half false, keep each statement short and age-appropriate, and "
        "write them in the SAME language as the topic/notes."
        + _grade_clause(user_id)
        + " "
        'Return ONLY valid JSON: a list of objects with keys "s" (the statement '
        'string), "ok" (boolean — true if the statement is correct), and "why" '
        '(a short sentence explaining why). Do not wrap the JSON in code fences.\n\n'
        f"Topic / notes:\n{source}"
    )
    messages = [
        {
            "role": "system",
            "content": "You are a quiz-game generator for schoolchildren. You output only strict JSON.",
        },
        {"role": "user", "content": instruction},
    ]
    return _parse_truefalse(generate(user_id, messages), num_rounds)


def _parse_wordgame(raw: str, num_rounds: int) -> list:
    """Validate the model's JSON into a list of {"word", "hint"} rounds."""
    if not raw:
        return []
    try:
        data = json.loads(_strip_code_fence(raw))
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    rounds = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = item.get("word")
        hint = item.get("hint")
        if not isinstance(word, str) or not word.strip():
            continue
        if not isinstance(hint, str) or not hint.strip():
            continue
        rounds.append(
            {"word": sanitize_reply(word.strip()), "hint": sanitize_reply(hint.strip())}
        )
        if len(rounds) >= num_rounds:
            break
    return rounds


def generate_word_game(user_id: int, source: str, num_rounds: int) -> list:
    """Generate a "guess the word" game from a topic or conspectus text.

    Returns a list of {"word", "hint"} rounds — a key term and a child-
    friendly clue — in the source's language. [] on failure.
    """
    instruction = (
        f"Pick exactly {num_rounds} important single words or short terms a "
        "child should know from the topic/notes below. For each, write a short, "
        "child-friendly hint that describes the word WITHOUT saying it. Write "
        "everything in the SAME language as the topic/notes."
        + _grade_clause(user_id)
        + " "
        'Return ONLY valid JSON: a list of objects with keys "word" (the word to '
        'guess) and "hint" (the clue). Do not wrap the JSON in code fences.\n\n'
        f"Topic / notes:\n{source}"
    )
    messages = [
        {
            "role": "system",
            "content": "You are a word-game generator for schoolchildren. You output only strict JSON.",
        },
        {"role": "user", "content": instruction},
    ]
    return _parse_wordgame(generate(user_id, messages), num_rounds)


# Example tree shown to the model so it copies the exact format. Kept as a
# constant so the /mindmap prompt and any tests reference the same shape.
_MINDMAP_EXAMPLE = (
    "🌍 Գլխավոր թեմա\n"
    "  ├── 📌 Ենթաթեմա 1\n"
    "  │     ├── մանրամասն\n"
    "  │     └── մանրամասն\n"
    "  ├── 📌 Ենթաթեմա 2\n"
    "  └── 📌 Ենթաթեմա 3"
)


def generate_mindmap(user_id: int, topic: str, conspectus_text: str) -> str:
    """Generate a text mind map of the topic in the fixed tree format.

    One-shot call (does not touch conversation history). The model is shown
    the exact indentation/tree/emoji format to copy and told to answer in
    the conspectus's own language. Any code fence the model adds is stripped.
    """
    instruction = (
        f"Create a text-based mind map of the topic «{topic}», based ONLY on these "
        "study notes. Use EXACTLY this indentation, tree connectors (├──, └──, │) "
        "and emoji-bullet format — copy the structure precisely:\n\n"
        f"{_MINDMAP_EXAMPLE}\n\n"
        "The first line is the main topic with a single leading emoji. Add 3-5 "
        "subtopics, each on its own line marked with 📌, and 1-3 short details "
        "indented under each subtopic. Keep every line short. Reply in the SAME "
        "language as the study notes." + _grade_clause(user_id) + " "
        "Output ONLY the mind map — no title, no explanation, no code fences.\n\n"
        f"Study notes:\n{conspectus_text}"
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(user_id)},
        {"role": "user", "content": instruction},
    ]
    return sanitize_reply(_strip_code_fence(generate(user_id, messages)))


def generate_story(user_id: int, topic: str, conspectus_text: str) -> str:
    """Retell the topic as an engaging short story for a child.

    One-shot call (does not touch conversation history). Turns the same
    facts into a 3-5 paragraph adventure, kept accurate and age-appropriate,
    in the conspectus's own language.
    """
    instruction = (
        f"Retell the topic «{topic}» as an engaging short story for a child, based "
        "ONLY on these study notes. Write 3-5 short paragraphs that turn the facts "
        "into a little adventure the child will enjoy, while keeping every fact "
        "accurate. Make it warm and vivid, not a dry summary. Reply in the SAME "
        "language as the study notes." + _grade_clause(user_id) + " "
        "Output ONLY the story.\n\n"
        f"Study notes:\n{conspectus_text}"
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(user_id)},
        {"role": "user", "content": instruction},
    ]
    return sanitize_reply(generate(user_id, messages))


def answer_question(user_id: int, question: str) -> str:
    """Answer a free-form question directly and simply (/ask mode, Feature 6).

    A one-shot, child-friendly answer — deliberately NOT a structured
    conspectus. Does not touch conversation history. Replies in the question's
    language.
    """
    instruction = (
        "Answer the child's question below clearly and simply, like a friendly "
        "teacher. Give a direct, correct, age-appropriate answer in a few short "
        "sentences — not a long lecture. Reply in the SAME language as the "
        "question." + _grade_clause(user_id) + " Output ONLY the answer.\n\n"
        f"Question:\n{question}"
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(user_id)},
        {"role": "user", "content": instruction},
    ]
    return sanitize_reply(generate(user_id, messages))


def generate_challenge(user_id: int) -> str:
    """Generate one short, curiosity-sparking educational challenge.

    A standalone daily challenge — not tied to any conspectus and it does not
    touch conversation history. Either a thought-provoking question or a tiny
    fascinating fact followed by a question to ponder. Armenian by default.
    """
    instruction = (
        "Give ONE short, interesting educational challenge for a curious child: "
        "either a thought-provoking question, or a tiny fascinating fact plus a "
        "question to think about. Pick any school subject. Keep it to 2-4 warm, "
        "simple sentences that spark curiosity. Reply in Armenian by default."
        + _grade_clause(user_id)
        + " Output ONLY the challenge."
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(user_id)},
        {"role": "user", "content": instruction},
    ]
    return sanitize_reply(generate(user_id, messages))


def generate_study_plan(user_id: int, subjects: str) -> str:
    """Generate a structured weekly study plan from a free-text subject list.

    One-shot call (does not touch conversation history). Spreads the given
    subjects/topics across the days of the week with short, realistic daily
    goals, in the language the student wrote their subjects in.
    """
    instruction = (
        "Create a structured weekly study plan for a schoolchild based on the "
        "subjects/topics they want to study, listed below. Organise it by day "
        "(Monday–Sunday): put a <b>bold day heading</b> for each day and 1-2 "
        "short bullet lines under it saying which topic to study and roughly "
        "for how long. Balance the load across the week, keep it realistic and "
        "encouraging, and leave a lighter day for rest/review. Reply in the "
        "SAME language the subjects are written in." + _grade_clause(user_id)
        + " Output ONLY the plan.\n\n"
        f"Subjects/topics to study:\n{subjects}"
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(user_id)},
        {"role": "user", "content": instruction},
    ]
    return sanitize_reply(generate(user_id, messages))


def explain_simply(user_id: int, topic: str, conspectus_text: str) -> str:
    """Re-explain the topic as if to a 5-year-old, with everyday analogies.

    One-shot call (does not touch conversation history). Uses the simplest
    possible words and concrete comparisons a small child would recognise,
    based on the conspectus, in the conspectus's own language.
    """
    instruction = (
        f"Explain the topic «{topic}» as if you were talking to a 5-year-old "
        "child. Use the very simplest words, short sentences, and warm everyday "
        "analogies (toys, food, animals, home, play) so it feels obvious and "
        "fun. Base it ONLY on these study notes and keep every fact correct. "
        "Reply in the SAME language as the study notes." + _grade_clause(user_id)
        + " Output ONLY the simple explanation.\n\n"
        f"Study notes:\n{conspectus_text}"
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(user_id)},
        {"role": "user", "content": instruction},
    ]
    return sanitize_reply(generate(user_id, messages))


def generate_homework(user_id: int, topic: str, conspectus_text: str) -> str:
    """Generate 3-5 practical homework exercises from a conspectus.

    One-shot call (does not touch conversation history). The tasks are drawn
    ONLY from the conspectus so they practise exactly what the student just
    read, are numbered, age-appropriate, and in the conspectus's language.
    """
    instruction = (
        f"Based ONLY on these study notes about «{topic}», create 3-5 practical "
        "homework exercises / tasks for a child to solve. Mix a few kinds "
        "(a short question to answer, something to find or match, a little "
        "problem to work out). Number them 1., 2., 3. … Keep each task short, "
        "clear, and age-appropriate, and do NOT include the answers. Reply in "
        "the SAME language as the study notes." + _grade_clause(user_id) + " "
        "Output ONLY the exercises.\n\n"
        f"Study notes:\n{conspectus_text}"
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(user_id)},
        {"role": "user", "content": instruction},
    ]
    return sanitize_reply(generate(user_id, messages))


def generate_why_matters(user_id: int, topic: str, conspectus_text: str) -> str:
    """Explain, in 3-4 sentences, why the topic matters in real life.

    One-shot call (does not touch conversation history). Uses concrete
    everyday examples a child can relate to, in the conspectus's language.
    """
    instruction = (
        f"In 3-4 short sentences, explain why the topic «{topic}» matters in real "
        "life. Use concrete, everyday examples a child can relate to — things they "
        "see or do at home, at school, or outside. Base it ONLY on these study "
        "notes and keep it warm and simple. Reply in the SAME language as the study "
        "notes." + _grade_clause(user_id) + " "
        "Output ONLY the explanation.\n\n"
        f"Study notes:\n{conspectus_text}"
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(user_id)},
        {"role": "user", "content": instruction},
    ]
    return sanitize_reply(generate(user_id, messages))


def generate_exam(user_id: int, topic: str) -> str:
    """Generate a full exam-prep review session for a topic (Feature 1).

    One-shot call (does not touch conversation history). Produces a key-points
    summary, 10 practice questions, and a short readiness self-check, formatted
    with HTML headings. Armenian by default (mirrors the topic's language).
    """
    instruction = (
        f"Create a complete exam-preparation review session for a schoolchild on "
        f"the topic «{topic}». Structure it with three clear sections:\n"
        "1) 🎯 <b>Հիմնական կետեր</b> — a short bullet-point summary of the key "
        "points to know.\n"
        "2) 📝 <b>Վարժանք</b> — EXACTLY 10 numbered practice questions of "
        "increasing difficulty. Do NOT include the answers.\n"
        "3) ✅ <b>Պատրաստության ստուգում</b> — 2-3 quick self-check questions the "
        "student should be able to answer if they are ready.\n"
        "Use the HTML section headings shown above. Reply in the SAME language as "
        "the topic (Armenian by default)." + _grade_clause(user_id) + " "
        "Output ONLY the review session."
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(user_id)},
        {"role": "user", "content": instruction},
    ]
    return sanitize_reply(generate(user_id, messages))


def generate_quiz_hint(user_id: int, question: str, options: list) -> str:
    """Give a hint for a multiple-choice question WITHOUT revealing the answer.

    One-shot call (no history). The model is explicitly told not to state or
    point to the correct option — only to nudge the student's reasoning. In
    the question's language.
    """
    opts = "; ".join(str(o) for o in (options or []))
    instruction = (
        "A student is stuck on this multiple-choice question. Give ONE short, "
        "encouraging HINT that guides their thinking toward the answer. "
        "Do NOT reveal the answer, do NOT say which option is correct, and do "
        "NOT restate an option as the answer — only nudge them on how to reason "
        "or what idea to recall. Reply in the SAME language as the question."
        + _grade_clause(user_id)
        + " Output ONLY the hint.\n\n"
        f"Question: {question}\nOptions: {opts}"
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(user_id)},
        {"role": "user", "content": instruction},
    ]
    return sanitize_reply(generate(user_id, messages))


def define_word(user_id: int, word: str) -> str:
    """Explain a difficult word in simple language with an example (Feature 3).

    One-shot call (no history). Gives a short child-friendly meaning plus one
    example sentence using the word, in the word's language (Armenian default).
    """
    instruction = (
        f"A child asks what the word «{word}» means. Explain it in the very "
        "simplest language a child would understand, then give ONE example "
        "sentence that uses the word naturally. Keep it short and warm. Put the "
        "word itself in <b>bold</b>. Reply in the SAME language as the word "
        "(Armenian by default)." + _grade_clause(user_id) + " "
        "Output ONLY the explanation and the example."
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(user_id)},
        {"role": "user", "content": instruction},
    ]
    return sanitize_reply(generate(user_id, messages))
