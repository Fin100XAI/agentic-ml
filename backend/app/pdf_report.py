"""PDF rendering of the decision brief (fpdf2).

Reuses the exact markdown from ``build_report`` so the .md download and the
PDF can never drift apart, and renders it with a light typographic hierarchy.
"""
from __future__ import annotations

import re

from fpdf import FPDF

from app.report import build_report
from engine.orchestrator import Run

INK = (15, 23, 42)
INK_DIM = (100, 116, 139)
ACCENT = (79, 70, 229)
EDGE = (221, 227, 238)

# Helvetica is latin-1 only; swap the common symbols agents emit.
_REPLACEMENTS = {
    "≈": "~", "±": "+/-", "→": "->", "←": "<-",
    "·": "-", "—": "-", "–": "-", "‘": "'",
    "’": "'", "“": '"', "”": '"', "×": "x",
    "…": "...", "❌": "[failed]", "\U0001f3c6": "[best]",
    "✅": "[ok]", "⚠": "[!]", "⚠️": "[!]",
}


def _latin(text: str) -> str:
    text = text.replace("`", "")  # markdown code ticks have no PDF meaning
    for src, dst in _REPLACEMENTS.items():
        text = text.replace(src, dst)
    # Drop the _emphasis_ markers fpdf's markdown mode doesn't know.
    text = re.sub(r"(?<![\w_])_([^_\n]+)_(?![\w_])", r"\1", text)
    return text.encode("latin-1", "replace").decode("latin-1")


class _BriefPdf(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4")
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(16, 16, 16)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("helvetica", "", 8)
        self.set_text_color(*INK_DIM)
        self.cell(0, 6, f"Agentic ML Workbench - page {self.page_no()}", align="C")


def _flush_table(pdf: _BriefPdf, rows: list[list[str]]) -> None:
    if not rows:
        return
    pdf.set_font("helvetica", "", 8.5)
    pdf.set_text_color(*INK)
    pdf.set_draw_color(*EDGE)
    with pdf.table(
        first_row_as_headings=True,
        line_height=5.5,
        padding=1.5,
        borders_layout="HORIZONTAL_LINES",
    ) as table:
        for r, row in enumerate(rows):
            tr = table.row()
            for cell in row:
                if r == 0:
                    pdf.set_font("helvetica", "B", 8.5)
                else:
                    pdf.set_font("helvetica", "", 8.5)
                tr.cell(_latin(cell))
    pdf.ln(3)


def build_report_pdf(run: Run) -> bytes:
    return markdown_to_pdf(build_report(run))


# QUERY-PATH EXTENSION (touch point c): the same renderer serves any
# markdown source, so query briefs and ML briefs can never drift apart.
def markdown_to_pdf(md: str) -> bytes:
    pdf = _BriefPdf()
    pdf.add_page()

    table_rows: list[list[str]] = []
    for raw in md.split("\n"):
        line = raw.rstrip()

        # Collect markdown table blocks, render them when the block ends.
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not all(set(c) <= {"-", ":", " "} for c in cells):  # skip |---| rows
                table_rows.append([c.replace("**", "") for c in cells])
            continue
        if table_rows:
            _flush_table(pdf, table_rows)
            table_rows = []

        if not line:
            pdf.ln(1.5)
        elif line.startswith("# "):
            pdf.set_font("helvetica", "B", 17)
            pdf.set_text_color(*ACCENT)
            pdf.multi_cell(0, 8, _latin(line[2:]))
            pdf.set_draw_color(*EDGE)
            pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.w - pdf.r_margin, pdf.get_y() + 1)
            pdf.ln(3)
        elif line.startswith("## "):
            pdf.ln(2)
            pdf.set_font("helvetica", "B", 12.5)
            pdf.set_text_color(*INK)
            pdf.multi_cell(0, 6.5, _latin(line[3:]))
            pdf.ln(0.5)
        elif line.startswith("### "):
            pdf.set_font("helvetica", "B", 10.5)
            pdf.set_text_color(*INK)
            pdf.multi_cell(0, 5.5, _latin(line[4:]))
        elif line.strip() == "---":
            pdf.ln(1)
            pdf.set_draw_color(*EDGE)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(2)
        elif re.match(r"^\d+\.\s", line) or line.startswith("- "):
            marker, _, rest = line.partition(" ")
            pdf.set_font("helvetica", "", 9.5)
            pdf.set_text_color(*INK)
            x = pdf.get_x()
            pdf.cell(7, 5.2, _latin(marker if marker != "-" else "\x95"))
            pdf.multi_cell(0, 5.2, _latin(rest.strip()), markdown=True)
            pdf.set_x(x)
        else:
            pdf.set_font("helvetica", "", 9.5)
            pdf.set_text_color(*INK)
            pdf.multi_cell(0, 5.2, _latin(line), markdown=True)

    if table_rows:
        _flush_table(pdf, table_rows)

    return bytes(pdf.output())
