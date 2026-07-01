import json
import re

from bot.config import NEW_USER_HINT, QUIZ_NUM_QUESTIONS, SYSTEM_PROMPT
from bot.grade import get_grade
from bot.history import get_history, save_history
from bot.providers import generate


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

    reply = generate(user_id, messages)

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
    return generate(user_id, messages)


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
                "q": q.strip(),
                "options": [o.strip() for o in options],
                "correct": correct,
                "explanation": str(explanation).strip(),
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
