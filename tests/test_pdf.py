from unittest.mock import MagicMock, patch


# ── bot.pdf: real PDF generation with the bundled Armenian font ─────────────


def test_build_conspectus_pdf_returns_valid_pdf_bytes():
    from bot.pdf import build_conspectus_pdf

    data = build_conspectus_pdf(
        "Ֆոտոսինթեզ",
        "Ֆոտոսինթեզը գործընթաց է, որի ընթացքում բույսերը արևի լույսից "
        "էներգիա են ստանում։\n\nԿանաչ տերևները կլանում են ածխաթթու գազը։",
    )
    assert isinstance(data, (bytes, bytearray))
    assert data[:5] == b"%PDF-"
    assert len(data) > 1000  # a real document, not an empty stub


def test_build_conspectus_pdf_handles_empty_topic():
    from bot.pdf import build_conspectus_pdf

    data = build_conspectus_pdf("", "Միայն բովանդակություն, առանց վերնագրի։")
    assert data[:5] == b"%PDF-"


def test_build_conspectus_pdf_strips_html_tags():
    """Conspectuses now carry Telegram-HTML tags; the PDF must render clean
    prose, not literal <b>/<i>/&lt; markup."""
    from bot.pdf import _strip_html

    assert _strip_html("<b>Սահմանում</b>") == "Սահմանում"
    assert _strip_html("5 &lt; 10 &amp; 3 &gt; 1") == "5 < 10 & 3 > 1"
    assert _strip_html("• <i>key</i>: <code>H2O</code>") == "• key: H2O"


# ── handlers: /pdf + callback ───────────────────────────────────────────────


def _call(data="pdf:export", user_id=123, chat_id=456):
    call = MagicMock()
    call.data = data
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    return call


def make_message(user_id=123, chat_id=456):
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    return msg


def test_export_pdf_without_conspectus_prompts_topic():
    with (
        patch("bot.handlers.get_last_conspectus", return_value=None),
        patch("bot.handlers.build_conspectus_pdf") as mock_build,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _export_pdf

        _export_pdf(456, 123)
        mock_build.assert_not_called()
        mock_bot.send_document.assert_not_called()
        sent = mock_bot.send_message.call_args[0][1]
        assert "Դեռ" in sent


def test_export_pdf_sends_document():
    with (
        patch(
            "bot.handlers.get_last_conspectus",
            return_value={"topic": "Ֆոտոսինթեզ", "text": "body"},
        ),
        patch("bot.handlers.build_conspectus_pdf", return_value=b"%PDF-fake"),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _export_pdf

        _export_pdf(456, 123)
        mock_bot.send_document.assert_called_once()
        args, kwargs = mock_bot.send_document.call_args
        assert args[0] == 456
        # A file-like document with a .pdf name was sent.
        document = args[1]
        assert getattr(document, "name", "").endswith(".pdf")
        assert kwargs.get("visible_file_name") == "konspekt.pdf"
        assert "Ֆոտոսինթեզ" in kwargs.get("caption", "")


def test_export_pdf_handles_generation_error():
    with (
        patch(
            "bot.handlers.get_last_conspectus",
            return_value={"topic": "t", "text": "body"},
        ),
        patch("bot.handlers.build_conspectus_pdf", side_effect=Exception("boom")),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _export_pdf

        _export_pdf(456, 123)
        mock_bot.send_document.assert_not_called()
        sent = mock_bot.send_message.call_args[0][1]
        assert "Չստացվեց" in sent


def test_export_pdf_truncates_long_topic_caption():
    long_topic = "Ա" * 500
    with (
        patch(
            "bot.handlers.get_last_conspectus",
            return_value={"topic": long_topic, "text": "body"},
        ),
        patch("bot.handlers.build_conspectus_pdf", return_value=b"%PDF-fake"),
        patch("bot.handlers.keep_typing"),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import _export_pdf

        _export_pdf(456, 123)
        caption = mock_bot.send_document.call_args[1]["caption"]
        # "📄 " + 200 chars max
        assert len(caption) <= 205


def test_cmd_pdf_invokes_export():
    with (
        patch("bot.handlers._export_pdf") as mock_export,
        patch("bot.handlers.bot"),
    ):
        from bot.handlers import cmd_pdf

        cmd_pdf(make_message())
        mock_export.assert_called_once_with(456, 123)


def test_cb_pdf_routes_and_acks():
    with (
        patch("bot.handlers._export_pdf") as mock_export,
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cb_pdf

        cb_pdf(_call())
        mock_export.assert_called_once_with(456, 123)
        mock_bot.answer_callback_query.assert_called_once()
