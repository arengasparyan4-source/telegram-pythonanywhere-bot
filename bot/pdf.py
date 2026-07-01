"""Render a conspectus to a PDF the student can download (Feature 4).

Uses fpdf2 with a bundled Noto Sans Armenian TTF so Armenian (and Latin /
Cyrillic, which Noto also covers) Unicode text renders correctly — the
default fpdf core fonts are Latin-1 only and would mojibake Armenian.

The font is committed under bot/assets/ so this works on PythonAnywhere
without installing system fonts. fpdf2 is pure-Python (no system libs),
so it's safe on the PA free tier.
"""

from pathlib import Path

from fpdf import FPDF

_FONT_PATH = Path(__file__).resolve().parent / "assets" / "NotoSansArmenian.ttf"
_FONT_FAMILY = "Noto"


def build_conspectus_pdf(topic: str, text: str) -> bytes:
    """Return PDF bytes for a conspectus titled ``topic`` with body ``text``."""
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
