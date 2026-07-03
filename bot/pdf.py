"""Render a conspectus to a PDF the student can download (Feature 4).

Uses fpdf2 with a bundled Noto Sans Armenian TTF so Armenian (and Latin /
Cyrillic, which Noto also covers) Unicode text renders correctly — the
default fpdf core fonts are Latin-1 only and would mojibake Armenian.

The font is committed under bot/assets/ so this works on PythonAnywhere
without installing system fonts. fpdf2 is pure-Python (no system libs),
so it's safe on the PA free tier.
"""

import html
import re
from pathlib import Path

from fpdf import FPDF

_FONT_PATH = Path(__file__).resolve().parent / "assets" / "NotoSansArmenian.ttf"
_FONT_FAMILY = "Noto"

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Turn Telegram-HTML conspectus text into plain text for the PDF.

    Conspectuses are now formatted with <b>/<i>/<code> tags (the bot sends
    them with parse_mode=HTML), but fpdf2 renders text literally — the raw
    tags would show up in the document. Drop the tags and unescape any
    &lt;/&gt;/&amp; entities so the PDF reads as clean prose.
    """
    return html.unescape(_HTML_TAG_RE.sub("", text))


def build_conspectus_pdf(topic: str, text: str) -> bytes:
    """Return PDF bytes for a conspectus titled ``topic`` with body ``text``."""
    topic = _strip_html(topic)
    text = _strip_html(text)
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    # The bundled font is a Unicode TTF; fpdf2 auto-detects Unicode mode.
    pdf.add_font(_FONT_FAMILY, "", str(_FONT_PATH))

    if topic:
        pdf.set_font(_FONT_FAMILY, size=16)
        pdf.multi_cell(0, 10, topic)
        pdf.ln(4)

    pdf.set_font(_FONT_FAMILY, size=12)
    # multi_cell wraps long lines; markdown=False keeps raw text intact.
    pdf.multi_cell(0, 8, text)

    # fpdf2 returns a bytearray; normalize to bytes for Telegram upload.
    return bytes(pdf.output())
