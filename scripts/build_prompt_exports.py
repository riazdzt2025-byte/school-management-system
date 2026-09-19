#!/usr/bin/env python3
"""Build shareable exports of the session prompts in ``docs/prompts/``.

Outputs (all under ``docs/prompts/``)::

    export/School-Prompts-28-BN.pdf        combined PDF (cover + index + 28 prompts, bookmarks)
    export/School-Prompts-28-BN.docx       combined Word file (cover + index + 28 prompts)
    export/docx/prompt-NN-<slug>.docx      one Word file per prompt (hand one session at a time)
    copy-paste/prompt-NN-<slug>.txt        plain-text copy of each prompt (easiest to copy/paste)
    copy-paste/ALL_PROMPTS.txt             every prompt in one plain-text file

Bengali needs a shaped font, so the PDF is built with fpdf2 + HarfBuzz text shaping
and Noto fonts (Bengali / Mono / Symbols / Math / Symbols2 / Emoji).  The fonts are
downloaded on demand into ``~/.cache/prompt-exports/fonts`` (never committed).

Requirements::

    pip install fpdf2 uharfbuzz fonttools python-docx

Usage (from the repository root)::

    python3 scripts/build_prompt_exports.py [--prompts-dir docs/prompts] [--variants all|pdf|docx|txt]

Only the .md files are the source of truth — re-run this script after editing them.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------------------
# fonts
# --------------------------------------------------------------------------------------

FONT_DIRS = [
    Path(os.environ.get("PROMPT_FONTS_DIR", "")),
    Path.home() / ".cache" / "prompt-exports" / "fonts",
    Path("/tmp/fonts"),
]

# NotoSansBengali / NotoSansMono / NotoEmoji are variable fonts -> instanced to static.
# NotoSansSymbols / NotoSansMath / NotoSansSymbols2 are plain static fonts.
GOOGLE_FONTS = {
    "NotoSansBengali-VF.ttf": "ofl/notosansbengali/NotoSansBengali%5Bwdth,wght%5D.ttf",
    "NotoSansMono-VF.ttf": "ofl/notosansmono/NotoSansMono%5Bwdth,wght%5D.ttf",
    "NotoEmoji-VF.ttf": "ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf",
    "NotoSansSymbols-VF.ttf": "ofl/notosanssymbols/NotoSansSymbols%5Bwght%5D.ttf",
    "NotoSansSymbols2-Regular.ttf": "ofl/notosanssymbols2/NotoSansSymbols2-Regular.ttf",
    "NotoSansMath-Regular.ttf": "ofl/notosansmath/NotoSansMath-Regular.ttf",
}
INSTANCES = {
    "NotoSansBengali-Regular.ttf": ("NotoSansBengali-VF.ttf", {"wght": 400, "wdth": 100}),
    "NotoSansBengali-Bold.ttf": ("NotoSansBengali-VF.ttf", {"wght": 700, "wdth": 100}),
    "NotoSansMono-Regular.ttf": ("NotoSansMono-VF.ttf", {"wght": 400, "wdth": 100}),
    "NotoSansMono-Bold.ttf": ("NotoSansMono-VF.ttf", {"wght": 700, "wdth": 100}),
    "NotoEmoji-Regular.ttf": ("NotoEmoji-VF.ttf", {"wght": 400}),
    "NotoSansSymbols-Regular.ttf": ("NotoSansSymbols-VF.ttf", {"wght": 400}),
}

# characters fpdf substitutes when the whole font set lacks them
SUBSTITUTIONS = {
    "\u2192": "->", "\u2190": "<-", "\u21d2": "=>",
    "\u2265": ">=", "\u2264": "<=", "\u2260": "!=",
    "\u2020": "-", "\u2021": "--", "\u00a0": " ",
}


def _download(url_path: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:  # gh keeps working without touching raw.githubusercontent
        out = subprocess.run(
            ["gh", "api", "-H", "Accept: application/vnd.github.raw",
             f"repos/google/fonts/contents/{url_path}"],
            capture_output=True, check=True,
        )
        dest.write_bytes(out.stdout)
        return True
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"  gh download failed ({exc}); trying https")
    for url in (f"https://github.com/google/fonts/raw/main/{url_path}",
                f"https://raw.githubusercontent.com/google/fonts/main/{url_path}"):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                dest.write_bytes(resp.read())
            return True
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"  download failed: {url} ({exc})")
    return False


def ensure_fonts() -> Path:
    """Return a directory that holds every font file, downloading/instancing as needed."""
    target = Path.home() / ".cache" / "prompt-exports" / "fonts"
    target.mkdir(parents=True, exist_ok=True)
    needed = list(INSTANCES) + ["NotoSansMath-Regular.ttf"]
    have_all = all((target / name).exists() for name in needed)
    if not have_all:
        for name, path in GOOGLE_FONTS.items():
            if not (target / name).exists():
                print(f"  downloading {name}")
                _download(path, target / name)
        try:
            from fontTools.ttLib import TTFont
            from fontTools.varLib.instancer import instantiateVariableFont
        except ImportError:  # pragma: no cover
            sys.exit("fontTools is required: pip install fonttools")
        for name, (src, loc) in INSTANCES.items():
            if (target / name).exists():
                continue
            if not (target / src).exists():
                sys.exit(f"missing source font {src} — download failed")
            font = TTFont(target / src)
            instantiateVariableFont(font, loc, inplace=True, updateFontNames=True)
            font.save(target / name)
            print(f"  instanced {name}")
    return target


def coverage(font_dir: Path) -> set[int]:
    from fontTools.ttLib import TTFont
    covered: set[int] = set()
    for name in list(INSTANCES) + ["NotoSansMath-Regular.ttf"]:
        path = font_dir / name
        if path.exists():
            font = TTFont(path, lazy=True)
            covered |= set(font.getBestCmap().keys())
            font.close()
    return covered


# --------------------------------------------------------------------------------------
# markdown model
# --------------------------------------------------------------------------------------

INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")


@dataclass
class Block:
    kind: str                     # h1 h2 h3 p li ol quote code hr
    text: str = ""
    level: int = 0
    lang: str = ""
    lines: list[str] = field(default_factory=list)
    marker: str = ""


def parse_markdown(text: str) -> list[Block]:
    lines = text.split("\n")
    blocks: list[Block] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            body, i = [], i + 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i].rstrip("\n"))
                i += 1
            i += 1  # closing fence
            blocks.append(Block("code", lang=lang, lines=body))
            continue

        if not stripped:
            i += 1
            continue

        if set(stripped) == {"-"} and len(stripped) >= 3:
            blocks.append(Block("hr"))
            i += 1
            continue

        if stripped.startswith("### "):
            blocks.append(Block("h3", text=stripped[4:].strip()))
            i += 1
            continue
        if stripped.startswith("## "):
            blocks.append(Block("h2", text=stripped[3:].strip()))
            i += 1
            continue
        if stripped.startswith("# "):
            blocks.append(Block("h1", text=stripped[2:].strip()))
            i += 1
            continue

        if stripped.startswith("> "):
            body = [stripped[2:].strip()]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("> "):
                body.append(lines[i].strip()[2:].strip())
                i += 1
            blocks.append(Block("quote", text=" ".join(body)))
            continue

        m = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if m:
            body = [m.group(2)]
            i += 1
            while i < len(lines) and lines[i].startswith("   ") and lines[i].strip():
                body.append(lines[i].strip())
                i += 1
            blocks.append(Block("ol", text=" ".join(body).strip(), marker=f"{m.group(1)}."))
            continue

        if stripped.startswith("- "):
            body = [stripped[2:].strip()]
            i += 1
            while i < len(lines) and lines[i].startswith("  ") and lines[i].strip() \
                    and not lines[i].strip().startswith(("- ", "#")):
                body.append(lines[i].strip())
                i += 1
            blocks.append(Block("li", text=" ".join(body).strip()))
            continue

        # paragraph / whole-line italic caption
        body = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip() or nxt.startswith(("```", "#", "- ", "> ")) \
                    or re.match(r"^\d+\.\s", nxt.strip()) or set(nxt.strip()) == {"-"}:
                break
            body.append(nxt.strip())
            i += 1
        text_join = " ".join(body)
        if text_join.startswith("_") and text_join.endswith("_") and text_join.count("_") == 2:
            blocks.append(Block("p", text=text_join, level=1))  # italic caption
        else:
            blocks.append(Block("p", text=text_join))
    return blocks


def parse_inline(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append((part[2:-2], "B"))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            out.append((part[1:-1], "code"))
        else:
            out.append((part, ""))
    return out


# --------------------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------------------

PAGE_W, PAGE_H = 210, 297
MARGIN = 15.0
ACCENT = (13, 42, 80)        # navy
ACCENT_2 = (176, 132, 44)    # gold
GREY = (110, 116, 126)
CODE_BG = (243, 245, 248)


class PromptPDF:
    """Thin fpdf wrapper with one font per role and Bengali shaping."""

    def __init__(self, font_dir: Path, total_pages: int = 0):
        from fpdf import FPDF

        class _PDF(FPDF):
            outer = self

            def header(self):  # pragma: no cover - trivial
                if self.page_no() == 1 or self.outer.suppress_header \
                        or not self.outer.running_label:
                    return
                self.set_font("bn", "", 7.5)
                self.set_text_color(*GREY)
                self.set_xy(MARGIN, 8)
                self.cell(0, 5, self.outer.running_label, align="L")
                self.cell(0, 5, "School Management System — release prompts", align="R")
                self.set_draw_color(226, 229, 234)
                self.line(MARGIN, 14.5, PAGE_W - MARGIN, 14.5)
                self.set_text_color(0, 0, 0)
                self.set_y(max(self.get_y(), self.t_margin))

            def footer(self):  # pragma: no cover - trivial
                if self.page_no() == 1:
                    return
                self.set_y(-12)
                self.set_font("bn", "", 7.5)
                self.set_text_color(*GREY)
                total = self.outer.total_pages or self.page_no()
                y = self.get_y()
                self.cell(0, 5, f"পৃষ্ঠা {self.page_no()} / {total}", align="C")
                self.set_text_color(0, 0, 0)
                self.set_y(y)

        self.pdf = _PDF(format="A4")
        self.pdf.set_margins(MARGIN, 20, MARGIN)
        self.pdf.set_auto_page_break(True, margin=18)
        self.total_pages = total_pages
        self.running_label = ""
        self.suppress_header = False

        for role, (regular, bold) in {
            "bn": ("NotoSansBengali-Regular.ttf", "NotoSansBengali-Bold.ttf"),
            "mono": ("NotoSansMono-Regular.ttf", "NotoSansMono-Bold.ttf"),
        }.items():
            self.pdf.add_font(role, "", str(font_dir / regular))
            self.pdf.add_font(role, "B", str(font_dir / bold))
        for role, name in {"sym": "NotoSansSymbols-Regular.ttf",
                           "math": "NotoSansMath-Regular.ttf",
                           "sym2": "NotoSansSymbols2-Regular.ttf",
                           "emoji": "NotoEmoji-Regular.ttf"}.items():
            self.pdf.add_font(role, "", str(font_dir / name))
        self.pdf.set_text_shaping(True)
        self.pdf.set_fallback_fonts(["mono", "bn", "sym", "math", "sym2", "emoji"])

    # -- helpers -----------------------------------------------------------------
    def font(self, style: str, size: float):
        role, style_name = ("bn", "")
        if style == "B":
            style_name = "B"
        elif style == "code":
            role, style_name = "mono", ""
        self.pdf.set_font(role, style_name, size)

    def runs_width(self, runs: list[tuple[str, str]], size: float) -> float:
        total = 0.0
        for text, style in runs:
            self.font(style, size)
            total += self.pdf.get_string_width(text)
        return total

    def write_paragraph(self, blocks_runs: list[list[tuple[str, str]]], size: float,
                        line_h: float, indent: float = 0.0, marker: str = "",
                        color=None, justify: bool = False):
        """Lay out inline runs as wrapped lines inside the current text column."""
        width = PAGE_W - 2 * MARGIN - indent - 3.0    # safety margin for shaping widths
        tokens: list[tuple[str, str]] = []
        for runs in blocks_runs:
            for text, style in runs:
                for piece in re.split(r"(\s+)", text):
                    if piece:
                        tokens.append((piece, style))
        lines: list[list[tuple[str, str]]] = []
        current: list[tuple[str, str]] = []
        current_w = 0.0
        for word, style in tokens:
            self.font(style, size)
            w = self.pdf.get_string_width(word)
            if current and current_w + w > width and not word.isspace():
                lines.append(current)
                current, current_w = [], 0.0
            if word.isspace() and not current:
                continue
            current.append((word, style))
            current_w += w
        if current:
            lines.append(current)

        if marker:
            if marker == "\u2022":
                self.pdf.set_font("sym", "", size)
            else:
                self.font("B", size)
            self.pdf.set_x(MARGIN + indent - 6)
            self.pdf.write(line_h, marker)
            self.pdf.set_x(MARGIN + indent)
        for idx, line in enumerate(lines):
            if color:
                self.pdf.set_text_color(*color)
            self.pdf.set_x(MARGIN + indent)
            for word, style in line:
                self.font(style, size)
                self.pdf.write(line_h, word)
            self.pdf.ln(line_h)
            if color:
                self.pdf.set_text_color(0, 0, 0)

    def code_block(self, lines: list[str], size: float = 8.0, line_h: float = 4.3):
        if not lines:
            return
        inner_w = PAGE_W - 2 * MARGIN - 6
        wrapped: list[str] = []
        self.font("code", size)
        for line in lines:
            if not line:
                wrapped.append("")
                continue
            while self.pdf.get_string_width(line) > inner_w:
                cut = len(line)
                while cut > 1 and self.pdf.get_string_width(line[:cut]) > inner_w:
                    cut -= 1
                wrapped.append(line[:cut])
                line = "    " + line[cut:]
            wrapped.append(line)
        height = line_h * len(wrapped) + 4
        if self.pdf.get_y() + min(height, line_h * 3) > PAGE_H - 20:
            self.pdf.add_page()
        x, y = MARGIN, self.pdf.get_y()
        self.pdf.set_fill_color(*CODE_BG)
        self.pdf.set_draw_color(224, 228, 234)
        self.pdf.rect(x, y, PAGE_W - 2 * MARGIN, height, style="DF")
        self.pdf.set_xy(x + 3, y + 2)
        self.pdf.set_text_color(20, 30, 50)
        for line in wrapped:
            self.font("code", size)
            self.pdf.set_x(x + 3)
            self.pdf.write(line_h, line if line else " ")
            self.pdf.ln(line_h)
        self.pdf.set_text_color(0, 0, 0)
        self.pdf.set_xy(MARGIN, max(y + height, self.pdf.get_y()) + 1.5)

    def rule(self, space_before: float = 1.5, space_after: float = 2.5):
        self.pdf.ln(space_before)
        self.pdf.set_draw_color(*ACCENT_2)
        y = self.pdf.get_y()
        self.pdf.line(MARGIN, y, MARGIN + 40, y)
        self.pdf.ln(space_after)

    def page_break(self):
        self.pdf.add_page()

    def section(self, label: str):
        try:
            self.pdf.start_section(label, level=0)
        except Exception:  # pragma: no cover - older fpdf without outline support
            pass

    def output(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.pdf.output(str(path))


def sanitize(text: str, covered: set[int], report: list[str]) -> str:
    out = []
    for ch in text:
        if ord(ch) in covered or ch in "\n\t":
            out.append(ch)
            continue
        replacement = SUBSTITUTIONS.get(ch, "")
        if replacement:
            out.append(replacement)
        report.append(f"{ch!r} U+{ord(ch):04X}")
    return "".join(out)


def render_prompt(pdf: PromptPDF, num: int, meta: dict, blocks: list[Block],
                  toc_pages: dict | None, record: dict | None):
    pdf.running_label = f"প্রম্পট {num:02d} / {meta['total']} — সেশন {meta['sid']}"
    pdf.suppress_header = True          # a prompt's first page carries its own title
    pdf.page_break()
    pdf.suppress_header = False
    pdf.section(f"প্রম্পট {num:02d} — {meta['sid']} · {meta['title']}")
    if record is not None:
        record[num] = pdf.pdf.page_no()

    # title
    pdf.pdf.set_text_color(*ACCENT)
    pdf.write_paragraph([parse_inline(f"প্রম্পট {num:02d} / {meta['total']} — {meta['sid']} · "
                                     f"{meta['title']}")], 14.5, 8.0)
    pdf.pdf.set_text_color(*GREY)
    pdf.write_paragraph([[ (meta["meta"], "") ]], 9.0, 5.2)
    pdf.pdf.set_text_color(0, 0, 0)

    if meta["note"]:
        pdf.write_paragraph([parse_inline(meta["note"])], 8.6, 4.9, indent=3.0, color=GREY)

    for block in blocks:
        if block.kind == "h1":
            continue  # already used as the page title
        if block.kind == "hr":
            pdf.rule()
        elif block.kind == "h2":
            pdf.pdf.ln(2.0)
            pdf.pdf.set_text_color(*ACCENT)
            pdf.write_paragraph([parse_inline(block.text)], 11.5, 6.6)
            pdf.pdf.set_text_color(0, 0, 0)
        elif block.kind == "h3":
            pdf.pdf.ln(1.2)
            pdf.write_paragraph([parse_inline(block.text)], 10.2, 5.9)
        elif block.kind == "li":
            pdf.write_paragraph([parse_inline(block.text)], 9.6, 5.5, indent=5.0,
                                marker="•")
        elif block.kind == "ol":
            pdf.write_paragraph([parse_inline(block.text)], 9.6, 5.5, indent=6.0,
                                marker=block.marker)
        elif block.kind == "quote":
            pdf.write_paragraph([parse_inline(block.text)], 9.2, 5.3, indent=5.0,
                                color=GREY)
        elif block.kind == "code":
            pdf.pdf.ln(0.8)
            pdf.code_block(block.lines)
            pdf.pdf.ln(0.8)
        else:  # paragraph or italic caption
            if block.level == 1:
                pdf.write_paragraph([[(block.text.strip("_"), "")]], 9.2, 5.4, color=GREY)
            else:
                pdf.write_paragraph([parse_inline(block.text)], 9.9, 5.6)


def build_pdf(prompts: list[dict], font_dir: Path, outfile: Path, covered: set[int],
              substitutions: list[str]):
    # ---- pass 1: measure page numbers for the index --------------------------------
    pages: dict[int, int] = {}
    pdf = PromptPDF(font_dir)
    pdf.pdf.add_page()
    for p in prompts:
        render_prompt(pdf, p["num"], p, p["blocks"], None, pages)
    total = pdf.pdf.pages_count + 1          # + cover page (index adds the other page)
    pages = {num: page + 1 for num, page in pages.items()}   # + cover page offset
    del pdf

    # ---- pass 2: real render -------------------------------------------------------
    pdf = PromptPDF(font_dir, total_pages=total)

    # cover
    pdf.pdf.add_page()
    pdf.pdf.set_fill_color(*ACCENT)
    pdf.pdf.rect(0, 0, PAGE_W, 62, style="F")
    pdf.pdf.set_fill_color(*ACCENT_2)
    pdf.pdf.rect(0, 62, PAGE_W, 2.2, style="F")
    pdf.pdf.set_xy(MARGIN, 20)
    pdf.pdf.set_text_color(255, 255, 255)
    pdf.write_paragraph([[( "School Management System", "B" )]], 15, 8.2)
    pdf.write_paragraph([[( "প্রথম production release — ২৮টি সেশন প্রম্পট", "B" )]], 18, 10.0)
    pdf.write_paragraph([[( "Principal Kazi Faruky School And College", "" )]], 10, 5.6)
    pdf.pdf.set_text_color(0, 0, 0)
    pdf.pdf.set_xy(MARGIN, 78)
    pdf.write_paragraph([[( "এই PDF-এ ২৮টি ক্রমিক প্রম্পট আছে — প্রতিটি prompt কপি করে এজেন্টকে দিন, "
                            "সেশন শেষে এজেন্ট docs/prompts/PROGRESS.md-এ নিজের সারি আপডেট করবে।", "" )]], 10.5, 6.0)
    pdf.pdf.ln(2)
    pdf.write_paragraph([[( "ক্রম: ০১ (সেশন ০০ যাচাই) → EX-01…EX-07 → OF-01…OF-08 → DB-01…DB-06 → "
                            "AT-01…AT-02 → EM-01…EM-03 → FN-01", "" )]], 10.5, 6.0)
    pdf.pdf.ln(4)
    pdf.pdf.set_font("bn", "B", 11)
    pdf.pdf.multi_cell(0, 6.4, f"মোট পৃষ্ঠা: {total} · প্রম্পট: {len(prompts)}টি · "
                               f"branch: arena/01a0b7f7-school-management-system · base: f64194a")

    # index
    pdf.pdf.add_page()
    pdf.pdf.set_text_color(*ACCENT)
    pdf.pdf.set_font("bn", "B", 16)
    pdf.pdf.multi_cell(0, 9, "সূচি — ২৮ প্রম্পট")
    pdf.pdf.set_text_color(0, 0, 0)
    pdf.pdf.ln(2)
    pdf.pdf.set_font("bn", "", 9.6)
    for p in prompts:
        nr = p["num"]
        label = f"প্রম্পট {nr:02d} — {p['sid']} · {p['title']}"
        pdf.font("code" if False else "bn", 9.6)
        pdf.pdf.set_x(MARGIN)
        pdf.pdf.cell(160, 6.2, label)
        pdf.pdf.set_text_color(*GREY)
        pdf.pdf.cell(0, 6.2, f"পৃষ্ঠা {pages.get(nr, '—')}", align="R")
        pdf.pdf.set_text_color(0, 0, 0)
        pdf.pdf.ln(6.2)
    pdf.pdf.ln(3)
    pdf.write_paragraph([[( "প্রতিটি prompt-এর শুরুতে ও শেষে বাধ্যতামূলক স্ট্যাটাস ব্লক থাকবে — "
                            "যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কোনটি শেষ হয়েছে।", "" )]], 9.6, 5.6,
                        color=GREY)

    for p in prompts:
        render_prompt(pdf, p["num"], p, p["blocks"], None, None)

    pdf.output(outfile)
    return total


# --------------------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------------------

def build_docx(prompts: list[dict], outfile: Path, combined: bool = True):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor, Inches

    BN_FONT = "Nirmala UI"     # ships with Windows; Word falls back gracefully elsewhere
    MONO_FONT = "Consolas"

    doc = Document()

    def set_run_font(run, name, size=None, bold=None, color=None):
        run.font.name = name
        if size:
            run.font.size = Pt(size)
        if bold is not None:
            run.bold = bold
        if color:
            run.font.color.rgb = RGBColor(*color)
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.get_or_add_rFonts()
        rfonts.set(qn("w:ascii"), name)
        rfonts.set(qn("w:hAnsi"), name)
        rfonts.set(qn("w:cs"), name)

    normal = doc.styles["Normal"]
    normal.font.name = BN_FONT
    normal.font.size = Pt(10.5)
    rpr = normal.element.get_or_add_rPr()
    rpr.get_or_add_rFonts().set(qn("w:cs"), BN_FONT)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.12

    for name, size, color in (("Heading 1", 17, ACCENT), ("Heading 2", 12.5, ACCENT),
                              ("Heading 3", 11, (40, 40, 40))):
        st = doc.styles[name]
        st.font.name = BN_FONT
        st.font.size = Pt(size)
        st.font.color.rgb = RGBColor(*color)
        st.font.bold = True
        st.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:cs"), BN_FONT)

    def add_page_number_footer(section):
        paragraph = section.footer.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run()
        for instruction, kind in (("PAGE", "begin"), (None, None), (None, "end")):
            pass
        fld_begin = OxmlElement("w:fldChar"); fld_begin.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve"); instr.text = "PAGE"
        fld_end = OxmlElement("w:fldChar"); fld_end.set(qn("w:fldCharType"), "end")
        run._element.append(fld_begin); run._element.append(instr); run._element.append(fld_end)
        set_run_font(run, BN_FONT, 8.5, color=GREY)

    add_page_number_footer(doc.sections[0])

    def add_runs(paragraph, text, size=10.5, base_bold=False):
        for chunk, style in parse_inline(text):
            run = paragraph.add_run(chunk)
            if style == "code":
                set_run_font(run, MONO_FONT, size - 0.7, bold=False)
            else:
                set_run_font(run, BN_FONT, size, bold=base_bold or style == "B")

    if combined:
        title = doc.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.LEFT
        set_run_font(title.add_run("School Management System — প্রথম production release"),
                     BN_FONT, 20, bold=True, color=ACCENT)
        sub = doc.add_paragraph()
        set_run_font(sub.add_run("২৮টি ক্রমিক সেশন প্রম্পট (০০ · EX-01…EX-07 · OF-01…OF-08 · "
                                 "DB-01…DB-06 · AT-01…AT-02 · EM-01…EM-03 · FN-01)"),
                     BN_FONT, 12, color=GREY)
        meta = doc.add_paragraph()
        set_run_font(meta.add_run("branch: arena/01a0b7f7-school-management-system · base: f64194a · "
                                  "ledger: docs/prompts/PROGRESS.md"), BN_FONT, 9, color=GREY)

        doc.add_paragraph()
        h = doc.add_paragraph()
        set_run_font(h.add_run("সূচি"), BN_FONT, 14, bold=True, color=ACCENT)
        for p in prompts:
            row = doc.add_paragraph(style="List Number")
            row.paragraph_format.space_after = Pt(1)
            set_run_font(row.add_run(f"{p['num']:02d} · {p['sid']} — {p['title']}"), BN_FONT, 10)

    for idx, p in enumerate(prompts):
        doc.add_page_break()
        heading = doc.add_paragraph()
        set_run_font(heading.add_run(f"প্রম্পট {p['num']:02d} / {p['total']} — সেশন {p['sid']} · {p['title']}"),
                     BN_FONT, 16, bold=True, color=ACCENT)
        meta = doc.add_paragraph()
        set_run_font(meta.add_run(p["meta"]), BN_FONT, 9, color=GREY)

        for block in p["blocks"]:
            if block.kind == "h1":
                continue
            if block.kind == "hr":
                para = doc.add_paragraph()
                ppr = para._p.get_or_add_pPr()
                borders = OxmlElement("w:pBdr")
                bottom = OxmlElement("w:bottom")
                bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "6")
                bottom.set(qn("w:color"), "B0842C")
                borders.append(bottom); ppr.append(borders)
                para.paragraph_format.space_after = Pt(4)
            elif block.kind in ("h2", "h3"):
                para = doc.add_paragraph(style="Heading 2" if block.kind == "h2" else "Heading 3")
                add_runs(para, block.text, size=12.5 if block.kind == "h2" else 11,
                         base_bold=True)
            elif block.kind == "li":
                para = doc.add_paragraph(style="List Bullet")
                add_runs(para, block.text)
            elif block.kind == "ol":
                para = doc.add_paragraph(style="List Number")
                add_runs(para, block.text)
            elif block.kind == "quote":
                para = doc.add_paragraph()
                para.paragraph_format.left_indent = Inches(0.28)
                add_runs(para, block.text, size=9.8)
                for run in para.runs:
                    set_run_font(run, run.font.name, 9.8, color=(90, 94, 102))
            elif block.kind == "code":
                for line in block.lines or [""]:
                    para = doc.add_paragraph()
                    para.paragraph_format.space_after = Pt(0)
                    para.paragraph_format.left_indent = Inches(0.18)
                    shd = OxmlElement("w:shd")
                    shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "F3F5F8")
                    para._p.get_or_add_pPr().append(shd)
                    set_run_font(para.add_run(line or " "), MONO_FONT, 8.5)
                doc.add_paragraph().paragraph_format.space_after = Pt(0)
            else:
                para = doc.add_paragraph()
                if block.level == 1:
                    add_runs(para, block.text.strip("_"), size=9.8)
                    for run in para.runs:
                        set_run_font(run, run.font.name, 9.8, color=(90, 94, 102))
                else:
                    add_runs(para, block.text)
    outfile.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(outfile))


# --------------------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------------------

HEADER_META = re.compile(r"^_(.+)_$")


def load_prompts(prompts_dir: Path, covered: set[int], substitutions: list[str]):
    files = sorted(prompts_dir.glob("prompt-*.md"))
    if not files:
        sys.exit(f"no prompt-*.md under {prompts_dir}")
    prompts = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^#\s+প্রম্পট\s+([০-৯\d]+)\s*/\s*([০-৯\d]+)\s*—\s*সেশন\s+(\S+)\s*·\s*(.+)$",
                     text.split("\n")[0])
        if not m:
            sys.exit(f"cannot parse title line of {path}")
        num_bn, total_bn, sid, title = m.group(1), m.group(2), m.group(3), m.group(4).strip()
        num = int(num_bn.translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")))
        total = int(total_bn.translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")))
        lines = text.split("\n")
        meta = lines[2].strip().strip("_") if len(lines) > 2 else ""
        note = ""
        for line in lines[:8]:
            if line.startswith("> "):
                note = line[2:].strip()
                break
        blocks = parse_markdown(text)
        # the meta line and the usage note are rendered separately -> drop the duplicates
        meta_plain = meta.strip().strip("_").strip()
        blocks = [b for b in blocks
                  if b.text.strip().strip("_").strip() != meta_plain]
        if note:
            blocks = [b for b in blocks if note not in b.text]
        # clean text: substitute unsupported glyphs, keep source files untouched
        for b in blocks:
            b.text = sanitize(b.text, covered, substitutions)
            b.lines = [sanitize(l, covered, substitutions) for l in b.lines]
        dep_match = re.search(r"নির্ভরতা:\s*(.+)$", meta)
        prompts.append({
            "num": num, "total": total, "title": sanitize(title, covered, substitutions),
            "meta": sanitize(meta, covered, substitutions),
            "note": sanitize(note, covered, substitutions),
            "sid": sid,
            "depends": dep_match.group(1).strip() if dep_match else "",
            "blocks": blocks,
            "slug": path.stem,
        })
    return prompts



# --------------------------------------------------------------------------------------
# START blocks — what to paste into a *new* agent session
# --------------------------------------------------------------------------------------

KICKOFF = """▶ নতুন সেশন — প্রম্পট __NNB__ / ২৮ (সেশন __SID__ · __TITLE__)

আমি একটি নতুন agent-সেশনে আছি; তোমার আগের কথোপকথনের কিছু মনে নেই। নিয়ম:

১. আগে শুধু পড়ো (কোনো ফাইল বদলানোর আগে):
   - `docs/prompts/PROGRESS.md` — কোন প্রম্পট শেষ (✅/🟡/⛔), তাদের commit/PR ও নোট
   - `docs/prompts/README.md` §৭ — owner-সিদ্ধান্তের সারি
   - __DEP_REPORTS__ — আগের সেশনের প্রকৃত ফল, ঝুঁকি ও যাচাই-না-হওয়া অংশ
   - `docs/prompts/reports/০০.md` — baseline verdict (কোনটি ইতিমধ্যেই আছে)
   - `docs/prompts/prompt-__NN__-*.md` — এটাই তোমার কাজের স্পেক (ধাপ, সীমা, কমান্ড, PR, ডক)
২. তারপর যাচাই করো (দাবি নয়, প্রমাণ): `git log --oneline -12`, `git status -sb`,
   `git rev-parse HEAD origin/main`। প্রম্পট ০১…__PREVB__ ✅ হলে তাদের কাজ এই branch-এ আছে কি না দেখো।
   → ⚠️ আগের প্রম্পট 🟡/⛔ হলে বা commit না থাকলে **কাজ শুরু করবে না**; এক লাইনে জানাও কী অনুপস্থিত।
   → (ব্যতিক্রম: নিচে আমি লিখে দিলে) __OVERRIDE__
৩. owner-সিদ্ধান্ত: নিচে আমি যা লিখেছি সেটাই চূড়ান্ত। খালি থাকলে prompt-এর §৮-এর প্রশ্নগুলোর উত্তর
   আগে repo-তে খোঁজো (README §৭, reports) — না পেলে সংক্ষেপে প্রশ্ন করো, বানিয়ে কিছু ধরে নিও না।
   --- owner-সিদ্ধান্ত (থাকলে এখানে লিখুন; না থাকলে ফাঁকা রাখুন): __DECISIONS__
   ---
৪. এরপর prompt-এর §০ অনুযায়ী শুরু করো — প্রথম লাইনে স্ট্যাটাস ব্লক:
   `▶ চলছে: প্রম্পট __NN__ / ২৮ (prompt __NN__/28) — সেশন __SID__ · ...`
   এবং prompt-এর §৩–§৯ হুবহু মানো (ধাপ, টেস্ট কমান্ড, PR+CI, ডক/ledger আপডেট, আউটপুট ফরম্যাট)।
৫. শেষে: `docs/prompts/PROGRESS.md`-এ প্রম্পট __NNB__-এর সারি আপডেট (স্ট্যাটাস · তারিখ · commit · PR ·
   টেস্ট সংখ্যা) + `docs/prompts/reports/__SID__.md` লিখো + `✔ শেষ হয়েছে: প্রম্পট __NNB__ / ২৮ …` ব্লক দেখাও।
৬. নিষেধ (prompt-এর §৪-এ বিস্তারিত): branch `arena/01a0b7f7-school-management-system` ছাড়া অন্য কোথাও নয় ·
   `main`-এ push নয় · owner অনুমোদন ছাড়া merge নয় · production DB/live Render/credential ছোঁবা না ·
   SSC Registration পুনরুদ্ধার নয় · migration-এর operations edit নয় · `.env`/`db.sqlite3`/`media/`/`backups/` commit নয়।
"""

HANDOFF_INTRO = """# কীভাবে একটি নতুন সেশনে প্রম্পট শুরু করবেন (START-গাইড)

_উদ্দেশ্য: আগের কথোপকথন মনে নেই এমন নতুন agent-সেশনে যেকোনো নম্বরের প্রম্পট ঠিক জায়গা থেকে শুরু করা।_

## ১. মাত্র দুইটি জিনিস পাঠাবেন

1. **START-ব্লক** — `docs/prompts/copy-paste/kickoff/prompt-<NN>-START.txt` (সংখ্যা-ভরা, তৈরি করা)। জেনেরিক সংস্করণ §৩-এ।
2. **প্রম্পট ফাইল** — `docs/prompts/copy-paste/prompt-<NN>-*.txt` (বা `docs/prompts/prompt-<NN>-*.md`) — এটাই কাজের স্পেক: চাহিদা, ধাপ, সীমা, টেস্ট কমান্ড, PR+CI, ডক আপডেট, owner-প্রশ্ন।

> ব্যস। আর কিছু লিখতে/বুঝিয়ে দিতে হয় না — বাকি সব **repo-তেই আছে**, এজেন্ট নিজে পড়ে ও যাচাই করে।

## ২. কেন এতটুকুই যথেষ্ট (তিন-ভাগের চুক্তি)

| কী | কোথায় থাকে | কে দেয় |
|---|---|---|
| কাজের স্পেক (কী করতে হবে) | `docs/prompts/prompt-NN-*.md` | আপনি (কপি-পেস্ট) |
| অবস্থা (কোন প্রম্পট শেষ, commit/PR, কী যাচাই হয়েছে, কী বাকি) | `docs/prompts/PROGRESS.md` + `docs/prompts/reports/*.md` | repo — এজেন্ট পড়ে **নিজে প্রমাণ করে** |
| owner-সিদ্ধান্ত (নীতি/সংখ্যা/অনুমোদন) | `docs/prompts/README.md` §৭ + reports + আপনার মেসেজের ফাঁকা ঘর | আপনি (থাকলে) |

তিনটিই থাকলে নতুন সেশনে "কোথায় আছি" হারায় না।

## ৩. জেনেরিক START-ব্লক (যেকোনো প্রম্পটে ব্যবহারযোগ্য)

`<NN>`, `<SID>`, `<TITLE>`, `<PREV>` পূরণ করলেই চলে; `copy-paste/kickoff/`-এ প্রতিটি প্রম্পটের **আগেই পূরণ করা** সংস্করণ আছে।

```text
__GENERIC__
```

## ৪. প্রতিটি প্রম্পটের START ফাইল ও আগে-পড়ার তালিকা

| # | সেশন | START ফাইল | আগের যে রিপোর্টগুলো পড়া দরকার | §৮-এ owner-প্রশ্ন |
|---|---|---|---|---|
__TABLE__

## ৫. উদাহরণ: প্রম্পট ০৪ (EX-03) পুরো START-ব্লক

```text
__P04__
```

## ৬. বাস্তবে যা ঘটবে

1. এজেন্ট `PROGRESS.md` পড়ে দেখবে প্রম্পট ০১–০৩-এর অবস্থা; `git log` দিয়ে commit মিলিয়ে নেবে।
2. `reports/০০.md`, `reports/EX-01.md`, `reports/EX-02.md` পড়ে বুঝবে আগের সেশনে কী বদলেছে (আপনার লিখে দেওয়ার দরকার নেই)।
3. prompt-০৪-এর §০ স্ট্যাটাস ব্লক দিয়ে শুরু করবে, §৩ ধাপ ধরে কাজ করবে, §৫-এর কমান্ড চালাবে।
4. শেষে `PROGRESS.md`-এ প্রম্পট ০৪-এর সারি + `reports/EX-03.md` + PR আপডেট করে `✔ শেষ হয়েছে…` ব্লক দেখাবে।

## ৭. যদি আগের প্রম্পট শেষ না থাকে / আংশিক থাকে

- **আগের প্রম্পট অন্য সেশনে শেষ হয়েছে, কিন্তু PROGRESS.md-এ লেখা হয়নি:** START-ব্লকের ২ নম্বর ধাপের ব্যতিক্রম-লাইনে লিখুন — “প্রম্পট ০১–০৩ আমি অন্য সেশনে করেছি; branch-এ কাজগুলো যাচাই করে PROGRESS.md-এ স্ট্যাটাস বসাও, নতুন করে কোরো না।”
- **আগের প্রম্পট আংশিক/ব্লকড:** আগে সেটিই শেষ করুন, নাহলে এই প্রম্পটের নির্ভরতা ভাঙবে। (নাহলে START-ব্লকের owner-সিদ্ধান্তে লিখে দিন “০৩ আংশিক; বাকি ছিল X — সেটা এড়িয়ে এগোও” এবং ঝুঁকি মেনে নিন।)
- **জরুরি কিছু জানাতে চান (নীতি, সংখ্যা, নাম):** START-ব্লকের ৩ নম্বর ধাপের ফাঁকা ঘরে ২–৪ লাইন লিখুন।

## ৮. সর্বনিম্ন নিরাপদ এক-লাইন (যদি পুরো START ব্লক না পাঠাতে চান)

পুরো START ব্লকের বদলে অন্তত এই এক লাইনটি লিখুন (এতে ঝুঁকি সবচেয়ে কম):

```text
docs/prompts/prompt-04-*.md পড়ে তার §০–§৯ হুবহু মানো। আগে docs/prompts/PROGRESS.md ও
docs/prompts/reports/EX-02.md পড়ে যাচাই করো প্রম্পট ০১–০৩ আসলে শেষ কি না (না হলে শুরু কোরো না, জানাও)।
owner-সিদ্ধান্ত: <থাকলে>। শেষে PROGRESS.md + reports/EX-03.md আপডেট করে স্ট্যাটাস ব্লক দেখাও।
```

**কেন পুরো ব্লক ভালো:** শুধু "প্রম্পট ৪ পড়ে কাজ কর" লিখলে এজেন্ট ফাইল খুঁজে পেলেও (ক) আগের প্রম্পট শেষ কি না
যাচাই না করে ফেলে দিতে পারে, (খ) owner-সিদ্ধান্তের কথা জানে না, (গ) `PROGRESS.md`/report আপডেট করতে ভুলে যেতে পারে।

## ৯. এজেন্টকে থামানোর শর্ত (START-ব্লকে আগেই লেখা থাকে)

- আগের নির্ভরতা ✅ নয় বা commit অনুপস্থিত → **শুরু করবে না**, জানাবে।
- owner-সিদ্ধান্ত ছাড়া কিছু "ধরে নেওয়া" নিষেধ → প্রশ্ন করবে।
- টেস্ট fail / CI fail → স্ট্যাটাস 🟡, লুকাবে না।
"""


def _dep_report_list(prompts, p):
    """Return the statement about which previous session reports to read."""
    total = len(prompts)
    nums = []
    for m in re.finditer(r"প্রম্পট\s+([০-৯\d]+)", p["depends"]):
        nums.append(int(m.group(1).translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789"))))
    if "সব" in p["depends"]:
        nums = list(range(1, total))
    if p["num"] - 1 not in nums and p["num"] > 1:
        nums.append(p["num"] - 1)
    nums = sorted({n for n in nums if 1 <= n <= total})
    labels = [f"`docs/prompts/reports/{prompts[n - 1]['sid']}.md`" for n in nums]
    if not labels:
        return "`docs/prompts/reports/` (আগের কোনো সেশন নেই)"
    if len(labels) > 4:
        return (f"`docs/prompts/reports/` — বিশেষভাবে {labels[0]} … {labels[-1]} "
                f"({len(labels)}টি রিপোর্ট: সব আগের সেশন)")
    return " ও ".join(labels)


def build_handoff(prompts, root, copy_paste_dir):
    total = len(prompts)

    kickoff_dir = copy_paste_dir / "kickoff"
    kickoff_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in prompts:
        dep_reports = _dep_report_list(prompts, p)
        bn = str(p['num']).translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))
        bn2 = f"{p['num']:02d}".translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))
        prev_bn = (f"{p['num'] - 1:02d}".translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))
                   if p["num"] > 1 else "—")
        block = (KICKOFF
                 .replace("__NNB__", bn2)
                 .replace("__PREVB__", prev_bn)
                 .replace("__NN__", f"{p['num']:02d}")
                 .replace("__SID__", p["sid"])
                 .replace("__TITLE__", p["title"])
                 .replace("__PREV__", f"{p['num'] - 1:02d}" if p["num"] > 1 else "—")
                 .replace("__DEP_REPORTS__", dep_reports)
                 .replace("__OVERRIDE__", "—"))
        (kickoff_dir / f"prompt-{p['num']:02d}-START.txt").write_text(block, encoding="utf-8")

        text = (root / f"{p['slug']}.md").read_text(encoding="utf-8")
        section = text.split("## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে", 1)
        count = 0
        if len(section) == 2:
            body = section[1].split("## ৯.", 1)[0]
            count = len(re.findall(r"^- ", body, flags=re.M))
        rows.append("| {n:02d} | {sid} | `copy-paste/kickoff/prompt-{n:02d}-START.txt` | {dep} | {c}টি |"
                    .format(n=p["num"], sid=p["sid"], dep=dep_reports, c=count))

    generic = (KICKOFF
               .replace("__NNB__", "<০N>").replace("__PREVB__", "<আগের নম্বর>")
               .replace("__NN__", "<NN>").replace("__SID__", "<সেশন আইডি>")
               .replace("__TITLE__", "<শিরোনাম>").replace("__PREV__", "<আগের প্রম্পটের নম্বর>")
               .replace("__DEP_REPORTS__", "`docs/prompts/reports/` — আগের সব সেশনের রিপোর্ট")
               .replace("__OVERRIDE__", "<থাকলে লিখুন: আগের প্রম্পট আমি অন্য সেশনে করেছি — যাচাই করে স্ট্যাটাস বসাও>"))

    p04 = prompts[3]
    p04_block = (KICKOFF
                 .replace("__NNB__", "০৪").replace("__PREVB__", "০৩")
                 .replace("__NN__", "04").replace("__SID__", p04["sid"])
                 .replace("__TITLE__", p04["title"]).replace("__PREV__", "03")
                 .replace("__DEP_REPORTS__", _dep_report_list(prompts, p04))
                 .replace("__OVERRIDE__", "—"))

    doc = (HANDOFF_INTRO
           .replace("__GENERIC__", generic)
           .replace("__P04__", p04_block)
           .replace("__TABLE__", "\n".join(rows)))
    (root / "HANDOFF-START.md").write_text(doc, encoding="utf-8")
    print(f"handoff written: HANDOFF-START.md + {total} START files")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts-dir", default="docs/prompts")
    ap.add_argument("--variants", default="all", choices=["all", "pdf", "docx", "txt"])
    args = ap.parse_args()

    root = Path(args.prompts_dir).resolve()
    print("resolving fonts …")
    font_dir = ensure_fonts()
    covered = coverage(font_dir)
    substitutions: list[str] = []
    prompts = load_prompts(root, covered, substitutions)
    print(f"loaded {len(prompts)} prompts from {root}")
    if substitutions:
        uniq = sorted(set(substitutions))
        print(f"  glyph substitutions applied: {', '.join(uniq)}")

    export_dir = root / "export"
    if args.variants in ("all", "pdf"):
        total = build_pdf(prompts, font_dir, export_dir / "School-Prompts-28-BN.pdf", covered,
                          substitutions)
        print(f"pdf written ({total} pages)")
    if args.variants in ("all", "docx"):
        build_docx(prompts, export_dir / "School-Prompts-28-BN.docx", combined=True)
        for p in prompts:
            build_docx([p], export_dir / "docx" / f"{p['slug']}.docx", combined=False)
        print("docx written (combined + one per prompt)")
    if args.variants in ("all", "txt"):
        cp = root / "copy-paste"
        cp.mkdir(parents=True, exist_ok=True)
        for path in sorted(root.glob("prompt-*.md")):
            (cp / (path.stem + ".txt")).write_text(path.read_text(encoding="utf-8"),
                                                   encoding="utf-8")
        parts = ["ALL PROMPTS — ২৮টি সেশন (এক ফাইলে, ক্রমানুসারে)\n",
                 "প্রতিটি prompt আলাদা করে এজেন্টকে দিন। সেশন শেষে এজেন্ট "
                 "docs/prompts/PROGRESS.md-এ নিজের সারি আপডেট করবে।\n"]
        for path in sorted(root.glob("prompt-*.md")):
            parts.append("\n\n" + "=" * 90 + "\n\n")
            parts.append(path.read_text(encoding="utf-8").rstrip() + "\n")
        (cp / "ALL_PROMPTS.txt").write_text("".join(parts), encoding="utf-8")
        print("copy-paste txt written (28 + ALL_PROMPTS.txt)")
        build_handoff(prompts, root, cp)


if __name__ == "__main__":
    main()
