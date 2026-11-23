#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""literature-translator — mechanical integrity tooling for paper translation.

Stdlib-only core for the "literature-translator" Agent Skill. The LLM does the
language work; this script does the *accounting* that keeps a paper translation
verifiable:

  segment     split extracted source text into numbered paragraphs (P0001..)
  candidates  propose glossary terms (acronyms, "X (Y)" definitions, repeated phrases)
  protect     extract numbers/units/formulas/citation & figure/table/eq markers;
              with --mask-out it also writes the ⟨PLACEHOLDER⟩-masked text
  restore     put protected tokens back after translation (⟨ID⟩ -> original text)
  align       build source-paragraph <-> target-paragraph pairs from IDs
  qa          check term drift, missing/reordered paragraphs, protected-token
              fidelity, number/unit drift, negation/qualifier drift

Every subcommand reads and writes UTF-8 text. No third-party packages are
required. PDF text extraction is attempted through optional imports (pypdf,
PyMuPDF/fitz, pdfminer) and falls back to the `pdftotext` binary or a clear
error telling the caller what to do. If OCR was used instead of a native text
layer, the caller must pass --ocr so downstream checks are graded as low
confidence instead of silently treated as authoritative.

Exit codes:
  0  OK
  1  usage / IO / parse error
  2  QA issues found (non-fatal; report still written)
  3  required input missing -> needs human/agent intervention
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter, OrderedDict
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SENTENCE_END = re.compile(r'[.!?…]["\')\]]*\s*$')
TERMINAL_PUNCT = ".!?…;:"

NEGATIONS_EN = [
    "not", "no", "never", "neither", "nor", "none", "nothing", "nobody",
    "without", "unless", "cannot", "can not", "can't", "don't", "do not",
    "doesn't", "does not", "didn't", "did not", "isn't", "is not", "aren't",
    "are not", "wasn't", "was not", "weren't", "were not", "won't", "will not",
    "wouldn't", "would not", "shouldn't", "should not", "couldn't", "could not",
    "lack", "lacks", "lacking", "absence", "absent", "fails", "failed",
    "unable", "impossible", "insignificant", "independent of", "regardless of",
    "hardly", "barely", "rarely", "seldom", "few", "little",
]
NEGATIONS_ZH = [
    "不", "无", "非", "未", "没有", "没", "并非", "否", "别", "勿", "免",
    "缺", "缺乏", "缺失", "欠", "鲜", "难以", "无法", "不能", "不可能",
    "几乎不", "绝不", "毫不", "不受", "无关", "无关的", "独立于",
]
QUALIFIERS_EN = [
    "only", "just", "merely", "solely", "exclusively", "all", "every", "each",
    "any", "some", "most", "many", "much", "several", "few", "at least",
    "at most", "approximately", "about", "roughly", "around", "nearly",
    "exactly", "precisely", "always", "often", "sometimes", "usually",
    "typically", "may", "might", "can", "could", "must", "shall", "should",
    "necessarily", "possibly", "potentially", "likely", "unlikely",
    "primarily", "mainly", "mostly", "especially", "particularly",
    "specifically", "in general", "in particular", "unless", "provided that",
    "only if", "if and only if", "rather than", "instead of", "except",
]
QUALIFIERS_ZH = [
    "仅", "只", "唯有", "唯", "只是", "仅仅", "仅仅", "唯独", "所有", "每个",
    "任何", "一些", "某些", "大多数", "多数", "大部分", "至少", "至多",
    "约", "大约", "大致", "将近", "几乎", "恰好", "精确", "总是", "常常",
    "有时", "通常", "一般", "可能", "也许", "或许", "可以", "必须", "应当",
    "应该", "必然", "未必", "很可能", "主要", "大多", "尤其", "特别",
    "具体而言", "一般来说", "除非", "只要", "当且仅当", "而非", "而不是",
    "除了", "除外",
]

# Formula / math detection
INLINE_MATH_RE = re.compile(r'\$[^$\n]{1,300}\$|\\\([^()\n]{1,300}\\\)')
DISPLAY_MATH_RE = re.compile(
    r'\$\$[^$]{1,2000}\$\$|\\\[[^\]]{1,2000}\\\]|'
    r'\\begin\{(equation\*?|align\*?|eqnarray\*?|gather\*?)\}.*?'
    r'\\end\{\1\}',
    re.S,
)
MATH_GLYPH_RE = re.compile(r'[=+\-±×÷∑∫√∝∞≈≠≤≥→⇒∂∇∆αβγδεζηθλμνξπρστφχψωΩΓΔΘΛΞΠΣΦΨ]')

# Number and unit regexes
NUMBER_RE = re.compile(
    r'(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\w])'
)
# A unit atom: a whitelisted unit symbol plus an optional exponent
# ("cm", "cm2", "cm^2", "cm-1"). Symbols are tried longest-first so that
# "kDa" wins over "Da" and "mM" wins over "M".
_UNIT_SYMBOLS = [
    '%', '‰', '°C', '℃', '°F', '°', 'K', 'Da', 'kDa', 'MDa',
    'M', 'mM', 'μM', 'µM', 'nM', 'pM', 'fM', 'mol', 'mmol', 'μmol', 'µmol',
    'g', 'mg', 'μg', 'µg', 'ng', 'pg', 'kg', 'L', 'l', 'mL', 'ml', 'μL',
    'µL', 'nL', 's', 'ms', 'μs', 'µs', 'min', 'h', 'hr', 'cm', 'mm', 'μm',
    'µm', 'nm', 'Å', 'Hz', 'kHz', 'MHz', 'GHz', 'THz', 'V', 'Vs', 'mV',
    'μV', 'µV', 'W', 'mW', 'kW', 'J', 'kJ', 'Pa', 'kPa', 'MPa', 'GPa',
    'bar', 'atm', 'torr', 'Ω', 'MΩ', 'eV', 'keV', 'meV',
]
_UNIT_SYMBOL = '(?:' + '|'.join(sorted(_UNIT_SYMBOLS, key=len, reverse=True)) + ')'
_UNIT_ATOM = r'(?:' + _UNIT_SYMBOL + r'(?:[²³¹⁰⁴⁵⁶⁷⁸⁹\-\^]?[-+]?\d*)?)'
UNIT_RE = re.compile(
    r'(?<=\d)[\s\u00A0\u202F]*' + _UNIT_ATOM +
    r'(?:[\s\u00A0\u202F]*(?:[/·⋅*])[\s\u00A0\u202F]*' + _UNIT_ATOM + r')*'
    r'(?![\w])'
)
CITATION_BRACKET_RE = re.compile(r'\[[^\[\]\n]{1,120}\]')
CITATION_AUTHORYEAR_RE = re.compile(
    r'\((?:[A-ZÀ-Ž][A-Za-zÀ-ž\'\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z\'\-]+)?'
    r'(?:\s+et\s+al\.?)?|'
    r'(?:[A-Z][A-Za-z\'\-]+\s+(?:and|&)\s+)?[A-Z][A-Za-z\'\-]+\s+et\s+al\.?'
    r')\s*,?\s*\d{4}[a-z]?(?:\s*[,;]\s*\d{4}[a-z]?)*\)'
)
REF_RE = re.compile(
    r'\b(?:Fig(?:ure)?s?\.?|Table(?:s)?\.?|Eq(?:uation)?s?\.?|Section(?:s)?\.?|'
    r'Chapter(?:s)?\.?)\s*(?:\(\s*)?\d+[A-Za-z]?(?:\s*[–\-—]\s*\d+[A-Za-z]?)?'
    r'(?:\s*\))?'
)

PAGE_MARKER_RE = re.compile(r'^\s*(?:\f|Page\s*\d+\s*of\s*\d+|[Pp]age\s*\d+)\s*$')
HEADING_RE = re.compile(
    r'^\s*(?:\d+(?:\.\d+){0,3}[.)]?\s+)?(?:'
    r'Abstract|摘要|Introduction|Introduction\s+to|Background|Related\s+Work|'
    r'Methods?|Materials?\s+and\s+Methods?|Experimental|Experiments?|'
    r'Results?|Results?\s+and\s+Discussion|Discussion|Conclusion(?:s)?|'
    r'Conclusions?\s+and\s+Outlook|Summary|Acknowledg(?:e)?ments?|'
    r'Funding|Author\s+Contributions|Data\s+Availability|Conflict(?:s)?\s+of\s+Interest|'
    r'References|Bibliography|Appendix|Supplementary|Supporting\s+Information|'
    r'引言|绪论|方法|实验|结果|讨论|结论|致谢|参考文献|附录|摘要'
    r')(?:\s*\d*\.?)?\s*:?\s*$',
    re.I,
)
CAPTION_RE = re.compile(
    r'^\s*(?:Fig(?:ure)?\.?|Table|Scheme|Chart)\s+\d+[A-Za-z]?[.:]\s+\S', re.I
)

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "with", "by",
    "to", "from", "as", "is", "are", "was", "were", "be", "been", "that",
    "this", "these", "those", "it", "its", "their", "our", "we", "they",
    "at", "which", "who", "using", "used", "between", "among", "via",
    "based", "study", "studies", "results", "result", "figure", "fig",
    "table", "et", "al", "e.g", "i.e", "etc", "also", "such",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def read_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"file not found: {path}")
    data = p.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "latin-1", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"cannot decode {path} as text")


def write_json(obj, path: str, indent: int = 2) -> None:
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8"
    )


def normalize_ws(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


def normalize_for_compare(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u00A0", " ").replace("\u202F", " ")
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def cjk_ratio(s: str) -> float:
    if not s:
        return 0.0
    cjk = sum(1 for ch in s if '\u4e00' <= ch <= '\u9fff')
    return cjk / len(s)


# ---------------------------------------------------------------------------
# PDF text extraction (optional third-party)
# ---------------------------------------------------------------------------

def extract_pdf_text(path: str) -> str:
    """Return (text, method). Prefers native text layer; OCR is caller's job."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    # 1) PyMuPDF
    try:
        import fitz  # type: ignore
        doc = fitz.open(str(p))
        pages = []
        for page in doc:
            pages.append(page.get_text("text"))
            pages.append("\f")  # page separator; segmenter understands \f
        doc.close()
        return "".join(pages), "pymupdf-textlayer"
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001 - report but continue
        sys.stderr.write(f"[warn] PyMuPDF failed: {e}\n")
    # 2) pypdf
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(str(p))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
            pages.append("\f")
        return "".join(pages), "pypdf-textlayer"
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[warn] pypdf failed: {e}\n")
    # 3) pdfminer
    try:
        from pdfminer.high_level import extract_text  # type: ignore
        return extract_text(str(p)), "pdfminer-textlayer"
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[warn] pdfminer failed: {e}\n")
    # 4) external pdftotext
    import shutil, subprocess, tempfile
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "out.txt")
            subprocess.run([pdftotext, "-layout", str(p), out], check=False)
            if os.path.exists(out):
                return Path(out).read_text(encoding="utf-8", errors="replace"), "pdftotext-layout"
    raise RuntimeError(
        "no PDF text layer tool available. Install one of: pymupdf, pypdf, "
        "pdfminer.six, or the poppler `pdftotext` binary; or OCR the PDF and "
        "save the recognized text to a .txt file, then pass that file instead."
    )


# ---------------------------------------------------------------------------
# Paragraph segmentation
# ---------------------------------------------------------------------------

def _looks_like_heading(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if HEADING_RE.match(s) or CAPTION_RE.match(s):
        return True
    # all-caps short line (common in PDF headings); require no digits/math
    words = s.split()
    if (
        1 <= len(words) <= 12
        and not SENTENCE_END.search(s)
        and s.upper() == s
        and any(ch.isalpha() for ch in s)
        and not any(ch.isdigit() for ch in s)
        and not MATH_GLYPH_RE.search(s)
    ):
        return True
    return False


def _looks_like_formula(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if DISPLAY_MATH_RE.search(s) or INLINE_MATH_RE.search(s):
        return True
    glyphs = MATH_GLYPH_RE.findall(s)
    digits = sum(ch.isdigit() for ch in s)
    return len(glyphs) >= 2 and (digits >= 2 or len(glyphs) >= 3)


def _starts_new_paragraph(prev: str, line: str) -> bool:
    """Heuristic: a new paragraph begins when the previous run ended with
    terminal punctuation and the current line starts with uppercase/digit."""
    p = prev.rstrip()
    if not p:
        return False
    if not SENTENCE_END.search(p):
        return False
    s = line.lstrip()
    if not s:
        return False
    return s[0].isupper() or s[0].isdigit() or s[0] in "\"'([“"


def _has_blank_line(text: str) -> bool:
    return bool(re.search(r'\n\s*\n', text))


def segment_paragraphs(text: str, ocr: bool = False, dense: bool = False):
    """Split text into paragraphs P0001..; page breaks never split a
    mid-sentence paragraph.

    Default rule: a blank line ends a paragraph; headings, captions and
    formula blocks always end the preceding paragraph; wrapped lines inside a
    paragraph are joined with a single space. If the text has NO blank lines
    (some extractors), fall back to a sentence-boundary heuristic (same as
    --dense). Returns a list of dicts.
    """
    lines = text.splitlines()
    use_sentence_fallback = dense or not _has_blank_line(text)
    paragraphs = []
    buf: list[str] = []
    page = 1
    start_line = 1

    def flush(end_line: int, kind: str = "body", page_no: int = page):
        nonlocal buf, start_line
        content = normalize_ws(" ".join(buf))
        if content:
            paragraphs.append({
                "id": f"P{len(paragraphs) + 1:04d}",
                "kind": kind,
                "text": content,
                "start_line": start_line,
                "end_line": end_line,
                "page": page_no,
                "confidence": "low" if ocr else "high",
            })
        buf = []
        start_line = end_line + 1

    def split_on_sentence_boundary(line: str, lineno: int):
        nonlocal buf, start_line
        if buf and _starts_new_paragraph(" ".join(buf), line):
            flush(lineno - 1)
            buf = [line.strip()]
            start_line = lineno
        else:
            buf.append(line.strip())

    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        # page break
        if PAGE_MARKER_RE.match(line) or line == "\f":
            # Paragraph that ended on this page -> flush; otherwise continue.
            if buf and SENTENCE_END.search(" ".join(buf)):
                flush(lineno - 1, "body", page)
            # else: paragraph continues across the page boundary
            page += 1
            continue
        if not line.strip():
            if buf:
                flush(lineno - 1)
            continue
        stripped = line.lstrip()
        if _looks_like_formula(stripped):
            if buf:
                flush(lineno - 1)
            paragraphs.append({
                "id": f"P{len(paragraphs) + 1:04d}",
                "kind": "formula",
                "text": stripped,
                "start_line": lineno,
                "end_line": lineno,
                "page": page,
                "confidence": "low" if ocr else "high",
            })
            start_line = lineno + 1
            continue
        if _looks_like_heading(stripped):
            if buf:
                flush(lineno - 1)
            buf = [stripped]
            start_line = lineno
            flush(lineno, "heading", page)
            continue
        if CAPTION_RE.match(stripped):
            if buf:
                flush(lineno - 1)
            buf = [stripped]
            start_line = lineno
            flush(lineno, "caption", page)
            continue
        # wrapped line vs new paragraph
        if use_sentence_fallback:
            split_on_sentence_boundary(line, lineno)
        else:
            buf.append(line.strip())
    if buf:
        flush(len(lines))
    return paragraphs


def paragraphs_to_json(paragraphs) -> str:
    return json.dumps(paragraphs, ensure_ascii=False, indent=2) + "\n"


def paragraphs_to_text(paragraphs) -> str:
    out = []
    for p in paragraphs:
        out.append(f"[{p['id']}] ({p['kind']}, p.{p['page']}) {p['text']}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Glossary
# ---------------------------------------------------------------------------

ACRONYM_DEF_RE = re.compile(
    r'\b([A-Z][A-Za-z0-9\-]{1,12})\s*\(([^()\n]{2,90})\)'
)
ACRONYM_IN_PARENS_RE = re.compile(r'\(([A-Z][A-Za-z0-9\-]{1,12})\)')

# measurement/notation tokens that are not real domain terms
UNIT_ACRONYMS = {
    "Vs", "vs", "min", "max", "Fig", "Figure", "Table", "Eq", "Ref", "Refs",
    "cm", "mm", "nm", "μm", "µm", "um", "Hz", "kHz", "MHz", "GHz", "Pa",
    "kPa", "MPa", "GPa", "eV", "keV", "MeV", "GeV", "Da", "kDa", "mol",
    "mM", "nM", "μM", "µm", "mL", "μL", "s", "h", "S1", "S2", "S3",
}


def _plausible_definition(d: str) -> bool:
    d = d.strip()
    if len(d) < 2 or len(d) > 90:
        return False
    if re.search(r'\d{4}', d) or "et al" in d:
        return False
    if re.search(r'[=+\-±×÷∑∫]', d):
        return False
    if not any(ch.islower() for ch in d):
        return False
    return 1 <= len(d.split()) <= 10


def _plausible_acronym(a: str) -> bool:
    if not (2 <= len(a) <= 12):
        return False
    if a in UNIT_ACRONYMS:
        return False
    if not any(ch.isalpha() for ch in a):
        return False
    return True


def extract_term_candidates(text: str, max_terms: int = 200):
    """Heuristic term mining: acronym-definition pairs (both orders), bare
    acronyms, chemical formulas, capitalized multiword phrases, and frequent
    content n-grams. Output is a draft for human/agent curation, not a final
    glossary."""
    terms = OrderedDict()

    def add(term, context):
        t = term.strip()
        if len(t) < 2 or len(t) > 60 or t.lower() in STOPWORDS:
            return
        if t not in terms:
            terms[t] = {"term": t, "context": context[:160]}

    # acronym-first: "TMD (transition metal dichalcogenide)"
    for m in ACRONYM_DEF_RE.finditer(text):
        acro, definition = m.group(1), m.group(2).strip()
        if _plausible_acronym(acro) and _plausible_definition(definition):
            add(acro, f"{acro} ({definition})")
    # definition-first: "molybdenum disulfide (MoS2)"
    for m in ACRONYM_IN_PARENS_RE.finditer(text):
        acro = m.group(1)
        if not _plausible_acronym(acro):
            continue
        prefix = text[:m.start()]
        prev_words = re.findall(r"[A-Za-z][A-Za-z\-]*", prefix)[-5:]
        heading_stop = {"abstract", "introduction", "methods", "method", "results",
                        "discussion", "conclusion", "conclusions", "summary",
                        "references", "acknowledgements", "acknowledgments",
                        "background", "experimental"}
        def_words = [w for w in prev_words
                     if w.lower() not in STOPWORDS and w.lower() not in heading_stop
                     and not w.isdigit()]
        if len(def_words) >= 1:
            definition = " ".join(def_words[-4:])
            if _plausible_definition(definition):
                add(acro, f"{definition} ({acro})")
    # bare acronyms and chemical formulas, freq >= 2
    for acro, n in Counter(re.findall(r'\b[A-Z]{2,8}\b', text)).items():
        if n >= 2 and acro not in UNIT_ACRONYMS:
            add(acro, f"repeated acronym, freq={n}")
    for formula, n in Counter(
        re.findall(r'\b[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*){1,7}\b', text)
    ).items():
        if n >= 2 and re.search(r'\d', formula) and formula not in UNIT_ACRONYMS:
            add(formula, f"chemical formula, freq={n}")
    # capitalized multiword phrases (same line only)
    for m in re.finditer(r'\b(?:[A-Z][a-z]{2,}[ \t]+){1,3}[A-Z][a-z]{2,}\b', text):
        add(m.group(0), m.group(0))
    # frequent content n-grams (1-3 words, lowercase, alpha)
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower()) if w not in STOPWORDS]
    # single frequent domain words
    for word, cnt in Counter(words).items():
        if cnt >= 4 and len(word) >= 4:
            add(word, f"frequent word, freq={cnt}")
    for n in (3, 2):
        ng = Counter(" ".join(words[i:i + n]) for i in range(len(words) - n + 1))
        for phrase, cnt in ng.items():
            if cnt >= 2:
                add(phrase, f"frequent {n}-gram, freq={cnt}")
    items = list(terms.values())[:max_terms]
    return items


def glossary_to_md(entries, source_language="auto", target_language="zh", domain="") -> str:
    lines = [
        "# Term glossary",
        "",
        "<!-- metadata -->",
        f"- source_language: {source_language}",
        f"- target_language: {target_language}",
        f"- domain: {domain or '(fill in: e.g. materials science)'}",
        "",
        "## Terms",
        "",
        "| term | translation | variants | context | first_location | status |",
        "|---|---|---|---|---|---|",
    ]
    for e in entries:
        term = (e.get("term") or "").replace("|", "\\|")
        tr = (e.get("translation") or "").replace("|", "\\|")
        var = (e.get("variants") or "").replace("|", "\\|")
        ctx = (e.get("context") or "").replace("|", "\\|")
        loc = (e.get("first_location") or "").replace("|", "\\|")
        status = e.get("status") or "pending"
        lines.append(f"| {term} | {tr} | {var} | {ctx} | {loc} | {status} |")
    lines += [
        "",
        "## Rules",
        "- status: locked = enforce this translation everywhere (title/abstract/body/captions/conclusion);",
        "  pending = candidate, not yet used; uncertain = translation uncertain, must be flagged in output.",
        "- term = exact source surface form (case-sensitive).",
        "- variants = other source surface forms mapping to the SAME translation (comma separated).",
        "- translation = the ONLY allowed translation when locked; use it verbatim.",
        "- To change a locked term's translation, edit this row first, then re-run QA.",
    ]
    return "\n".join(lines) + "\n"


def _split_table_cells(line: str):
    """Split a markdown table row on unescaped pipes, dropping outer empties."""
    cells, cur, escaped = [], [], False
    for ch in line:
        if escaped:
            cur.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == "|":
            cells.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    cells.append("".join(cur))
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [c.strip().replace("\\|", "|") for c in cells]


def parse_glossary_md(text: str):
    """Parse the glossary markdown (see templates/term_glossary.md)."""
    entries = []
    meta = {"source_language": "auto", "target_language": "zh", "domain": ""}
    in_table = False
    header = None
    for line in text.splitlines():
        s = line.strip()
        if not in_table and s.startswith("- "):
            kv = s[2:].split(":", 1)
            if len(kv) == 2 and kv[0].strip() in meta:
                meta[kv[0].strip()] = kv[1].strip()
            continue
        if "|" in s:
            cells = _split_table_cells(s)
            if not in_table:
                low = [c.lower() for c in cells]
                if any("term" in c and "translation" in c for c in low) or (
                    "term" in low and "translation" in low
                ):
                    in_table = True
                    header = low
                    continue
                # allow headerless single separator row `|---|---|`
                if all(re.fullmatch(r':?-{1,}:?', c) for c in cells):
                    in_table = True
                    header = ["term", "translation", "variants", "context", "first_location", "status"]
                    continue
            else:
                if all(re.fullmatch(r':?-{1,}:?', c) for c in cells):
                    continue
                if len(cells) < 2 or not cells[0]:
                    continue
                row = dict(zip(header, cells))
                if row.get("term"):
                    entries.append({
                        "term": row.get("term", ""),
                        "translation": row.get("translation", ""),
                        "variants": [v.strip() for v in (row.get("variants") or "").split(",") if v.strip()],
                        "context": row.get("context", ""),
                        "first_location": row.get("first_location", ""),
                        "status": row.get("status", "pending"),
                        "domain": meta["domain"],
                    })
    return meta, entries


def load_glossary(path: str):
    text = read_text(path)
    return parse_glossary_md(text)


def locked_terms(entries):
    return [e for e in entries if (e.get("status") or "").lower() == "locked"]


def term_needles(entry):
    """All surface forms that should be recognized for this glossary entry."""
    forms = [entry.get("term", "")]
    forms += [v for v in (entry.get("variants") or []) if v]
    return [f for f in forms if f]


def _match_flags(needle: str) -> int:
    """Case-insensitive for plain lowercase words; case-sensitive for terms
    whose case carries meaning (acronyms, formulas, mixed case, digits)."""
    if any(ch.isupper() for ch in needle) or any(ch.isdigit() for ch in needle):
        return 0
    return re.IGNORECASE


def find_term_occurrences(text: str, entry):
    """Return match spans for a term and its variants, longest-first, no overlap."""
    spans = []
    for needle in term_needles(entry):
        if not needle:
            continue
        flags = _match_flags(needle)
        for m in re.finditer(re.escape(needle), text, flags):
            spans.append((m.start(), m.end(), needle))
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    kept = []
    last_end = -1
    for s, e, needle in spans:
        if s < last_end:
            continue
        kept.append({"start": s, "end": e, "surface": text[s:e], "needle": needle})
        last_end = e
    return kept


def check_term_drift(src_text: str, tgt_text: str, entries):
    """For each locked term present in src, require the canonical translation
    (or one of its allowed variants) in tgt at least once per occurrence."""
    issues = []
    src_norm = normalize_for_compare(src_text)
    tgt_norm = normalize_for_compare(tgt_text)
    for e in locked_terms(entries):
        occ = find_term_occurrences(src_norm, e)
        if not occ:
            continue
        canon = normalize_for_compare(e.get("translation") or "")
        variants = [normalize_for_compare(v) for v in (e.get("variants") or [])]
        if not canon:
            issues.append({
                "type": "term_missing_translation",
                "term": e.get("term"),
                "detail": "locked term has empty translation; cannot enforce",
            })
            continue
        hits = tgt_norm.count(canon)
        for v in variants:
            hits += tgt_norm.count(v)
        if hits < len(occ):
            issues.append({
                "type": "term_drift",
                "term": e.get("term"),
                "expected": e.get("translation"),
                "source_occurrences": len(occ),
                "target_hits": hits,
                "detail": "locked term occurs in source but canonical translation missing/insufficient in target",
            })
        # term left untranslated (raw English surface survives in target).
        # Skip when the canonical translation intentionally equals the source
        # surface (chemical formulas, proper nouns, gene/protein names).
        raw = normalize_for_compare(e.get("term") or "")
        if raw and canon and raw != canon and raw in tgt_norm:
            issues.append({
                "type": "term_untranslated",
                "term": e.get("term"),
                "detail": f"source surface '{e.get('term')}' appears untranslated in target",
            })
    return issues


# ---------------------------------------------------------------------------
# Protected tokens
# ---------------------------------------------------------------------------

def extract_protected_tokens(text: str):
    """Return ordered, non-overlapping tokens: number, unit, citation, ref,
    inline formula. Display formula blocks are handled by the segmenter."""
    candidates = []

    def add(kind, m, surface=None):
        if m is None:
            return
        candidates.append((m.start(), m.end(), kind, surface if surface is not None else m.group(0)))

    for m in INLINE_MATH_RE.finditer(text):
        add("formula", m)
    for m in CITATION_BRACKET_RE.finditer(text):
        add("citation", m)
    for m in CITATION_AUTHORYEAR_RE.finditer(text):
        add("citation", m)
    for m in REF_RE.finditer(text):
        add("ref", m)
    for m in UNIT_RE.finditer(text):
        add("unit", m)
    for m in NUMBER_RE.finditer(text):
        add("number", m)

    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0]), c[2]))
    tokens = []
    last_end = -1
    for start, end, kind, surface in candidates:
        if start < last_end:
            continue
        tokens.append({
            "id": f"{kind.upper()}_{len(tokens) + 1:04d}",
            "kind": kind,
            "text": text[start:end],
            "start": start,
            "end": end,
        })
        last_end = end
    return tokens


def mask_protected(text: str, tokens):
    """Replace token spans with placeholders like ⟨NUM_0001⟩. Longest spans are
    already ordered; apply from the end so offsets stay valid."""
    out = text
    for t in sorted(tokens, key=lambda x: -x["start"]):
        out = out[:t["start"]] + f"⟨{t['id']}⟩" + out[t["end"]:]
    return out


def restore_protected(masked: str, tokens):
    out = masked
    for t in tokens:
        out = out.replace(f"⟨{t['id']}⟩", t["text"])
    return out


def check_protected(src_text: str, tgt_text: str, tokens):
    """Flag protected tokens absent from the target (whitespace-normalized).

    kind=ref (Fig. 1, Table 2, Equation (2), Section 3.1) only requires the
    numeric identifier(s) to survive, since "Fig." -> "图" localization is
    legitimate; every other kind must survive verbatim."""
    issues = []
    tgt_norm = normalize_for_compare(tgt_text)
    for t in tokens:
        if t["kind"] == "ref":
            digits = re.findall(r'\d+[A-Za-z]?', t["text"])
            if digits and not any(d in tgt_norm for d in digits):
                issues.append({
                    "type": "token_missing",
                    "token_id": t["id"],
                    "kind": t["kind"],
                    "text": t["text"],
                    "detail": "figure/table/equation/section identifier not found in target",
                })
            continue
        needle = normalize_for_compare(t["text"])
        if needle and needle not in tgt_norm:
            issues.append({
                "type": "token_missing",
                "token_id": t["id"],
                "kind": t["kind"],
                "text": t["text"],
                "detail": "protected token not found verbatim in target",
            })
    return issues


def check_number_fidelity(src_text: str, tgt_text: str, src_tokens=None):
    """Compare the multiset of numbers in source vs target."""
    def numbers(s):
        out = []
        for m in NUMBER_RE.finditer(s):
            raw = m.group(0).replace(",", "")
            out.append(raw)
        return Counter(out)

    issues = []
    src_c = numbers(src_text)
    tgt_c = numbers(tgt_text)
    for num in sorted(set(src_c) | set(tgt_c)):
        if src_c[num] != tgt_c[num]:
            issues.append({
                "type": "number_drift",
                "number": num,
                "source_count": src_c[num],
                "target_count": tgt_c[num],
                "detail": "number count differs between source and target",
            })
    return issues


def count_lexical_markers(text: str, markers, boundary=True):
    """Count marker occurrences. For English, use word boundaries where the
    marker is alphabetic; for CJK, plain substring."""
    c = Counter()
    for mk in markers:
        if re.fullmatch(r'[A-Za-z\'\s]+', mk):
            pat = r'(?<![A-Za-z])' + re.escape(mk) + r'(?![A-Za-z])'
        else:
            pat = re.escape(mk)
        c[mk] = len(re.findall(pat, text, flags=re.I))
    return c


def check_negation_qualifier(src_text: str, tgt_text: str):
    """Flag paragraphs whose source carries a negation/qualifier but whose
    target shows none of that class. Count-based flag, not a verdict; a human
    or follow-up pass must confirm whether the marker was truly dropped."""
    issues = []
    src_neg = sum(count_lexical_markers(src_text, NEGATIONS_EN).values())
    tgt_neg = sum(count_lexical_markers(tgt_text, NEGATIONS_ZH).values())
    tgt_neg_en = sum(count_lexical_markers(tgt_text, NEGATIONS_EN).values()) if cjk_ratio(tgt_text) < 0.5 else 0
    if src_neg > 0 and (tgt_neg + tgt_neg_en) == 0:
        issues.append({
            "type": "negation_possibly_dropped",
            "detail": f"source has {src_neg} negation marker(s) but target has none",
        })
    src_qc = sum(count_lexical_markers(src_text, QUALIFIERS_EN).values())
    if src_qc > 0:
        tgt_q = sum(count_lexical_markers(tgt_text, QUALIFIERS_ZH).values())
        tgt_q_en = sum(count_lexical_markers(tgt_text, QUALIFIERS_EN).values()) if cjk_ratio(tgt_text) < 0.5 else 0
        if (tgt_q + tgt_q_en) == 0:
            issues.append({
                "type": "qualifier_possibly_dropped",
                "detail": f"source has {src_qc} qualifier marker(s) but target has none",
            })
    return issues


# ---------------------------------------------------------------------------
# Target paragraph parsing / alignment
# ---------------------------------------------------------------------------

TARGET_ID_RE = re.compile(r'^\s*\[(P\d{4,})\]', re.I)


def parse_target_paragraphs(text: str):
    """Parse target text marked with [P####] paragraph markers, or return a
    single free-text block if no markers are present."""
    lines = text.splitlines()
    paras = []
    cur_id = None
    buf = []
    order = []
    for line in lines:
        m = TARGET_ID_RE.match(line)
        if m:
            if cur_id is not None:
                paras.append({"id": cur_id, "text": normalize_ws(" ".join(buf))})
                buf = []
            cur_id = m.group(1).upper()
            order.append(cur_id)
            # strip the marker for the text content
            rest = line[m.end():].strip()
            if rest:
                buf.append(rest)
        elif cur_id is not None:
            buf.append(line.strip())
        else:
            buf.append(line.strip())
    if cur_id is not None:
        paras.append({"id": cur_id, "text": normalize_ws(" ".join(buf))})
    elif buf:
        paras.append({"id": None, "text": normalize_ws(" ".join(buf))})
    return paras, order


def build_alignment(source_paragraphs, target_paragraphs):
    """1:1 source<->target pairing by id; report missing/extra/reordered."""
    src_by_id = {p["id"]: p for p in source_paragraphs}
    tgt_by_id = {p["id"]: p for p in target_paragraphs if p.get("id")}
    pairs = []
    missing = []
    extra = []
    order_issues = []
    src_ids = [p["id"] for p in source_paragraphs]
    tgt_ids = [p["id"] for p in target_paragraphs if p.get("id")]
    for sid in src_ids:
        if sid in tgt_by_id:
            pairs.append({"source_id": sid, "target_id": sid,
                          "source_text": src_by_id[sid]["text"],
                          "target_text": tgt_by_id[sid]["text"],
                          "source_kind": src_by_id[sid]["kind"]})
        else:
            missing.append(sid)
    for tid in tgt_ids:
        if tid not in src_by_id:
            extra.append(tid)
    # order: target ids should appear in source order
    present = [tid for tid in tgt_ids if tid in src_by_id]
    if present != [sid for sid in src_ids if sid in present]:
        order_issues.append({"detail": "target paragraph order differs from source order"})
    # duplicate ids
    dup_src = [i for i, c in Counter(src_ids).items() if c > 1]
    dup_tgt = [i for i, c in Counter(tgt_ids).items() if c > 1]
    return {
        "pairs": pairs,
        "missing_target": missing,
        "extra_target": extra,
        "order_issues": order_issues,
        "duplicate_source_ids": dup_src,
        "duplicate_target_ids": dup_tgt,
    }


def alignment_to_md(alignment, glossary_entries=None, source_meta=None):
    lines = ["# Bilingual alignment", ""]
    if source_meta:
        lines.append(f"- source: {source_meta}")
        lines.append("")
    for p in alignment["pairs"]:
        lines.append(f"## [{p['source_id']}] ({p.get('source_kind', 'body')})")
        lines.append("")
        lines.append("**Source**")
        lines.append("")
        lines.append(p["source_text"])
        lines.append("")
        lines.append("**Translation**")
        lines.append("")
        lines.append(p["target_text"])
        lines.append("")
        if p.get("rationale"):
            lines.append(f"**Rationale**: {p['rationale']}")
            lines.append("")
        if p.get("uncertain"):
            lines.append(f"**Uncertain**: {p['uncertain']}")
            lines.append("")
    if alignment.get("missing_target"):
        lines.append("## Missing in target")
        lines.append("")
        lines.append(", ".join(alignment["missing_target"]))
        lines.append("")
    if alignment.get("extra_target"):
        lines.append("## Extra in target")
        lines.append("")
        lines.append(", ".join(alignment["extra_target"]))
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# QA
# ---------------------------------------------------------------------------

def run_qa(source_paragraphs, target_paragraphs, glossary_entries):
    """Aggregate all checks into one report. Protected tokens are re-extracted
    per source paragraph so attribution to the correct paragraph is exact."""
    report = {
        "source_paragraph_count": len(source_paragraphs),
        "target_paragraph_count": len(target_paragraphs),
        "checks": [],
        "issues": [],
    }
    locked = locked_terms(glossary_entries)

    align = build_alignment(source_paragraphs, target_paragraphs)
    report["alignment"] = {
        "missing_target": align["missing_target"],
        "extra_target": align["extra_target"],
        "order_issues": align["order_issues"],
        "duplicate_source_ids": align["duplicate_source_ids"],
        "duplicate_target_ids": align["duplicate_target_ids"],
    }
    if align["missing_target"] or align["extra_target"] or align["order_issues"] or align["duplicate_target_ids"]:
        report["issues"].append({
            "type": "paragraph_inventory",
            "detail": "see alignment block: missing/extra/reordered/duplicated paragraph ids",
        })

    # per-pair checks
    for p in align["pairs"]:
        src, tgt = p["source_text"], p["target_text"]
        local = []
        local += check_term_drift(src, tgt, locked)
        local += check_protected(src, tgt, extract_protected_tokens(src))
        local += check_number_fidelity(src, tgt)
        local += check_negation_qualifier(src, tgt)
        for issue in local:
            issue.setdefault("paragraph_id", p["source_id"])
            report["issues"].append(issue)
        report["checks"].append({
            "paragraph_id": p["source_id"],
            "ok": len(local) == 0,
            "issue_count": len(local),
        })

    # whole-document term consistency summary (distinct translations seen)
    if locked:
        full_tgt = "\n".join(p["target_text"] for p in align["pairs"])
        for e in locked:
            canon = normalize_for_compare(e.get("translation") or "")
            hits = full_tgt.count(canon) if canon else 0
            report.setdefault("term_consistency", []).append({
                "term": e.get("term"),
                "canonical_translation": e.get("translation"),
                "target_occurrences_of_canonical": hits,
            })

    n_err = sum(1 for i in report["issues"] if i["type"] in {
        "term_drift", "term_untranslated", "term_missing_translation",
        "paragraph_inventory", "token_missing", "number_drift",
    })
    n_warn = len(report["issues"]) - n_err
    report["summary"] = {
        "error_count": n_err,
        "warning_count": n_warn,
        "passed": n_err == 0,
    }
    return report


def qa_report_to_text(report):
    lines = ["QA report", "=========", ""]
    lines.append(f"paragraphs: source={report['source_paragraph_count']} "
                 f"target={report['target_paragraph_count']}")
    lines.append(f"errors={report['summary']['error_count']} "
                 f"warnings={report['summary']['warning_count']}")
    lines.append("")
    if report.get("alignment"):
        a = report["alignment"]
        lines.append("paragraph inventory:")
        lines.append(f"  missing_target={a['missing_target']}")
        lines.append(f"  extra_target={a['extra_target']}")
        lines.append(f"  order_issues={len(a['order_issues'])}")
        lines.append("")
    for i in report["issues"]:
        pid = i.get("paragraph_id", "-")
        lines.append(f"[{i['type']}] {pid}: {i.get('detail', '')}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_segment(args):
    text = read_text(args.source)
    paras = segment_paragraphs(text, ocr=args.ocr, dense=args.dense)
    Path(args.out).write_text(paragraphs_to_json(paras), encoding="utf-8")
    if args.text_out:
        Path(args.text_out).write_text(paragraphs_to_text(paras), encoding="utf-8")
    print(json.dumps({
        "paragraph_count": len(paras),
        "kinds": dict(Counter(p["kind"] for p in paras)),
        "out": args.out,
    }, ensure_ascii=False, indent=2))


def cmd_candidates(args):
    text = read_text(args.source)
    items = extract_term_candidates(text, max_terms=args.max_terms)
    md = glossary_to_md(items, source_language=args.source_language,
                        target_language=args.target_language, domain=args.domain)
    Path(args.out).write_text(md, encoding="utf-8")
    print(json.dumps({"candidate_count": len(items), "out": args.out},
                     ensure_ascii=False, indent=2))


def cmd_protect(args):
    text = read_text(args.source)
    tokens = extract_protected_tokens(text)
    payload = {"tokens": tokens, "source_file": args.source,
               "ocr": args.ocr}
    if args.mask_out:
        payload["masked_text"] = mask_protected(text, tokens)
        Path(args.mask_out).write_text(payload["masked_text"], encoding="utf-8")
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    kinds = Counter(t["kind"] for t in tokens)
    print(json.dumps({"token_count": len(tokens), "kinds": dict(kinds),
                      "out": args.out}, ensure_ascii=False, indent=2))


def cmd_restore(args):
    masked = read_text(args.masked)
    payload = json.loads(read_text(args.tokens))
    restored = restore_protected(masked, payload["tokens"])
    Path(args.out).write_text(restored, encoding="utf-8")
    print(json.dumps({"out": args.out}, ensure_ascii=False, indent=2))


def cmd_align(args):
    src = json.loads(read_text(args.source))
    tgt_paras, order = parse_target_paragraphs(read_text(args.target))
    align = build_alignment(src, tgt_paras)
    align["target_order"] = order
    if args.out:
        write_json(align, args.out)
    if args.md_out:
        Path(args.md_out).write_text(alignment_to_md(align), encoding="utf-8")
    print(json.dumps({
        "pairs": len(align["pairs"]),
        "missing_target": align["missing_target"],
        "extra_target": align["extra_target"],
        "order_issues": len(align["order_issues"]),
    }, ensure_ascii=False, indent=2))


def cmd_qa(args):
    src = json.loads(read_text(args.source))
    tgt_paras, _order = parse_target_paragraphs(read_text(args.target))
    meta, entries = load_glossary(args.glossary)
    report = run_qa(src, tgt_paras, entries)
    if args.out:
        write_json(report, args.out)
    print(qa_report_to_text(report))
    if report["summary"]["error_count"] > 0:
        sys.exit(2)


def cmd_extract(args):
    """Extract a text layer from a PDF into a .txt file."""
    text, method = extract_pdf_text(args.pdf)
    Path(args.out).write_text(text, encoding="utf-8")
    print(json.dumps({"method": method, "chars": len(text), "out": args.out},
                     ensure_ascii=False, indent=2))


def build_parser():
    p = argparse.ArgumentParser(
        prog="translate.py",
        description="literature-translator integrity tooling (segment / candidates / "
                    "protect / mask / restore / align / qa / extract)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("segment", help="split source text into numbered paragraphs")
    s.add_argument("--source", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--text-out", default=None)
    s.add_argument("--ocr", action="store_true", help="text came from OCR (low confidence)")
    s.add_argument("--dense", action="store_true",
                   help="force sentence-boundary fallback even when blank lines exist")
    s.set_defaults(func=cmd_segment)

    c = sub.add_parser("candidates", help="mine candidate glossary terms")
    c.add_argument("--source", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--max-terms", type=int, default=200)
    c.add_argument("--source-language", default="auto")
    c.add_argument("--target-language", default="zh")
    c.add_argument("--domain", default="")
    c.set_defaults(func=cmd_candidates)

    pr = sub.add_parser("protect", help="extract numbers/units/citations/refs/formulas")
    pr.add_argument("--source", required=True)
    pr.add_argument("--out", required=True)
    pr.add_argument("--mask-out", default=None, help="also write masked text")
    pr.add_argument("--ocr", action="store_true")
    pr.set_defaults(func=cmd_protect)

    rs = sub.add_parser("restore", help="restore placeholders from a masked translation")
    rs.add_argument("--masked", required=True)
    rs.add_argument("--tokens", required=True)
    rs.add_argument("--out", required=True)
    rs.set_defaults(func=cmd_restore)

    a = sub.add_parser("align", help="build source<->target paragraph pairs")
    a.add_argument("--source", required=True, help="source paragraphs JSON from segment")
    a.add_argument("--target", required=True, help="target text with [P####] markers")
    a.add_argument("--out", default=None)
    a.add_argument("--md-out", default=None, help="write bilingual markdown")
    a.set_defaults(func=cmd_align)

    q = sub.add_parser("qa", help="run the full QA battery")
    q.add_argument("--source", required=True, help="source paragraphs JSON from segment")
    q.add_argument("--target", required=True, help="target text with [P####] markers")
    q.add_argument("--glossary", required=True, help="locked glossary markdown")
    q.add_argument("--out", default=None)
    q.set_defaults(func=cmd_qa)

    e = sub.add_parser("extract", help="extract PDF text layer to .txt")
    e.add_argument("--pdf", required=True)
    e.add_argument("--out", required=True)
    e.set_defaults(func=cmd_extract)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(3)
    except RuntimeError as e:
        print(f"ERROR (needs intervention): {e}", file=sys.stderr)
        sys.exit(3)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"ERROR: invalid input: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
