#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""refs.py — 参考文献与引用管理核心工具（仅标准库，Python >= 3.8，无第三方依赖）。

子命令（每个都可独立运行、输出 JSON 便于 Agent 复核）：
  normalize  把 BibTeX / RIS / JSONL / TSV 文献库解析成统一的 canonical 记录（JSONL）。
  dedup      用可解释的匹配键检测重复条目：DOI > 题名+第一作者+年份 > 作者+年份+出处，
             并显式输出“禁止合并”的同名同作者不同文献。
  renumber   顺序编码制编号：按正文首次出现顺序给 [CITE:key] 标记分配连续编号，
             同步重排文末列表，支持 "1,2-4" 区间折叠与上标样式。
  validate   双向校验：正文引用的每条是否都在文献表中、文献表每条是否都被引用、
             数字编号是否越界/重复。
  format     将 canonical 记录渲染为 GB/T 7714—2015（顺序编码制）或 APA-7（尽力而为）。
  self-test  运行内置示例并断言关键行为（回归自检）。

设计原则：
  - 可解释：每个去重/重排/校验结果都带 reason 与 confidence，绝不静默合并。
  - 幂等：同输入多次运行输出一致（排序确定、不依赖哈希随机化）。
  - 容错：缺字段不崩溃，标记为 missing 并继续。
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import re
import sys
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 1. 规范化工具（去重键的每一段都可单独解释）
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[\W_]+", re.UNICODE)          # 非字母数字下划线 → 分隔
_WS_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_LEADING_ARTICLE_RE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)
_YEAR_RE = re.compile(r"(18|19|20)\d{2}")
_DOI_CLEAN_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?", re.IGNORECASE)
_DOI_TRAIL_RE = re.compile(r"[.,;)\]]+$")
_FIRST_PAGE_RE = re.compile(r"^(\d+)")


def norm_doi(doi: Optional[str]) -> str:
    """DOI 规范化：去前缀、小写、去尾标点。空值返回 ''。"""
    if not doi:
        return ""
    s = html.unescape(str(doi)).strip()
    s = _DOI_CLEAN_RE.sub("", s, count=1)
    s = _DOI_TRAIL_RE.sub("", s)
    return s.lower()


def norm_title(title: Optional[str]) -> str:
    """题名规范化：NFKC → 小写 → 去 HTML → 去标点 → 折叠空白 → 去英文首冠词。

    中文题名仅去掉标点；中英文题名之间不会因该函数相等（这是设计如此，
    跨语言等价只能靠 作者+年份+出处 的次级键判定，见 pair_match）。
    """
    if not title:
        return ""
    s = unicodedata.normalize("NFKC", str(title))
    s = html.unescape(s)
    s = _HTML_TAG_RE.sub(" ", s)
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip().lower()
    s = _LEADING_ARTICLE_RE.sub("", s, count=1)
    return s


def norm_venue(venue: Optional[str]) -> str:
    """出处（刊名/会议名/出版社）规范化。"""
    if not venue:
        return ""
    s = unicodedata.normalize("NFKC", str(venue)).lower()
    s = html.unescape(s)
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def split_name(raw: Optional[str]) -> Dict[str, str]:
    """把一条作者字符串拆成 {family, given}。支持 'Smith, John'、'John Smith'、'王伟'。"""
    out: Dict[str, str] = {"family": "", "given": ""}
    if not raw:
        return out
    s = html.unescape(str(raw)).strip()
    if "," in s:
        family, _, given = s.partition(",")
        out["family"] = family.strip()
        out["given"] = given.strip()
        return out
    parts = s.split()
    if len(parts) == 1:
        # 单 token：中文姓名 '王伟' 或单姓 'Einstein'
        out["family"] = parts[0]
        return out
    # 西方姓名 'John Smith'：姓为最后一个 token
    out["family"] = parts[-1]
    out["given"] = " ".join(parts[:-1])
    return out


def norm_surname(author: Optional[Dict[str, str]]) -> str:
    """姓氏规范化（用于第一作者匹配）。"""
    if not author:
        return ""
    fam = author.get("family") or ""
    if not fam and author.get("given"):
        # 兼容只有全名字段的情况
        fam = str(author["given"]).split()[-1]
    return unicodedata.normalize("NFKC", str(fam)).lower()


def extract_year(entry: Dict[str, Any]) -> str:
    """年份抽取：优先 year 字段，其次 date；取首个 4 位年。"""
    for src in (entry.get("year"), entry.get("date")):
        if src is None:
            continue
        m = _YEAR_RE.search(str(src))
        if m:
            return m.group(0)
    return ""


def first_page(entry: Dict[str, Any]) -> str:
    pages = entry.get("pages") or ""
    m = _FIRST_PAGE_RE.search(str(pages))
    return m.group(1) if m else ""


def authors_of(entry: Dict[str, Any]) -> List[Dict[str, str]]:
    """统一返回作者列表；优先已结构化 authors，否则解析 authors_text。"""
    auths = entry.get("authors")
    if isinstance(auths, list) and auths:
        result = []
        for a in auths:
            if isinstance(a, dict):
                result.append(split_name(" ".join(filter(None, [a.get("family", ""), a.get("given", "")]))))
            else:
                result.append(split_name(str(a)))
        return result
    raw = entry.get("authors_text")
    if raw:
        return [split_name(x) for x in _split_author_list(str(raw))]
    return []


def _split_author_list(raw: str) -> List[str]:
    if " and " in raw.lower():
        return [x.strip() for x in re.split(r"\s+and\s+", raw, flags=re.IGNORECASE) if x.strip()]
    if ";" in raw:
        return [x.strip() for x in raw.split(";") if x.strip()]
    if "," in raw and _looks_like_comma_sep(raw):
        return [x.strip() for x in raw.split(",") if x.strip()]
    return [raw]


def _looks_like_comma_sep(raw: str) -> bool:
    # 仅当逗号两侧都像完整姓名时才按逗号切，避免 'Smith, John' 被误切。
    pieces = [p.strip() for p in raw.split(",")]
    return len(pieces) >= 3 and all(pieces)


def make_dedup_key(entry: Dict[str, Any]) -> Dict[str, str]:
    """可解释的去重键。每段独立，便于在 merge_reason 里引用具体命中的字段。"""
    authors = authors_of(entry)
    first_author = authors[0] if authors else {}
    doi = norm_doi(entry.get("doi"))
    return {
        "doi_norm": doi,
        "title_norm": norm_title(entry.get("title")),
        "title_alt_norm": norm_title(entry.get("title_original")),
        "first_author_norm": norm_surname(first_author),
        "year": extract_year(entry),
        "venue_norm": norm_venue(entry.get("venue") or entry.get("journal") or entry.get("booktitle")),
        "volume": str(entry.get("volume") or "").strip().lower(),
        "first_page": first_page(entry),
    }


def title_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _both_nonempty(*vals: str) -> bool:
    return all(v for v in vals)


def pair_match(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """两两判定。返回 verdict ∈ {same_work, candidate_merge, ambiguous, different_work}。

    判定顺序即优先级（高置信优先）：
      1) DOI 相同                     → same_work (0.99)
      2) 题名相同 + 第一作者 + 年份   → same_work (0.95)
      3) 题名相同（作者/年份缺失或不符）→ candidate_merge (0.80)
      4) 题名不同但 作者+年份+出处 同，且卷/首页同或缺失 → candidate_merge (0.75)（中英题名/预印本vs正式版）
      5) 作者+年份同，题名明显不同，出处也不同/缺 → different_work（同名作者不同文献，禁并）
      6) 仅作者+年份同，其余缺 → ambiguous（字段不足，交人工）
      其余 → different_work
    """
    ka, kb = make_dedup_key(a), make_dedup_key(b)
    reasons: List[str] = []

    if _both_nonempty(ka["doi_norm"], kb["doi_norm"]):
        if ka["doi_norm"] == kb["doi_norm"]:
            return _v("same_work", 0.99, "DOI 一致: " + ka["doi_norm"])
        # DOI 都有但不同 → 同一作者同名论文的强排除证据
        return _v("different_work", 0.98, "DOI 不同: %s vs %s" % (ka["doi_norm"], kb["doi_norm"]))

    title_a = ka["title_norm"] or ka["title_alt_norm"]
    title_b = kb["title_norm"] or kb["title_alt_norm"]
    same_title = _both_nonempty(title_a, title_b) and title_a == title_b
    same_author = _both_nonempty(ka["first_author_norm"], kb["first_author_norm"]) and \
        ka["first_author_norm"] == kb["first_author_norm"]
    same_year = _both_nonempty(ka["year"], kb["year"]) and ka["year"] == kb["year"]

    if same_title and same_author and same_year:
        return _v("same_work", 0.95, "题名+第一作者+年份一致")
    if same_title and same_author:
        return _v("same_work", 0.85, "题名+第一作者一致（年份缺失或不符）")
    if same_title:
        return _v("candidate_merge", 0.80, "题名一致但作者/年份缺失或不符，需人工确认")

    same_venue = _both_nonempty(ka["venue_norm"], kb["venue_norm"]) and ka["venue_norm"] == kb["venue_norm"]
    same_vol = _both_nonempty(ka["volume"], kb["volume"]) and ka["volume"] == kb["volume"]
    same_page = _both_nonempty(ka["first_page"], kb["first_page"]) and ka["first_page"] == kb["first_page"]

    if same_author and same_year and same_venue:
        # 同一作者同一年在同一出处、题名不同：极可能是同一工作的中英题名/预印本与正式版/期刊与会议版本。
        # 不自动合并，交人工确认；卷/首页也一致时置信更高。
        sim = title_similarity(title_a, title_b)
        conf = 0.80 if (same_vol or same_page) else 0.70
        return _v(
            "candidate_merge", conf,
            "第一作者+年份+出处一致、题名不同（题名相似度 %.2f）：可能是中英题名/预印本与正式版/期刊与会议版本，需人工确认" % sim,
            extra={"title_similarity": round(sim, 4)},
        )

    if same_author and same_year:
        sim = title_similarity(title_a, title_b)
        if _both_nonempty(title_a, title_b) and sim < 0.55 and not same_venue:
            return _v(
                "different_work", 0.85,
                "同名作者同年份但题名相似度仅 %.2f 且出处不同/缺失：判为不同文献，禁止合并" % sim,
                extra={"title_similarity": round(sim, 4)},
            )
        return _v(
            "ambiguous", 0.40,
            "仅第一作者+年份一致，题名/出处字段不足：需人工判定（题名相似度 %.2f）" % sim,
            extra={"title_similarity": round(sim, 4)},
        )

    return _v("different_work", 0.0, "无有效匹配键（作者/年份/题名/DOI 均无一致证据）")


def _v(verdict: str, confidence: float, reason: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    d: Dict[str, Any] = {"verdict": verdict, "confidence": confidence, "reason": reason}
    if extra:
        d.update(extra)
    return d


# ---------------------------------------------------------------------------
# 2. 文献库解析（BibTeX / RIS / JSONL / TSV）
# ---------------------------------------------------------------------------

def parse_bibtex(text: str) -> List[Dict[str, Any]]:
    """容忍式 BibTeX 解析：支持 @type{...} 与 @type(...)，嵌套花括号按层计数。"""
    entries: List[Dict[str, Any]] = []
    i = 0
    n = len(text)
    while i < n:
        m = re.search(r"@(\w+)\s*([({])", text[i:])
        if not m:
            break
        typ = m.group(1).lower()
        open_ch = m.group(2)
        close_ch = "}" if open_ch == "{" else ")"
        start = i + m.end()
        # 条目开括号已被 m 消费，故初始深度为 1；内部字段值的花括号不再影响条目边界。
        depth = 1
        j = start
        while j < n:
            c = text[j]
            if c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth != 0:
            # 未闭合：把剩余当作一条，避免崩溃
            j = n
        body = text[start:j]
        key, fields = _parse_bib_body(body)
        entry: Dict[str, Any] = {"key": key or "bib%d" % len(entries), "type": _BIB_TYPE.get(typ, "other"), "source_fmt": "bibtex"}
        entry.update(_map_bib_fields(fields))
        entries.append(entry)
        i = j + 1
    return entries


def _parse_bib_body(body: str) -> Tuple[str, Dict[str, str]]:
    key = ""
    idx = body.find(",")
    if idx != -1:
        key = body[:idx].strip()
        body = body[idx + 1:]
    fields: Dict[str, str] = {}
    pos = 0
    while pos < len(body):
        m = re.search(r"([A-Za-z][A-Za-z0-9_\-]*)\s*=\s*", body[pos:])
        if not m:
            break
        fname = m.group(1).lower()
        vstart = pos + m.end()
        if vstart >= len(body):
            break
        if body[vstart] in "{(":
            open_c = body[vstart]
            close_c = "}" if open_c == "{" else ")"
            depth = 0
            k = vstart
            while k < len(body):
                if body[k] == open_c:
                    depth += 1
                elif body[k] == close_c:
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            value = body[vstart + 1:k].strip()
            fields[fname] = _strip_braces(value)
            pos = k + 1
        else:
            # 非花括号值（带引号或裸值）：扫描到深度 0 处的下一个逗号
            quote = body[vstart] if body[vstart] in "\"'" else None
            comma = vstart
            while comma < len(body):
                if quote and body[comma] == quote:
                    quote = None
                elif quote is None and body[comma] in "\"'":
                    quote = body[comma]
                elif quote is None and body[comma] == ",":
                    break
                comma += 1
            value = body[vstart:comma].strip()
            fields[fname] = value.strip('"').strip("'").strip()
            pos = comma
        # 跳到下一个字段或结尾
        while pos < len(body) and body[pos] in " \t\n\r,":
            pos += 1
    return key, fields


def _strip_braces(s: str) -> str:
    # 去 LaTeX 分组花括号与多余空白
    return re.sub(r"[{}]", "", s).strip()


def _map_bib_fields(fields: Dict[str, str]) -> Dict[str, Any]:
    authors_raw = fields.get("author", "")
    return {
        "authors_text": authors_raw,
        "title": fields.get("title", ""),
        "year": fields.get("year", ""),
        "venue": fields.get("journal") or fields.get("booktitle") or fields.get("publisher", ""),
        "volume": fields.get("volume", ""),
        "issue": fields.get("number", ""),
        "pages": fields.get("pages", ""),
        "doi": fields.get("doi", ""),
        "url": fields.get("url", ""),
        "publisher": fields.get("publisher", ""),
        "raw_fields": fields,
    }


def parse_ris(text: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    cur: Dict[str, List[str]] = {}
    for line in text.splitlines():
        if line.startswith("ER  -") or line.strip() == "ER":
            if cur:
                entries.append(_ris_to_entry(cur))
                cur = {}
            continue
        if len(line) >= 6 and line[2:6] == "  - ":
            tag = line[:2].strip().upper()
            value = line[6:].strip()
            cur.setdefault(tag, []).append(value)
        elif line.strip():
            # 续行
            if cur:
                last = list(cur.keys())[-1]
                cur[last][-1] += " " + line.strip()
    if cur:
        entries.append(_ris_to_entry(cur))
    return entries


_BIB_TYPE = {
    "article": "journal-article", "inproceedings": "conference", "conference": "conference",
    "book": "book", "inbook": "book-chapter", "incollection": "book-chapter",
    "phdthesis": "thesis", "mastersthesis": "thesis", "techreport": "report",
    "unpublished": "preprint", "misc": "other", "online": "web", "www": "web",
}

_RIS_TYPE = {
    "JOUR": "journal-article", "JFULL": "journal-article", "CONF": "conference",
    "CPAPER": "conference", "RPRT": "report", "THES": "thesis", "BOOK": "book",
    "CHAP": "book-chapter", "ELEC": "web", "GEN": "other", "PREPRINT": "preprint",
}


def _ris_to_entry(cur: Dict[str, List[str]]) -> Dict[str, Any]:
    def one(tag: str) -> str:
        vals = cur.get(tag, [])
        return vals[0] if vals else ""

    authors_raw = "; ".join(cur.get("AU", []) + cur.get("A1", []))
    typ = _RIS_TYPE.get(one("TY").upper(), "other")
    return {
        "key": one("ID") or one("AN") or "ris%d" % len(cur),
        "type": typ,
        "source_fmt": "ris",
        "authors_text": authors_raw,
        "title": one("TI") or one("T1"),
        "title_original": one("TT"),
        "year": one("PY") or one("Y1"),
        "venue": one("JO") or one("JF") or one("T2") or one("BT"),
        "volume": one("VL"),
        "issue": one("IS"),
        "pages": one("SP") + ("-" + one("EP") if one("EP") else ""),
        "doi": one("DO"),
        "url": one("UR"),
        "publisher": one("PB"),
    }


def parse_jsonl(text: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, list):
            entries.extend(obj)
        else:
            entries.append(obj)
    return entries


def parse_tsv(text: str) -> List[Dict[str, Any]]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    header = [h.strip().lower() for h in lines[0].split("\t")]
    entries = []
    for ln in lines[1:]:
        vals = ln.split("\t")
        obj = {header[i]: vals[i] for i in range(min(len(header), len(vals)))}
        entries.append(_map_flat_fields(obj))
    return entries


def _map_flat_fields(obj: Dict[str, Any]) -> Dict[str, Any]:
    """把常见导出列名映射到 canonical 字段。"""
    out: Dict[str, Any] = dict(obj)
    out.setdefault("key", obj.get("id") or obj.get("key") or obj.get("record_id") or "")
    out.setdefault("title", obj.get("title") or obj.get("ti") or "")
    out.setdefault("authors_text", obj.get("authors") or obj.get("author") or obj.get("au") or "")
    out.setdefault("year", obj.get("year") or obj.get("py") or obj.get("date") or "")
    out.setdefault("venue", obj.get("journal") or obj.get("venue") or obj.get("jo") or obj.get("source") or "")
    out.setdefault("doi", obj.get("doi") or obj.get("do") or "")
    out.setdefault("volume", obj.get("volume") or obj.get("vl") or "")
    out.setdefault("issue", obj.get("issue") or obj.get("is") or obj.get("number") or "")
    out.setdefault("pages", obj.get("pages") or obj.get("sp") or "")
    out.setdefault("url", obj.get("url") or obj.get("link") or "")
    return out


def normalize_library(raw_text: str, fmt: str = "auto") -> List[Dict[str, Any]]:
    """入口：按格式解析并规范化。auto 时按内容特征推断。"""
    fmt = (fmt or "auto").lower()
    if fmt == "auto":
        s = raw_text.lstrip()[:200].lower()
        if s.startswith("{") or s.startswith("["):
            fmt = "jsonl"
        elif s.startswith("@") or raw_text.lstrip().startswith("@"):
            fmt = "bibtex"
        elif re.search(r"^TY\s+-\s+", raw_text, flags=re.MULTILINE):
            fmt = "ris"
        elif "\t" in (raw_text.splitlines()[0] if raw_text.splitlines() else ""):
            fmt = "tsv"
        else:
            fmt = "jsonl"
    if fmt == "bibtex":
        entries = parse_bibtex(raw_text)
    elif fmt == "ris":
        entries = parse_ris(raw_text)
    elif fmt == "tsv":
        entries = parse_tsv(raw_text)
    else:  # jsonl
        entries = parse_jsonl(raw_text)
    # 补齐稳定 key（脚本幂等依赖 key 稳定）
    for idx, e in enumerate(entries):
        if not e.get("key"):
            e["key"] = "ref%d" % idx
    return entries


# ---------------------------------------------------------------------------
# 3. 去重
# ---------------------------------------------------------------------------

def _is_preprint(e: Dict[str, Any]) -> bool:
    return str(e.get("type", "")).lower() in {"preprint", "working-paper"} or \
        "arxiv" in (str(e.get("url", "")) + str(e.get("doi", ""))).lower()


def _completeness(e: Dict[str, Any]) -> int:
    score = 0
    for f in ("title", "year", "venue", "doi", "volume", "pages", "authors_text"):
        if e.get(f):
            score += 1
    if _is_preprint(e):
        score -= 2
    return score


def choose_canonical(cluster: List[Dict[str, Any]]) -> Dict[str, Any]:
    """簇内代表：优先有 DOI、优先正式版、再按字段完整度。"""
    with_doi = [e for e in cluster if norm_doi(e.get("doi"))]
    pool = with_doi or cluster
    pool = sorted(pool, key=lambda e: (_is_preprint(e), -_completeness(e)))
    return pool[0]


def detect_duplicates(entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """O(n^2) 成对判定并做并查集聚类。输出含解释，供 Agent 直接写入来源映射记录。"""
    n = len(entries)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    same_edges: List[Dict[str, Any]] = []
    candidates: List[Dict[str, Any]] = []
    kept_separate: List[Dict[str, Any]] = []
    for i in range(n):
        for j in range(i + 1, n):
            res = pair_match(entries[i], entries[j])
            rec = {"a": i, "b": j, "a_key": entries[i].get("key"), "b_key": entries[j].get("key"), **res}
            if res["verdict"] == "same_work":
                union(i, j)
                same_edges.append(rec)
            elif res["verdict"] == "candidate_merge":
                candidates.append(rec)
            elif res["verdict"] == "different_work" and res.get("confidence", 0) >= 0.8 and \
                    make_dedup_key(entries[i])["first_author_norm"] and \
                    make_dedup_key(entries[i])["first_author_norm"] == make_dedup_key(entries[j])["first_author_norm"]:
                kept_separate.append(rec)
    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    clusters = []
    for members in groups.values():
        if len(members) < 2:
            continue
        canonical = choose_canonical([entries[i] for i in members])
        reason_parts = [same_edges[k]["reason"] for k in range(len(same_edges))
                        if same_edges[k]["a"] in members and same_edges[k]["b"] in members]
        clusters.append({
            "canonical_key": canonical.get("key"),
            "member_keys": [entries[i].get("key") for i in members],
            "confidence": 0.95,
            "reason": " ; ".join(sorted(set(reason_parts))),
            "canonical": canonical,
        })
    singletons = [entries[i].get("key") for i in range(n) if len(groups.get(find(i), [])) == 1]
    return {
        "total_input": n,
        "clusters": clusters,
        "candidates_need_human": candidates,
        "kept_separate_same_author": kept_separate,
        "singletons": singletons,
        "merged_entry_count": n - len(groups),
    }


# ---------------------------------------------------------------------------
# 4. 正文标记解析与编号
# ---------------------------------------------------------------------------

_KEYED_SINGLE_RE = re.compile(r"\[CITE:([A-Za-z0-9_.:/\-]+)\]")
_KEYED_MULTI_RE = re.compile(r"\[CITE:([^\]]+)\]")
_NUMERIC_RE = re.compile(r"\[(\d{1,4}(?:\s*[-–—]\s*\d{1,4})?(?:\s*,\s*\d{1,4}(?:\s*[-–—]\s*\d{1,4})?)*)\]")


def parse_keyed_markers(text: str) -> List[Dict[str, Any]]:
    """提取 [CITE:key] / [CITE:k1,k2] 标记，返回按位置排序的列表。"""
    markers: List[Dict[str, Any]] = []
    for m in _KEYED_MULTI_RE.finditer(text):
        keys = [k.strip() for k in m.group(1).split(",") if k.strip()]
        markers.append({"start": m.start(), "end": m.end(), "raw": m.group(0), "keys": keys})
    markers.sort(key=lambda x: x["start"])
    return markers


def first_appearance_order(markers: Sequence[Dict[str, Any]]) -> List[str]:
    order: List[str] = []
    seen = set()
    for mk in markers:
        for k in mk["keys"]:
            if k not in seen:
                seen.add(k)
                order.append(k)
    return order


def _collapse_ranges(nums: Sequence[int]) -> str:
    nums = sorted(set(nums))
    parts: List[str] = []
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        if j - i >= 2:
            parts.append("%d-%d" % (nums[i], nums[j]))
        elif j - i == 1:
            parts.append("%d,%d" % (nums[i], nums[j]))
        else:
            parts.append("%d" % nums[i])
        i = j + 1
    return ",".join(parts)


def renumber_keyed(text: str, key_order: Optional[Sequence[str]] = None,
                   superscript: bool = False) -> Dict[str, Any]:
    """把 [CITE:key] 替换为连续编号标记。

    编号规则：按正文首次出现顺序 1..N（若给定 key_order 则使用该顺序，未出现的 key 排后）。
    多引合并为 [n1,n2]，连续号折叠为 [n1-n2]。superscript=True 时输出 ^[n]。
    """
    markers = parse_keyed_markers(text)
    order = list(key_order) if key_order is not None else first_appearance_order(markers)
    index: Dict[str, int] = {k: i + 1 for i, k in enumerate(order)}
    # 文本里出现但不在 order 中的 key：追加到末尾，保证有编号
    for mk in markers:
        for k in mk["keys"]:
            if k not in index:
                index[k] = len(index) + 1
                order = list(index.keys())

    out_chars = list(text)
    for mk in reversed(markers):  # 从后往前替换，避免偏移
        nums = [index[k] for k in mk["keys"]]
        rendered = "[" + _collapse_ranges(nums) + "]"
        if superscript:
            rendered = "^" + rendered
        out_chars[mk["start"]:mk["end"]] = rendered
    warnings = [{"key": mk["raw"], "reason": "marker 含空 key 列表"} for mk in markers if not mk["keys"]]
    return {
        "text": "".join(out_chars),
        "order": order,
        "index": index,
        "warnings": warnings,
    }


def order_references(entries: Sequence[Dict[str, Any]], order: Sequence[str]) -> Dict[str, Any]:
    """按 order 重排文献表；返回重排后列表 + 未用/缺失条目报告。"""
    by_key = {str(e.get("key")): e for e in entries}
    ordered: List[Dict[str, Any]] = []
    used = set()
    missing: List[str] = []
    for k in order:
        if k in by_key:
            ordered.append(by_key[k])
            used.add(k)
        else:
            missing.append(k)
    unused = [str(e.get("key")) for e in entries if str(e.get("key")) not in used]
    return {"entries": ordered, "missing_in_library": missing, "unused_in_library": unused, "by_key": by_key}


# ---------------------------------------------------------------------------
# 5. 双向校验
# ---------------------------------------------------------------------------

def parse_numeric_markers(text: str) -> List[Dict[str, Any]]:
    markers = []
    for m in _NUMERIC_RE.finditer(text):
        nums: List[int] = []
        for part in re.split(r",", m.group(1)):
            rng = re.split(r"\s*[-–—]\s*", part.strip())
            if len(rng) == 2 and rng[0].isdigit() and rng[1].isdigit():
                nums.extend(range(int(rng[0]), int(rng[1]) + 1))
            elif part.strip().isdigit():
                nums.append(int(part.strip()))
        markers.append({"start": m.start(), "end": m.end(), "raw": m.group(0), "nums": sorted(set(nums))})
    return markers


def validate_citations(text: str, entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """双向校验：正文标记与文献表互相核验。

    支持两类标记：
      - 键名标记 [CITE:key]：按 key 集合比对文献表。
      - 数字标记 [n] / [n,m] / [n-m]：按序号 1..N 比对文献表长度。
    返回项：
      keyed_missing_in_list    正文引了但文献表没有的 key（错误）。
      keyed_unused_in_list     文献表有但正文从未引用的 key（反向缺引用，需补挂或删条）。
      numeric_out_of_range     数字编号 <1 或 > 文献表长度（编号越界）。
      numeric_uncited_indices  1..N 中从未在正文出现的序号（列表有未引用条目）。
      ok                       上述错误项全为空。
    注：同一来源被多次引用是正常的，不计为错误。
    """
    keyed = parse_keyed_markers(text)
    cited_keys: List[str] = []
    for mk in keyed:
        cited_keys.extend(mk["keys"])
    cited_key_set = set(cited_keys)
    lib_keys = [str(e.get("key")) for e in entries]
    lib_key_set = set(lib_keys)

    keyed_missing = sorted(cited_key_set - lib_key_set)
    keyed_unused = sorted(lib_key_set - cited_key_set) if keyed else []

    numeric = parse_numeric_markers(text)
    n_refs = len(entries)
    cited_idx = sorted({num for mk in numeric for num in mk["nums"]})
    numeric_out_of_range = [num for num in cited_idx if num < 1 or num > n_refs]
    numeric_uncited = ([i for i in range(1, n_refs + 1) if i not in set(cited_idx)] if numeric else [])

    errors = bool(keyed_missing) or bool(keyed_unused) or bool(numeric_out_of_range) or bool(numeric_uncited)
    return {
        "keyed_cited_keys": sorted(set(cited_keys)),
        "library_keys": lib_keys,
        "keyed_missing_in_list": keyed_missing,
        "keyed_unused_in_list": keyed_unused,
        "numeric_markers": len(numeric),
        "numeric_cited_indices": cited_idx,
        "numeric_out_of_range": numeric_out_of_range,
        "numeric_uncited_indices": numeric_uncited,
        "citations_found": bool(keyed or numeric),
        "ok": not errors,
    }


# ---------------------------------------------------------------------------
# 6. 著者—出版年制（APA）同年消歧
# ---------------------------------------------------------------------------

def assign_author_year_suffixes(entries: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """对 (第一作者姓, 年份) 相同的条目赋 a/b/c 后缀，返回 {key: suffix}。"""
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for e in entries:
        k = make_dedup_key(e)
        authors = authors_of(e)
        fam = norm_surname(authors[0]) if authors else ""
        groups.setdefault((fam, k["year"]), []).append(e)
    suffix: Dict[str, str] = {}
    for (_, _), members in groups.items():
        if len(members) > 1:
            # 按标题排序保证幂等
            members_sorted = sorted(members, key=lambda e: norm_title(e.get("title")))
            for i, e in enumerate(members_sorted):
                suffix[str(e.get("key"))] = "abcdefghijklmnopqrstuvwxyz"[i]
    return suffix


# ---------------------------------------------------------------------------
# 7. 格式渲染（尽力而为，标点与斜体需人工在编辑器中复核）
# ---------------------------------------------------------------------------

def _fmt_authors_gbt(authors: List[Dict[str, str]]) -> str:
    names = []
    for a in authors:
        fam = a.get("family", "")
        given = a.get("given", "")
        if not fam:
            continue
        if re.search(r"[\u4e00-\u9fff]", fam + given):
            names.append(fam + given)  # 中文姓名连写
        else:
            initials = " ".join(p[0].upper() for p in given.split() if p)
            names.append(fam.upper() + (" " + initials if initials else ""))
    if not names:
        return "佚名"
    if len(names) <= 3:
        return ", ".join(names)
    return ", ".join(names[:3]) + ", 等"


def format_gbt7714(entry: Dict[str, Any], index: Optional[int] = None) -> str:
    """GB/T 7714—2015（顺序编码制）单条渲染，[文献类型标识] 按 type 映射。

    仅输出纯文本骨架；中文标点、字体（斜体刊名/卷号）与序号格式需在编辑器最终排版时复核。
    """
    authors = _fmt_authors_gbt(authors_of(entry))
    title = entry.get("title") or entry.get("title_original") or "（题名缺失）"
    year = extract_year(entry)
    type_mark = {
        "journal-article": "J", "conference": "C", "book": "M", "thesis": "D",
        "report": "R", "book-chapter": "M", "preprint": "EB/OL", "web": "EB/OL",
    }.get(str(entry.get("type", "")), "Z")
    venue = entry.get("venue") or ""
    volume = entry.get("volume") or ""
    issue = entry.get("issue") or ""
    pages = (entry.get("pages") or "").replace("--", "-")
    core = "%s. %s[%s]. " % (authors, title, type_mark)
    if type_mark in ("J", "C", "Z") and venue:
        parts = [venue]
        if year:
            parts.append(year)
        volissue = volume + ("(" + issue + ")" if issue else "")
        if volissue:
            parts.append(volissue)
        loc = ", ".join(parts)
        if pages:
            loc += ": " + pages
        core += loc + "."
    elif type_mark == "M":
        loc = venue
        if year:
            loc = (loc + ", " if loc else "") + year
        if pages:
            loc += ": " + pages
        core += loc + "."
    elif type_mark in ("EB/OL", "Z"):
        loc = entry.get("url") or venue
        if loc:
            core += loc
        if year:
            core += ", %s" % year
        core += "."
    else:
        core = core.rstrip() + "."
    if year and type_mark not in ("J", "C", "Z", "M"):
        core = core.rstrip(".") + ", %s." % year
    doi = norm_doi(entry.get("doi"))
    if doi:
        core += " DOI:%s." % doi
    prefix = "[%d] " % index if index is not None else ""
    return prefix + core


def _fmt_authors_apa(authors: List[Dict[str, str]]) -> str:
    names = []
    for a in authors:
        fam = a.get("family", "")
        given = a.get("given", "")
        if not fam:
            continue
        if re.search(r"[\u4e00-\u9fff]", fam + given):
            names.append(fam + given)  # 中文名常连写，具体依出版方
        else:
            initials = "".join(p[0] + "." for p in given.split() if p)
            names.append(fam + ", " + (initials + " " if initials else "").strip())
    if not names:
        return "Anonymous"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return names[0] + ", & " + names[1]
    if len(names) <= 20:
        return ", ".join(names[:-1]) + ", & " + names[-1]
    return ", ".join(names[:19]) + ", ... " + names[-1]


def format_apa7(entry: Dict[str, Any]) -> str:
    """APA-7 单条渲染（纯文本；卷号、书名斜体需在编辑器补加）。"""
    authors = _fmt_authors_apa(authors_of(entry))
    year = extract_year(entry)
    title = entry.get("title") or "（题名缺失）"
    venue = entry.get("venue") or ""
    volume = entry.get("volume") or ""
    issue = entry.get("issue") or ""
    pages = entry.get("pages") or ""
    doi = norm_doi(entry.get("doi"))
    if doi:
        url = "https://doi.org/" + doi
    else:
        url = entry.get("url") or ""
    head = "%s (%s). %s. " % (authors, year or "n.d.", title)
    if str(entry.get("type", "")).lower() in ("journal-article", "preprint", "conference"):
        mid = venue
        if volume:
            mid += ", %s" % volume
            if issue:
                mid += "(%s)" % issue
        if pages:
            mid += ", %s" % pages
        head += mid + "."
    else:
        head += venue + "."
    if url:
        head += " " + url
    return head


def format_entries(entries: Sequence[Dict[str, Any]], style: str, numbered: bool = True) -> str:
    lines = []
    for i, e in enumerate(entries):
        if style == "apa7":
            lines.append(format_apa7(e))
        else:
            lines.append(format_gbt7714(e, index=i + 1 if numbered else None))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _write_file(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _load_entries(path: str) -> List[Dict[str, Any]]:
    raw = _read_file(path)
    if path.endswith(".jsonl"):
        return parse_jsonl(raw)
    # 也允许给原始 bib/ris 文件
    return normalize_library(raw)


def _dump_json(obj: Any, path: str) -> None:
    _write_file(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="参考文献与引用管理工具（stdlib-only）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_norm = sub.add_parser("normalize", help="解析文献库为 canonical JSONL")
    sp_norm.add_argument("library")
    sp_norm.add_argument("--fmt", default="auto", choices=["auto", "bibtex", "ris", "jsonl", "tsv"])
    sp_norm.add_argument("--out", default="refs.jsonl")

    sp_dedup = sub.add_parser("dedup", help="检测重复条目")
    sp_dedup.add_argument("refs")
    sp_dedup.add_argument("--out", default="dedup.json")

    sp_ren = sub.add_parser("renumber", help="顺序编码制编号同步")
    sp_ren.add_argument("manuscript")
    sp_ren.add_argument("refs")
    sp_ren.add_argument("--order", default=None, help="逗号分隔的 key 顺序；缺省按正文首次出现")
    sp_ren.add_argument("--superscript", action="store_true")
    sp_ren.add_argument("--out-manuscript", default="manuscript_renumbered.txt")
    sp_ren.add_argument("--out-refs", default="refs_ordered.jsonl")

    sp_val = sub.add_parser("validate", help="正文与文献表双向校验")
    sp_val.add_argument("manuscript")
    sp_val.add_argument("refs")
    sp_val.add_argument("--out", default="validate.json")

    sp_fmt = sub.add_parser("format", help="渲染为 GB/T 7714 或 APA-7")
    sp_fmt.add_argument("refs")
    sp_fmt.add_argument("--style", default="gbt7714", choices=["gbt7714", "apa7"])
    sp_fmt.add_argument("--out", default="refs.txt")

    sub.add_parser("self-test", help="运行内置自检")

    args = p.parse_args(argv)
    if args.cmd == "self-test":
        return self_test()
    if args.cmd == "normalize":
        entries = normalize_library(_read_file(args.library), args.fmt)
        _write_file(args.out, "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n")
        print(json.dumps({"ok": True, "count": len(entries), "out": args.out}, ensure_ascii=False))
        return 0
    if args.cmd == "dedup":
        entries = _load_entries(args.refs)
        result = detect_duplicates(entries)
        _dump_json(result, args.out)
        print(json.dumps({"ok": True, "clusters": len(result["clusters"]),
                          "candidates_need_human": len(result["candidates_need_human"]),
                          "out": args.out}, ensure_ascii=False))
        return 0
    if args.cmd == "renumber":
        text = _read_file(args.manuscript)
        entries = _load_entries(args.refs)
        order = [k for k in (args.order.split(",") if args.order else []) if k]
        ren = renumber_keyed(text, order or None, superscript=args.superscript)
        ord_refs = order_references(entries, ren["order"])
        _write_file(args.out_manuscript, ren["text"])
        _write_file(args.out_refs, "\n".join(json.dumps(e, ensure_ascii=False) for e in ord_refs["entries"]) + "\n")
        report = {"order": ren["order"], "index": ren["index"],
                  "missing_in_library": ord_refs["missing_in_library"],
                  "unused_in_library": ord_refs["unused_in_library"],
                  "warnings": ren["warnings"]}
        _dump_json(report, args.out_manuscript + ".report.json")
        print(json.dumps({"ok": True, "cited": len(ren["order"]), "out_manuscript": args.out_manuscript,
                          "out_refs": args.out_refs,
                          "missing_in_library": ord_refs["missing_in_library"],
                          "unused_in_library": ord_refs["unused_in_library"]}, ensure_ascii=False))
        return 0
    if args.cmd == "validate":
        text = _read_file(args.manuscript)
        entries = _load_entries(args.refs)
        report = validate_citations(text, entries)
        _dump_json(report, args.out)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["ok"] else 2
    if args.cmd == "format":
        entries = _load_entries(args.refs)
        text = format_entries(entries, args.style, numbered=(args.style != "apa7"))
        _write_file(args.out, text)
        print(json.dumps({"ok": True, "count": len(entries), "out": args.out}, ensure_ascii=False))
        return 0
    return 0


# ---------------------------------------------------------------------------
# 自检（回归测试）
# ---------------------------------------------------------------------------

def self_test() -> int:
    failures: List[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if not cond:
            failures.append(name + (" | " + detail if detail else ""))

    # 1) DOI 规范化
    check("doi", norm_doi("https://doi.org/10.1000/ABC.123") == "10.1000/abc.123", norm_doi("https://doi.org/10.1000/ABC.123"))
    # 2) 题名规范化去冠词/标点
    check("title", norm_title("The Quick, Brown: Fox!") == "quick brown fox", norm_title("The Quick, Brown: Fox!"))
    # 3) 去重：DOI 一致 → same_work
    a = {"key": "a", "title": "A study", "authors_text": "Smith, John", "year": "2020", "doi": "10.1/x"}
    b = {"key": "b", "title": "A study (dup)", "authors_text": "John Smith", "year": "2020", "doi": "10.1/X"}
    r = pair_match(a, b)
    check("dedup-doi", r["verdict"] == "same_work", str(r))
    # 4) 去重：中英题名 + 作者年份出处一致 → candidate_merge（不自动合并）
    c = {"key": "c", "title": "基于深度学习的图像分割", "authors_text": "王伟", "year": "2021", "venue": "计算机学报"}
    d = {"key": "d", "title": "Image segmentation based on deep learning", "authors_text": "王伟", "year": "2021", "venue": "计算机学报", "volume": "44", "pages": "1-10"}
    r2 = pair_match(c, d)
    check("dedup-bilingual", r2["verdict"] == "candidate_merge", str(r2))
    # 5) 去重：同名同作者同年不同文献 → different_work（禁并）
    e = {"key": "e", "title": "Neural networks for vision", "authors_text": "Smith, John", "year": "2020", "venue": "Nature"}
    f = {"key": "f", "title": "Quantum error correction", "authors_text": "Smith, John", "year": "2020", "venue": "Science"}
    r3 = pair_match(e, f)
    check("dedup-false-merge-guard", r3["verdict"] == "different_work", str(r3))
    # 6) 编号：首次出现顺序 + 区间折叠 + 上标
    text = "结论甲[CITE:b]；方法乙[CITE:a]，且[CITE:b,c,d]成立。"
    ren = renumber_keyed(text, ["a", "b", "c", "d"])
    check("renumber", ren["text"] == "结论甲[2]；方法乙[1]，且[2-4]成立。", ren["text"])
    check("renumber-index", ren["index"] == {"a": 1, "b": 2, "c": 3, "d": 4}, str(ren["index"]))
    # 7) 双向校验：缺条目、越界、未引用条目
    entries = [{"key": "a"}, {"key": "b"}]
    v = validate_citations("结论[CITE:a][CITE:zz]与[9]。", entries)
    check("validate-missing", v["keyed_missing_in_list"] == ["zz"], str(v["keyed_missing_in_list"]))
    check("validate-unused", v["keyed_unused_in_list"] == ["b"], str(v["keyed_unused_in_list"]))
    check("validate-range", v["numeric_out_of_range"] == [9], str(v["numeric_out_of_range"]))
    check("validate-ok-false", v["ok"] is False, str(v["ok"]))
    # 8) APA 消歧
    g = [{"key": "g1", "title": "Alpha", "authors_text": "Smith, John", "year": "2020"},
         {"key": "g2", "title": "Beta", "authors_text": "John Smith", "year": "2020"}]
    sfx = assign_author_year_suffixes(g)
    check("apa-suffix", set(sfx.values()) == {"a", "b"}, str(sfx))

    if failures:
        print("SELF-TEST FAILED:")
        for f in failures:
            print("  - " + f)
        return 1
    print("self-test OK: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
