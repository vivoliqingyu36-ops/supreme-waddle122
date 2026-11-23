#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_parse.py — 文献 PDF 解析后处理助手（纯标准库，无第三方依赖）。

用途
----
把「带坐标的文字片段(spans)」整理成可复核的结构化结果：
  1) page-block text assembly    —— 同一行的 span 并成行、相近行并成块，保留逐行原文；
  2) multi-column reorder        —— 用纵向投影+重复沟槽判定列带，按「列优先 + 通栏锚点」排阅读顺序；
  3) table cell extraction       —— 由 span 的 x/y 聚类重建网格，推断 colspan/rowspan 与单元格归属；
  4) evidence IDs                —— 每个块/单元格生成稳定 ID，附页码 + bbox + 来源 span 列表。

输入契约（canonical span 格式，见 schema/span_schema.json）：
  {
    "source": "paper.pdf",
    "unit": "pt", "origin": "top-left",
    "pages": [
      {"page": 1, "width": 612.0, "height": 792.0, "rotate": 0,
       "spans": [
         {"text": "Title", "x0": 72.0, "y0": 90.0, "x1": 200.0, "y1": 101.0,
          "font": "Times", "size": 14.0, "style": "bold"},
         ...
       ]}
    ]
  }
  x0/y0/x1/y1 为左上原点(point)；若只有 x/y/w/h 会被 normalize() 归一化为 x0/y0/x1/y1。

运行（CLI）：
  python3 pdf_parse.py assemble spans.json --out blocks.json
  python3 pdf_parse.py table spans.json --page 3 --region 60,180,500,600 --out table.json
  python3 pdf_parse.py demo --out demo_spans.json      # 生成双栏+表格的合成样例
  python3 pdf_parse.py self-test                       # 跑内置断言，验证核心函数
  python3 pdf_parse.py assemble text.txt --from-text   # 无坐标纯文本退化路径（每页单块）

限制（诚实声明）：
  - 本脚本不直接解析 PDF 二进制，也不做 OCR；它消费 pdf-text-tool / ocr-tool 输出的 span 列表。
  - 版面判定是启发式：极端错位、旋转页、任意重叠文本框可能出错，出错处会写入 uncertainty。
  - 合并单元格的推断（rowspan/colspan）依据坐标外延，若 PDF 文字框与视觉边框不一致会有偏差，
    此时 cell 带 uncertain 标记，需要人工/渲染图复核。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

EPS = 1e-6

# 公式/特殊字符保留用的字符集（用于识别公式行与希腊字母保真标注）。
GREEK_MAP = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "ζ": "zeta", "η": "eta", "θ": "theta", "ι": "iota", "κ": "kappa",
    "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "ο": "omicron",
    "π": "pi", "ρ": "rho", "σ": "sigma", "τ": "tau", "υ": "upsilon",
    "φ": "phi", "χ": "chi", "ψ": "psi", "ω": "omega",
    "Γ": "Gamma", "Δ": "Delta", "Θ": "Theta", "Λ": "Lambda", "Ξ": "Xi",
    "Π": "Pi", "Σ": "Sigma", "Φ": "Phi", "Ψ": "Psi", "Ω": "Omega",
    "µ": "mu", "×": "times", "·": "cdot", "±": "pm", "∓": "mp",
    "≤": "leq", "≥": "geq", "≠": "neq", "≈": "approx", "≡": "equiv",
    "∞": "infty", "∂": "partial", "∇": "nabla", "∫": "int", "∑": "sum",
    "∏": "prod", "√": "sqrt", "→": "to", "←": "leftarrow", "↔": "leftrightarrow",
    "∈": "in", "∉": "notin", "⊂": "subset", "⊆": "subseteq", "∪": "cup",
    "∩": "cap", "⊕": "oplus", "⊗": "otimes", "·": "cdot", "‾": "overline",
    "′": "prime", "″": "dprime", "…": "ldots", "⟨": "langle", "⟩": "rangle",
}
MATH_GLYPHS = set(GREEK_MAP.keys()) | set("^_0123456789") | set("=+-*/<>()[]{}|")
SUPERSCRIPT_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")

# 页眉页脚/页码判定用的正则。
PAGE_NUMBER_RE = re.compile(r"^\s*[ivxlcdmIVXLCDM0-9]{1,6}\s*$")
SECTION_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3}){0,3}\.?)\s+(\S.*)$")
CAPTION_RE = re.compile(r"^\s*(fig(?:ure)?|table|algorithm|scheme|listing|box)\s*\.?\s*\d+", re.I)
REFMARK_RE = re.compile(r"^(\[[0-9]{1,3}(?:[,\-\s]+\d{1,3})*\])")


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def normalize_span(sp: Dict[str, Any]) -> Dict[str, Any]:
    """把 x/y/w/h 形式归一化为 x0/y0/x1/y1。不修改原 dict。"""
    s = dict(sp)
    if "x0" not in s:
        s["x0"] = float(s.get("x", 0.0))
        s["y0"] = float(s.get("y", 0.0))
        s["x1"] = s["x0"] + float(s.get("w", 0.0))
        s["y1"] = s["y0"] + float(s.get("h", 0.0))
    for k in ("x0", "y0", "x1", "y1"):
        s[k] = float(s[k])
    if s["x1"] < s["x0"]:
        s["x0"], s["x1"] = s["x1"], s["x0"]
    if s["y1"] < s["y0"]:
        s["y0"], s["y1"] = s["y1"], s["y0"]
    return s


def load_pages(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """读入 span 文档，返回带 page 键的扁平 span 列表 + 页面信息。"""
    pages: List[Dict[str, Any]] = []
    for p in raw.get("pages", []):
        pg = {"page": int(p.get("page", len(pages) + 1)),
              "width": float(p.get("width", 0.0)),
              "height": float(p.get("height", 0.0)),
              "rotate": int(p.get("rotate", 0))}
        spans = []
        for i, sp in enumerate(p.get("spans", [])):
            if not sp.get("text") or not str(sp["text"]).strip():
                continue
            s = normalize_span(sp)
            s["text"] = str(s.get("text", ""))
            s["page"] = pg["page"]
            s["span_id"] = "p%d-s%04d" % (pg["page"], i)
            spans.append(s)
        pg["spans"] = spans
        pages.append(pg)
    return pages


def merge_intervals(intervals: Iterable[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """合并重叠/相接的 [x0,x1] 区间（闭区间容差 EPS）。"""
    it = sorted((float(a), float(b)) for a, b in intervals if b >= a)
    out: List[Tuple[float, float]] = []
    for a, b in it:
        if out and a <= out[-1][1] + EPS:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def cluster_1d(values: Iterable[float], tol: float) -> List[float]:
    """一维聚合：返回各簇的代表值（簇内均值）。用于把接近的 x0/y0 归并。"""
    vals = sorted(float(v) for v in values)
    clusters: List[List[float]] = []
    for v in vals:
        if clusters and v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [sum(c) / len(c) for c in clusters]


def median(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


# --------------------------------------------------------------------------
# (2) 多栏检测：纵向投影 + 逐条带内部沟槽投票
# --------------------------------------------------------------------------
def detect_column_bands(spans: List[Dict[str, Any]],
                        page_width: float,
                        page_height: float,
                        min_gap: float = 12.0,
                        gap_ratio: float = 0.025,
                        vote_ratio: float = 0.5) -> List[Tuple[float, float]]:
    """返回列带区间 [(left, right), ...]，按 x 升序。

    思路：把页面高度切成若干水平条带，每个条带内合并 span 的 x 区间，
    找出条带内部连续文本之间的「空洞(gap)」；只有跨多数条带稳定出现的
    空洞才被认定为栏间沟槽。好处：
      * 缩进/首行空格只出现在少数条带，被 vote_ratio 过滤；
      * 通栏标题/表格只在少数条带填满沟槽，不会破坏判定；
      * 左右页边距（条带首尾）不参与，因为只统计文本区间之间的内部空洞。
    """
    if page_width <= 0:
        page_width = max((s["x1"] for s in spans), default=1.0)
    if page_height <= 0:
        page_height = max((s["y1"] for s in spans), default=1.0)
    if not spans or page_width <= 0 or page_height <= 0:
        return [(0.0, page_width or 612.0)]

    slice_h = max(1.0, page_height / max(1, int(page_height // 24)))
    n_slices = int(math.ceil(page_height / slice_h))
    slices: List[List[Tuple[float, float]]] = [[] for _ in range(n_slices)]
    for s in spans:
        i0 = clamp(int(s["y0"] // slice_h), 0, n_slices - 1)
        i1 = clamp(int(s["y1"] // slice_h), 0, n_slices - 1)
        for i in range(i0, i1 + 1):
            slices[i].append((s["x0"], s["x1"]))

    gap_thresh = max(min_gap, gap_ratio * page_width)
    gap_votes: Dict[int, List[float]] = defaultdict(list)  # 量化中点 -> [中点们]
    nonempty = 0
    for intervals in slices:
        merged = merge_intervals(intervals)
        if not merged:
            continue
        nonempty += 1
        for (_, r0), (l1, _) in zip(merged, merged[1:]):
            w = l1 - r0
            if w >= gap_thresh:
                mid = (r0 + l1) / 2.0
                key = int(round(mid / 6.0))  # 6pt 量化再聚类
                gap_votes[key].append(mid)

    need = max(2, int(math.ceil(vote_ratio * max(1, nonempty))))
    boundaries: List[float] = []
    for _, mids in gap_votes.items():
        if len(mids) >= need:
            boundaries.append(sum(mids) / len(mids))
    boundaries.sort()

    if not boundaries:
        return [(0.0, page_width)]
    bands: List[Tuple[float, float]] = []
    prev = 0.0
    for b in boundaries:
        bands.append((prev, b))
        prev = b
    bands.append((prev, page_width))
    # 丢弃没有任何 span 中心的空带
    nonempty_bands = []
    for (a, b) in bands:
        if any(a <= (s["x0"] + s["x1"]) / 2.0 < b for s in spans):
            nonempty_bands.append((a, b))
    return nonempty_bands or [(0.0, page_width)]


def assign_band(span: Dict[str, Any], bands: List[Tuple[float, float]]) -> Tuple[int, bool]:
    """返回 (band_index, spanning)。

    spanning 判据：span 的 x 范围覆盖 ≥2 个列带的「中心」——只有真正横跨
    两栏的通栏元素（标题、通栏表格、大公式）才会被判定为 spanning，
    避免列内单元格因略越过栏分界线而被误判为通栏。
    """
    cx = (span["x0"] + span["x1"]) / 2.0
    centers = [(a + b) / 2.0 for (a, b) in bands]
    inside = [i for i, c in enumerate(centers) if span["x0"] <= c <= span["x1"]]
    # 归属：中心所在带；中心落在带外时取最近的带
    if inside:
        idx = min(inside, key=lambda i: abs(centers[i] - cx))
    else:
        idx = min(range(len(bands)), key=lambda i: abs(centers[i] - cx))
    spanning = len(inside) >= 2
    return idx, spanning


# --------------------------------------------------------------------------
# (1) 行/块组装 + 阅读顺序
# --------------------------------------------------------------------------
def cluster_into_lines(spans: List[Dict[str, Any]], y_tol: float = 3.0) -> List[List[Dict[str, Any]]]:
    """按 y0 聚合成视觉行，返回按 y0 升序的行列表（行内按 x0 升序）。"""
    ordered = sorted(spans, key=lambda s: (s["y0"], s["x0"]))
    lines: List[List[Dict[str, Any]]] = []
    for s in ordered:
        if lines and s["y0"] - lines[-1][-1]["y0"] <= y_tol:
            lines[-1].append(s)
        else:
            lines.append([s])
    for ln in lines:
        ln.sort(key=lambda s: (s["x0"], s["y0"]))
    return lines


def line_geom(line: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "x0": min(s["x0"] for s in line),
        "y0": min(s["y0"] for s in line),
        "x1": max(s["x1"] for s in line),
        "y1": max(s["y1"] for s in line),
        "text": " ".join(s["text"] for s in line),
        "size": max((s.get("size", 0.0) for s in line), default=0.0),
        "spans": line,
    }


def classify_line(line: List[Dict[str, Any]], page_h: float, body_size: float) -> str:
    """把视觉行分类为 caption/heading/formula/body/footnote 等角色（粗分类）。"""
    text = " ".join(s["text"] for s in line).strip()
    if not text:
        return "empty"
    size = max((s.get("size", 0.0) for s in line), default=0.0)
    y0 = min(s["y0"] for s in line)
    y1 = max(s["y1"] for s in line)
    if CAPTION_RE.match(text):
        return "caption"
    if page_h > 0 and y0 > page_h * 0.88 and len(text) < 200:
        # 底部 12% 的短行：仅当带脚注标记、或非表格数值行时才标脚注候选。
        # 表格数值行（多短数字 span）不能误判为脚注。
        if REFMARK_RE.match(text) or re.match(r"^\s*[*†‡§¶]\s+", text):
            return "footnote_candidate"
        if not _looks_numeric(text):
            return "footnote_candidate"
    if size >= body_size * 1.10 and body_size > 0 and len(text) < 200:
        return "heading"
    if SECTION_RE.match(text) and len(text) < 160:
        return "heading"
    if _is_formula_line(text):
        return "formula"
    return "body"


def _is_formula_line(text: str) -> bool:
    """公式行粗判：一行内出现 ≥2 个数学/希腊字形，或形如 (3) 的编号 + 符号。"""
    n = sum(1 for ch in text if ch in GREEK_MAP or ch in "∑∫∂∇√±×·≤≥≠≈∞∈⊂∪∩⊗⊕")
    if n >= 2:
        return True
    if re.match(r"^\s*\(?\d{1,3}\)\s*[=+\-*/<>∑∫∂√]", text):
        return True
    return False


def ordering_key(line: List[Dict[str, Any]], bands: List[Tuple[float, float]]) -> Tuple:
    """用于单栏页（bands 数量为 1）或通栏排序的统一 key。"""
    g = line_geom(line)
    return (round(g["y0"], 1), round(g["x0"], 1))


def cluster_lines_in_band(spans: List[Dict[str, Any]], y_tol: float) -> List[List[Dict[str, Any]]]:
    """在单个列带内按 y0 聚合视觉行（避免跨列合并）。"""
    ordered = sorted(spans, key=lambda s: (s["y0"], s["x0"]))
    lines: List[List[Dict[str, Any]]] = []
    for s in ordered:
        if lines and s["y0"] - lines[-1][-1]["y0"] <= y_tol:
            lines[-1].append(s)
        else:
            lines.append([s])
    for ln in lines:
        ln.sort(key=lambda s: (s["x0"], s["y0"]))
    return lines


def line_signature(line: List[Dict[str, Any]], x_tol: float = 4.0) -> Tuple[int, ...]:
    """把一行内 span 的 x0 量化成签名，用于识别跨多行对齐的表格列。"""
    xs = sorted(s["x0"] for s in line)
    return tuple(int(round(x / x_tol)) for x in xs)


def detect_table_candidates_from_lines(lines: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """表格候选：同一列带内多行具有相同 x0 签名（≥2 列、≥2 行）→ 候选矩形。

    只依赖坐标对齐，不依赖语义；结果是「候选」，需与渲染图/竖线复核。
    """
    groups: Dict[Tuple[int, ...], List[List[Dict[str, Any]]]] = defaultdict(list)
    for ln in lines:
        sig = line_signature(ln)
        if len(sig) >= 2:
            groups[sig].append(ln)
    candidates: List[Dict[str, Any]] = []
    for sig, lns in groups.items():
        if len(lns) < 2:
            continue
        x0 = min(min(s["x0"] for s in ln) for ln in lns)
        x1 = max(max(s["x1"] for s in ln) for ln in lns)
        y0 = min(min(s["y0"] for s in ln) for ln in lns)
        y1 = max(max(s["y1"] for s in ln) for ln in lns)
        candidates.append({"region": (x0, y0, x1, y1), "n_lines": len(lns),
                           "columns": len(sig),
                           "note": "heuristic_candidate_verify_with_render"})
    # 合并相邻/包含的候选矩形
    return _merge_regions(candidates)


def _merge_regions(cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(cands) <= 1:
        return cands
    regions = [c["region"] for c in cands]
    merged = []
    used = [False] * len(cands)
    for i in range(len(cands)):
        if used[i]:
            continue
        a = list(regions[i])
        for j in range(i + 1, len(cands)):
            if used[j]:
                continue
            b = regions[j]
            # 垂直重叠且水平重叠 → 合并
            if not (a[3] < b[1] - 2 or b[3] < a[1] - 2 or a[2] < b[0] - 2 or b[2] < a[0] - 2):
                a = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                used[j] = True
        merged.append({"region": tuple(a), "n_lines": cands[i]["n_lines"],
                       "columns": cands[i]["columns"],
                       "note": cands[i]["note"]})
    return merged


def assemble_page(page: Dict[str, Any],
                  y_tol: float = 3.0,
                  min_gap: float = 12.0,
                  para_gap_ratio: float = 1.5) -> Dict[str, Any]:
    """单页组装：列带检测 → 分带行聚类 → 通栏锚点分段 → 列优先阅读顺序 → 块合并。"""
    spans = page["spans"]
    out: Dict[str, Any] = {"page": page["page"], "blocks": [], "columns": [],
                           "warnings": [], "table_candidates": []}
    if not spans:
        out["warnings"].append("no_spans")
        return out

    page_w = page.get("width", 0.0)
    page_h = page.get("height", 0.0)
    if page_w <= 0:
        page_w = max(s["x1"] for s in spans)
    if page_h <= 0:
        page_h = max(s["y1"] for s in spans)

    bands = detect_column_bands(spans, page_w, page_h, min_gap=min_gap)
    out["columns"] = [{"index": i, "x0": a, "x1": b} for i, (a, b) in enumerate(bands)]

    # 把 span 分为「通栏(横跨≥2列带)」与「列内」两类。
    spanning_spans: List[Dict[str, Any]] = []
    col_spans: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for s in spans:
        idx, spanning = assign_band(s, bands)
        if spanning and len(bands) > 1:
            spanning_spans.append(s)
        else:
            col_spans[idx].append(s)

    # 每个列带内部独立聚合行；通栏 span 单独聚合行。
    line_objs: List[Dict[str, Any]] = []
    body_sizes = [s.get("size", 0.0) for s in spans if s.get("size", 0.0) > 0]
    body_size = median(body_sizes) if body_sizes else 0.0
    band_lines: List[List[Dict[str, Any]]] = []
    for idx in sorted(col_spans):
        for ln in cluster_lines_in_band(col_spans[idx], y_tol):
            band_lines.append(ln)
            g = line_geom(ln)
            line_objs.append({"line": ln, "geom": g, "band": idx, "spanning": False,
                              "role": "body"})
    for ln in cluster_lines_in_band(spanning_spans, y_tol):
        g = line_geom(ln)
        line_objs.append({"line": ln, "geom": g, "band": 0, "spanning": True,
                          "role": "body"})

    # 表格候选：在「列内行」上按 x0 签名识别；识别出的行标记为 table 角色。
    table_candidates = detect_table_candidates_from_lines(band_lines)
    out["table_candidates"] = table_candidates

    def in_table(o: Dict[str, Any]) -> bool:
        g = o["geom"]
        for tc in table_candidates:
            rx0, ry0, rx1, ry1 = tc["region"]
            if g["y0"] >= ry0 - 4 and g["y1"] <= ry1 + 4 and g["x0"] >= rx0 - 4 and g["x1"] <= rx1 + 4:
                return True
        return False

    for o in line_objs:
        role = classify_line(o["line"], page_h, body_size)
        if in_table(o) and role in ("body", "footnote_candidate"):
            role = "table"
        o["role"] = role

    if len(bands) == 1:
        ordered = sorted(line_objs, key=lambda o: (o["geom"]["y0"], o["geom"]["x0"]))
    else:
        # 通栏行作为锚点切分页面；锚点之间的内容按 (列, y, x) 排序。
        anchors = sorted((o for o in line_objs if o["spanning"]), key=lambda o: o["geom"]["y0"])
        col_lines = [o for o in line_objs if not o["spanning"]]

        def between(lo: float, hi: float) -> List[Dict[str, Any]]:
            sub = [o for o in col_lines if lo <= o["geom"]["y0"] < hi]
            return sorted(sub, key=lambda o: (o["band"], round(o["geom"]["y0"], 1),
                                              round(o["geom"]["x0"], 1)))

        ordered: List[Dict[str, Any]] = []
        prev_y = -1.0
        for a in anchors:
            ordered.extend(between(prev_y, a["geom"]["y0"]))
            ordered.append(a)
            prev_y = a["geom"]["y0"]
        ordered.extend(between(prev_y, float("inf")))
        if not anchors:
            ordered = sorted(col_lines, key=lambda o: (o["band"], round(o["geom"]["y0"], 1),
                                                       round(o["geom"]["x0"], 1)))

    # 块合并：按阅读顺序相邻行，若垂直间距小且角色/字号一致则并入同一块。
    heights = [o["geom"]["y1"] - o["geom"]["y0"] for o in ordered if o["geom"]["y1"] > o["geom"]["y0"]]
    line_h = median(heights) if heights else 10.0
    para_gap = max(6.0, para_gap_ratio * line_h)
    blocks: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    seq = 0
    for o in ordered:
        g = o["geom"]
        new_block = False
        if cur is None:
            new_block = True
        else:
            last = cur["lines"][-1]
            dy = g["y0"] - last["y1"]
            role_changed = o["role"] != cur["role"]
            size_changed = abs((g.get("size") or 0) - (cur.get("size") or 0)) > 0.6
            band_changed = o["band"] != cur.get("band")
            if (dy > para_gap or role_changed or size_changed or band_changed
                    or (o["spanning"] and not last.get("spanning"))):
                new_block = True
        if new_block:
            if cur:
                blocks.append(_finalize_block(cur, seq, page["page"]))
                seq += 1
            cur = {"page": page["page"], "role": o["role"], "band": o["band"],
                   "spanning": o["spanning"], "size": g.get("size", 0.0),
                   "lines": [{"text": g["text"], "x0": g["x0"], "y0": g["y0"],
                              "x1": g["x1"], "y1": g["y1"], "span_ids": [s["span_id"] for s in o["line"]],
                              "para_break": False}],
                   "span_ids": [s["span_id"] for s in o["line"]]}
        else:
            para = dy > para_gap * 0.9
            cur["lines"].append({"text": g["text"], "x0": g["x0"], "y0": g["y0"],
                                 "x1": g["x1"], "y1": g["y1"], "span_ids": [s["span_id"] for s in o["line"]],
                                 "para_break": para})
            cur["span_ids"].extend(s["span_id"] for s in o["line"])
    if cur:
        blocks.append(_finalize_block(cur, seq, page["page"]))
        seq += 1

    out["blocks"] = blocks
    out["reading_order"] = [b["block_id"] for b in blocks]
    return out


def _finalize_block(cur: Dict[str, Any], seq: int, page: int) -> Dict[str, Any]:
    cur["block_id"] = "p%d-b%02d" % (page, seq)
    cur["order"] = seq
    cur["bbox"] = {"x0": min(l["x0"] for l in cur["lines"]),
                   "y0": min(l["y0"] for l in cur["lines"]),
                   "x1": max(l["x1"] for l in cur["lines"]),
                   "y1": max(l["y1"] for l in cur["lines"])}
    cur["text"] = "\n".join(l["text"] for l in cur["lines"])
    cur["confidence"] = "high"
    cur["uncertainty"] = []
    cur["source"] = "text_layer"
    return cur


# --------------------------------------------------------------------------
# (3) 表格：从 span 重建行列 + 单元格归属 + 合并推断
# --------------------------------------------------------------------------
def extract_table(spans: List[Dict[str, Any]],
                  region: Optional[Tuple[float, float, float, float]] = None,
                  x_tol: float = 4.0,
                  y_tol: Optional[float] = None,
                  page: int = 1) -> Dict[str, Any]:
    """把 region 内的 span 重建为表格网格。

    返回 {"rows": [[cell,...]], "n_rows", "n_cols", "markdown", "uncertainty", ...}
    每个 cell: {"cell_id","row","col","text","rowspan","colspan","merged_into",
                "span_ids","bbox","uncertainty"}。
    """
    region = region or (0.0, 0.0, float("inf"), float("inf"))
    rx0, ry0, rx1, ry1 = region
    sel = [s for s in spans
           if s["x0"] >= rx0 - 0.5 and s["x1"] <= rx1 + 0.5
           and s["y0"] >= ry0 - 0.5 and s["y1"] <= ry1 + 0.5]
    if not sel:
        return {"rows": [], "n_rows": 0, "n_cols": 0, "markdown": "",
                "uncertainty": ["empty_region"], "page": page}

    heights = [s["y1"] - s["y0"] for s in sel if s["y1"] > s["y0"]]
    med_h = median(heights) if heights else 10.0
    y_tol = y_tol if y_tol is not None else max(3.0, 0.6 * med_h)

    # 列边界只由 x0 聚类决定（把 x1 也纳入会制造伪列）；
    # colspan 通过「span.x1 越过多少个列中心」推断，见下方 covered_cols。
    col_x = sorted(cluster_1d((s["x0"] for s in sel), x_tol))
    row_y = sorted(cluster_1d((s["y0"] for s in sel), y_tol))

    n_rows, n_cols = len(row_y), len(col_x)
    grid: List[List[Optional[Dict[str, Any]]]] = [
        [None for _ in range(n_cols)] for _ in range(n_rows)]

    def nearest(vals: List[float], v: float) -> int:
        return min(range(len(vals)), key=lambda i: abs(vals[i] - v))

    for s in sel:
        r = nearest(row_y, s["y0"])
        c = nearest(col_x, s["x0"])
        # colspan: x1 覆盖到第几个列中心之后
        covered_cols = [i for i in range(n_cols) if col_x[i] < s["x1"] - x_tol * 0.5]
        colspan = max(1, (max(covered_cols) + 1 - c)) if covered_cols else 1
        covered_rows = [i for i in range(n_rows) if row_y[i] < s["y1"] - y_tol * 0.5]
        rowspan = max(1, (max(covered_rows) + 1 - r)) if covered_rows else 1
        cell = grid[r][c]
        if cell is None:
            grid[r][c] = {"row": r, "col": c, "text": s["text"], "rowspan": rowspan,
                          "colspan": colspan, "span_ids": [s["span_id"]],
                          "uncertainty": []}
        else:
            if cell["text"]:
                cell["text"] += " " + s["text"]
            else:
                cell["text"] = s["text"]
            cell["span_ids"].append(s["span_id"])
            cell["rowspan"] = max(cell["rowspan"], rowspan)
            cell["colspan"] = max(cell["colspan"], colspan)
            cell["uncertainty"].append("overlapping_spans_in_cell")

    # 标记被 rowspan/colspan 覆盖的空单元格（merged_into 指向拥有者）
    for r in range(n_rows):
        for c in range(n_cols):
            cell = grid[r][c]
            if cell is not None:
                for dr in range(cell["rowspan"]):
                    for dc in range(cell["colspan"]):
                        if dr == 0 and dc == 0:
                            continue
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < n_rows and 0 <= cc < n_cols:
                            if grid[rr][cc] is None:
                                grid[rr][cc] = {"row": rr, "col": cc, "text": "",
                                                "rowspan": 1, "colspan": 1,
                                                "merged_into": f"p{page}:t{r+1}c{c+1}",
                                                "span_ids": [], "uncertainty": ["merged"]}
                            elif not grid[rr][cc].get("merged_into"):
                                grid[rr][cc]["uncertainty"].append("overlap_with_merge")

    rows = []
    for r in range(n_rows):
        row_cells = []
        for c in range(n_cols):
            cell = grid[r][c]
            if cell is None:
                cell = {"row": r, "col": c, "text": "", "rowspan": 1, "colspan": 1,
                        "span_ids": [], "uncertainty": ["empty_unexplained"]}
            cell["cell_id"] = f"p{page}:t{r+1}c{c+1}"
            if "bbox" not in cell:
                cx0 = col_x[c] if c < n_cols else 0.0
                cy0 = row_y[r] if r < n_rows else 0.0
                cell["bbox"] = {"x0": cx0, "y0": cy0,
                                "x1": col_x[min(c + cell["colspan"] - 1, n_cols - 1)],
                                "y1": row_y[min(r + cell["rowspan"] - 1, n_rows - 1)]}
            row_cells.append(cell)
        rows.append(row_cells)

    markdown = _grid_to_markdown(rows, n_rows, n_cols)
    uncertainty = []
    for row in rows:
        for cell in row:
            for u in cell["uncertainty"]:
                if u not in uncertainty:
                    uncertainty.append(u)
    return {"rows": rows, "n_rows": n_rows, "n_cols": n_cols, "markdown": markdown,
            "uncertainty": uncertainty, "page": page,
            "col_x": col_x, "row_y": row_y}


def _grid_to_markdown(rows: List[List[Dict[str, Any]]], n_rows: int, n_cols: int) -> str:
    if not rows or not rows[0]:
        return ""
    # Markdown 无 rowspan/colspan；把合并单元格文本放在左上角，其余留空，并在表后注记。
    md_rows = []
    for r in range(n_rows):
        cells = []
        for c in range(n_cols):
            cell = rows[r][c]
            if cell.get("merged_into"):
                cells.append("")
            else:
                cells.append(cell["text"].replace("|", "\\|").replace("\n", " ").strip())
        md_rows.append("| " + " | ".join(cells) + " |")
    header_sep = "| " + " | ".join(["---"] * n_cols) + " |"
    return "\n".join([md_rows[0], header_sep] + md_rows[1:])


def _looks_numeric(t: str) -> bool:
    t = t.strip()
    if not t:
        return False
    return bool(re.match(r"^[-+]?[0-9.,%±×\s]*[0-9][0-9.,%±×\s]*$", t))


# --------------------------------------------------------------------------
# (4) 证据 ID + 汇总
# --------------------------------------------------------------------------
def build_evidence_ids(blocks: List[Dict[str, Any]], page: int) -> List[Dict[str, Any]]:
    for i, b in enumerate(blocks):
        b.setdefault("block_id", "p%d-b%02d" % (page, i))
        b.setdefault("order", i)
        b.setdefault("page", page)
    return blocks


def special_char_annotations(text: str) -> List[Dict[str, str]]:
    """列出文本中的希腊字母/特殊符号及其 LaTeX 等价（用于公式保真标注）。"""
    out = []
    for ch in text:
        if ch in GREEK_MAP:
            out.append({"char": ch, "latex": GREEK_MAP[ch]})
    return out


def analyze_page(page: Dict[str, Any], **kw: Any) -> Dict[str, Any]:
    """把 assemble_page + 公式/特殊字符 合成为单页结果（表格候选已在 assemble_page 内计算）。"""
    result = assemble_page(page, **kw)
    formulas = []
    for b in result["blocks"]:
        if b.get("role") == "formula":
            ann = special_char_annotations(b["text"])
            formulas.append({"block_id": b["block_id"], "page": page["page"],
                             "text": b["text"], "latex_hint": None,
                             "special_chars": ann, "bbox": b["bbox"],
                             "uncertainty": ["heuristic_formula_role"]})
    result["formulas"] = formulas
    return result


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
def cmd_assemble(args: argparse.Namespace) -> int:
    raw = read_json_or_text(args.input, from_text=args.from_text)
    pages = load_pages(raw)
    out_pages = []
    all_blocks = []
    for pg in pages:
        res = analyze_page(pg, y_tol=args.y_tol, min_gap=args.min_gap,
                           para_gap_ratio=args.para_gap_ratio)
        out_pages.append(res)
        for b in res["blocks"]:
            b.setdefault("page", pg["page"])
            all_blocks.append(b)
    doc = {"source": raw.get("source", ""), "unit": raw.get("unit", "pt"),
           "origin": raw.get("origin", "top-left"),
           "per_page": out_pages,
           "blocks": sorted(all_blocks, key=lambda b: (b["page"], b["order"])),
           "stats": {"n_pages": len(pages), "n_blocks": len(all_blocks),
                     "n_lines": sum(len(p["blocks"]) for p in out_pages)}}
    emit(args.out, doc)
    print(f"assemble: {len(pages)} page(s), {len(all_blocks)} block(s)", file=sys.stderr)
    return 0


def cmd_table(args: argparse.Namespace) -> int:
    raw = read_json_or_text(args.input, from_text=False)
    pages = load_pages(raw)
    page = next((p for p in pages if p["page"] == args.page), None)
    if page is None and pages:
        page = pages[0]
    if page is None:
        print("table: no spans", file=sys.stderr)
        return 1
    region = None
    if args.region:
        parts = [float(x) for x in args.region.split(",")]
        if len(parts) != 4:
            print("table: --region must be x0,y0,x1,y1", file=sys.stderr)
            return 2
        region = tuple(parts)  # type: ignore[assignment]
    t = extract_table(page["spans"], region=region, page=page["page"])
    emit(args.out, t)
    print(f"table: {t['n_rows']}x{t['n_cols']} uncertainty={t['uncertainty']}", file=sys.stderr)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    doc = make_demo_spans()
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"demo spans written to {args.out}", file=sys.stderr)
    return 0


def cmd_self_test(args: argparse.Namespace) -> int:
    failures = run_self_tests()
    if failures:
        print(f"self-test: {len(failures)} FAILURE(S)", file=sys.stderr)
        for f in failures:
            print(" - " + f, file=sys.stderr)
        return 1
    print("self-test: OK", file=sys.stderr)
    return 0


def read_json_or_text(path: str, from_text: bool = False) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = f.read()
    if from_text:
        # 退化路径：纯文本按页分块（用 "\\f" 分页符；每行构造一个全宽 span）。
        pages_txt = re.split(r"\f", data)
        pages = []
        for i, txt in enumerate(pages_txt):
            if not txt.strip():
                continue
            spans = []
            y = 60.0
            for ln in txt.splitlines():
                if not ln.strip():
                    continue
                spans.append({"text": ln.strip(), "x0": 60.0, "y0": y,
                              "x1": 552.0, "y1": y + 12.0, "size": 10.0})
                y += 14.0
            pages.append({"page": i + 1, "width": 612.0, "height": 792.0,
                          "rotate": 0, "spans": spans})
        return {"source": path, "unit": "pt", "origin": "top-left", "pages": pages}
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        raise SystemExit(f"not valid JSON and --from-text not set: {e}")


def emit(out_path: Optional[str], obj: Dict[str, Any]) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
            f.write("\n")
    else:
        print(text)


# --------------------------------------------------------------------------
# 合成样例 + 自测
# --------------------------------------------------------------------------
def make_demo_spans() -> Dict[str, Any]:
    """构造一个双栏 + 底部表格的合成页面，用于演示与自测。"""
    spans = []
    W, H = 612.0, 792.0
    # 通栏标题
    spans.append({"text": "A Two-Column", "x0": 70, "y0": 60, "x1": 200, "y1": 75, "size": 18})
    # 左栏 12 行 / 右栏 12 行（不同 y0，模拟独立基线，且页面足够密）
    left_x, right_x = 60.0, 320.0
    y = 100.0
    for i in range(12):
        spans.append({"text": f"Left paragraph line {i}", "x0": left_x, "y0": y,
                      "x1": left_x + 170, "y1": y + 10, "size": 10})
        y += 14
    y = 99.0
    for i in range(12):
        spans.append({"text": f"Right column line {i}", "x0": right_x, "y0": y,
                      "x1": right_x + 150, "y1": y + 10, "size": 10})
        y += 14
    # 底部表格 2x2
    ty = 700.0
    for r in range(2):
        tx = 60.0
        for c in range(2):
            spans.append({"text": f"R{r+1}C{c+1}", "x0": tx, "y0": ty, "x1": tx + 100, "y1": ty + 12, "size": 9})
            tx += 120
        ty += 16
    return {"source": "demo.pdf", "unit": "pt", "origin": "top-left",
            "pages": [{"page": 1, "width": W, "height": H, "rotate": 0, "spans": spans}]}


def run_self_tests() -> List[str]:
    failures: List[str] = []
    doc = make_demo_spans()
    pages = load_pages(doc)
    page = pages[0]

    bands = detect_column_bands(page["spans"], 612.0, 792.0)
    if len(bands) != 2:
        failures.append(f"expected 2 columns, got {len(bands)}: {bands}")

    res = assemble_page(page)
    # 左栏内容必须整体排在右栏之前（列优先）：用块的顺序号比较，而不是同串内位置。
    def block_order(needle: str) -> int:
        for b in res["blocks"]:
            if needle in b["text"]:
                return b["order"]
        return -1
    lo = block_order("Left paragraph line 11")
    ro = block_order("Right column line 0")
    if not (lo >= 0 and ro >= 0 and lo < ro):
        failures.append(f"column reading order broken: left(last)={lo}, right(first)={ro}")

    # 表格候选应被识别（≥2 列、≥2 行的 x0 签名对齐）
    if not res.get("table_candidates"):
        failures.append("table candidate not detected")
    # 表格行不能被误判为脚注
    for b in res["blocks"]:
        if b["text"].startswith("R1C1") and b["role"] == "footnote_candidate":
            failures.append("table row misclassified as footnote")

    # 表格区域重建
    t = extract_table(page["spans"], region=(40, 690, 400, 740), page=1)
    if t["n_rows"] != 2 or t["n_cols"] != 2:
        failures.append(f"table grid expected 2x2, got {t['n_rows']}x{t['n_cols']}")
    flat = [c["text"] for row in t["rows"] for c in row]
    if "R1C1" not in flat or "R2C2" not in flat:
        failures.append("table cell text missing")

    # 证据 ID 稳定性
    ids = [b["block_id"] for b in res["blocks"]]
    if len(ids) != len(set(ids)):
        failures.append("duplicate block ids")
    if not all(re.match(r"^p1-b\d+$", i) for i in ids):
        failures.append("malformed block id")
    return failures


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="PDF span post-processor (stdlib only)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("assemble", help="assemble spans into ordered blocks")
    pa.add_argument("input")
    pa.add_argument("--out", default=None)
    pa.add_argument("--from-text", action="store_true")
    pa.add_argument("--y-tol", type=float, default=3.0)
    pa.add_argument("--min-gap", type=float, default=12.0)
    pa.add_argument("--para-gap-ratio", type=float, default=1.5)
    pa.set_defaults(func=cmd_assemble)

    pt = sub.add_parser("table", help="extract a table grid from spans")
    pt.add_argument("input")
    pt.add_argument("--page", type=int, default=1)
    pt.add_argument("--region", default=None, help="x0,y0,x1,y1 in points")
    pt.add_argument("--out", default=None)
    pt.set_defaults(func=cmd_table)

    pd = sub.add_parser("demo", help="write a synthetic demo span file")
    pd.add_argument("--out", default="demo_spans.json")
    pd.set_defaults(func=cmd_demo)

    ps = sub.add_parser("self-test", help="run built-in assertions")
    ps.set_defaults(func=cmd_self_test)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
