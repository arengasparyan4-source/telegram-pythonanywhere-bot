from unittest.mock import MagicMock, patch


def group_message(text, user_id=1, chat_id=-100, first_name="Անի", reply_to=None):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.from_user.first_name = first_name
    msg.from_user.username = None
    msg.chat.id = chat_id
    msg.chat.type = "supergroup"
    msg.reply_to_message = reply_to
    return msg


def _dict_store():
    saved = {}
    s = MagicMock()
    s.set.side_effect = lambda k, v, ex=None: saved.__setitem__(k, v)
    s.get.side_effect = lambda k: saved.get(k)
    s.delete.side_effect = lambda k: saved.pop(k, None)
    return s, saved


# ── history: group class state (multi-user) ──────────────────────────────────
def test_set_get_clear_group_question():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import (
            clear_group_question,
            get_group_question,
            set_group_question,
        )

        assert set_group_question(-100, "Ի՞նչ է ջուրը", asker_id=5) is True
        q = get_group_question(-100)
        assert q["question"] == "Ի՞նչ է ջուրը" and q["asker"] == 5 and q["answers"] == []
        clear_group_question(-100)
        assert get_group_question(-100) is None


def test_add_class_answer_multiple_students_and_replace():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import (
            add_class_answer,
            get_group_question,
            set_group_question,
        )

        set_group_question(-100, "Q", asker_id=5)
        assert add_class_answer(-100, 1, "Անի", "H2O") is True
        assert add_class_answer(-100, 2, "Բաբկեն", "ջուր") is True
        # Same student answers again → replaces, not duplicates.
        assert add_class_answer(-100, 1, "Անի", "ջրածին") is True
        answers = get_group_question(-100)["answers"]
        assert len(answers) == 2
        by_uid = {a["uid"]: a["text"] for a in answers}
        assert by_uid == {1: "ջրածին", 2: "ջուր"}


def test_add_class_answer_without_active_question():
    s, _ = _dict_store()
    with patch("bot.history.store", s):
        from bot.history import add_class_answer

        assert add_class_answer(-100, 1, "Անի", "x") is False


# ── handlers: group detection helpers ────────────────────────────────────────
def test_is_group_detects_group_vs_private():
    from bot.handlers import _is_group

    assert _is_group(group_message("hi")) is True
    priv = group_message("hi")
    priv.chat.type = "private"
    assert _is_group(priv) is False


def test_is_reply_to_bot_and_mentions():
    with patch("bot.handlers.BOT_INFO", MagicMock(id=42, username="testbot")):
        from bot.handlers import _is_reply_to_bot, _mentions_bot

        reply = MagicMock()
        reply.from_user.id = 42
        assert _is_reply_to_bot(group_message("hi", reply_to=reply)) is True
        other = MagicMock()
        other.from_user.id = 7
        assert _is_reply_to_bot(group_message("hi", reply_to=other)) is False
        assert _mentions_bot(group_message("hey @testbot")) is True
        assert _mentions_bot(group_message("hey")) is False


# ── handlers: /askclass (teacher-only, group-only) ───────────────────────────
def test_askclass_rejected_in_private():
    with patch("bot.handlers.bot") as mock_bot:
        from bot.handlers import cmd_askclass

        msg = group_message("/askclass Q")
        msg.chat.type = "private"
        cmd_askclass(msg)
        assert "խմբային" in mock_bot.send_message.call_args[0][1]


def test_askclass_rejected_for_non_admin():
    with (
        patch("bot.handlers._is_group_admin", return_value=False),
        patch("bot.handlers.set_group_question") as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_askclass

        cmd_askclass(group_message("/askclass Ի՞նչ է ջուրը"))
        mock_set.assert_not_called()
        assert "ադմին" in mock_bot.send_message.call_args[0][1]


def test_askclass_posts_question_for_admin():
    with (
        patch("bot.handlers._is_group_admin", return_value=True),
        patch("bot.handlers.set_group_question", return_value=True) as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_askclass

        cmd_askclass(group_message("/askclass Ի՞նչ է ջուրը", user_id=5))
        mock_set.assert_called_once_with(-100, "Ի՞նչ է ջուրը", 5)
        assert "Հարց դասարանին" in mock_bot.send_message.call_args[0][1]


def test_askclass_requires_question_text():
    with (
        patch("bot.handlers._is_group_admin", return_value=True),
        patch("bot.handlers.set_group_question") as mock_set,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_askclass

        cmd_askclass(group_message("/askclass", user_id=5))
        mock_set.assert_not_called()
        assert "Գրիր հարցը" in mock_bot.send_message.call_args[0][1]


# ── handlers: answer collection + gating in handle_message ───────────────────
def test_group_message_collected_as_answer_when_question_active():
    with (
        patch("bot.handlers.should_respond", return_value=True),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.BOT_INFO", MagicMock(id=42, username="testbot")),
        patch("bot.handlers.touch_user"),
        patch("bot.handlers.incr_messages"),
        patch("bot.handlers.get_group_question", return_value={"question": "Q", "answers": []}),
        patch("bot.handlers.add_class_answer", return_value=True) as mock_add,
        patch("bot.handlers.ask_ai") as mock_ask,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import handle_message

        handle_message(group_message("H2O", user_id=1, first_name="Անի"))
        mock_add.assert_called_once_with(-100, 1, "Անի", "H2O")
        # Collected, acknowledged, and NOT turned into a conspectus.
        mock_ask.assert_not_called()
        assert "Ստացա" in mock_bot.send_message.call_args[0][1]


def test_group_message_ignored_when_no_question_and_no_mention():
    with (
        patch("bot.handlers.should_respond", return_value=True),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.BOT_INFO", MagicMock(id=42, username="testbot")),
        patch("bot.handlers.touch_user"),
        patch("bot.handlers.incr_messages"),
        patch("bot.handlers.get_group_question", return_value=None),
        patch("bot.handlers.ask_ai") as mock_ask,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import handle_message

        handle_message(group_message("random chatter", user_id=1))
        # No question, not addressed → the bot stays silent (no spam).
        mock_ask.assert_not_called()
        mock_bot.send_message.assert_not_called()


def test_group_message_engages_when_mentioned():
    with (
        patch("bot.handlers.should_respond", return_value=True),
        patch("bot.handlers.is_rate_limited", return_value=False),
        patch("bot.handlers.BOT_INFO", MagicMock(id=42, username="testbot")),
        patch("bot.handlers.touch_user"),
        patch("bot.handlers.incr_messages"),
        patch("bot.handlers.get_group_question", return_value=None),
        patch("bot.handlers.get_mode", return_value=None),
        patch("bot.handlers.get_provider", return_value="main"),
        patch("bot.handlers.ask_ai", return_value="Պատասխան") as mock_ask,
        patch("bot.handlers.save_last_conspectus"),
        patch("bot.handlers.incr_topics"),
        patch("bot.handlers.incr_conspectuses"),
        patch("bot.handlers.record_activity"),
        patch("bot.handlers._award_new_badges"),
        patch("bot.handlers.send_reply") as mock_send,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import handle_message

        handle_message(group_message("@testbot ի՞նչ է ջուրը", user_id=1))
        # Mentioned → falls through to normal AI handling.
        mock_ask.assert_called_once()
        assert mock_send.called


def test_answers_lists_all_and_clears():
    data = {
        "question": "Ի՞նչ է ջուրը",
        "answers": [
            {"uid": 1, "name": "Անի", "text": "H2O"},
            {"uid": 2, "name": "Բաբկեն", "text": "ջուր"},
        ],
    }
    with (
        patch("bot.handlers._is_group_admin", return_value=True),
        patch("bot.handlers.get_group_question", return_value=data),
        patch("bot.handlers.clear_group_question") as mock_clear,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_answers

        cmd_answers(group_message("/answers", user_id=5))
        sent = mock_bot.send_message.call_args[0][1]
        assert "Անի" in sent and "Բաբկեն" in sent and "H2O" in sent
        mock_clear.assert_called_once_with(-100)
