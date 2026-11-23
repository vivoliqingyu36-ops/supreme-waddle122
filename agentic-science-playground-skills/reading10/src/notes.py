#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notes.py — structured-paper-notes 的机械校验 / 抽取 / 归并工具。

用途：把「文献总结与结构化笔记」Skill 中可由机器判定的部分做成确定性的、
仅用 Python 标准库的命令行工具，把 Agent 的语义判断限定在最小范围，其余交给
可复跑的函数。四个问题对应的能力：

  对得上  -> section_alignment_check()     章节骨架是否与论文自身章节一致
  留得住  -> extract_fields() + check_fields()  字段齐备、结论前提条件在位
  找得回  -> validate_anchor() + check_anchors() 每条笔记都能回到原文位置
  用得上  -> dedupe_knowledge_points() + resolve_abbreviations() 术语归一、去重、冲突检测

设计约定：
  - 所有函数纯函数、幂等、确定性（除 dict 键顺序由输入顺序决定外）。
  - 输入/输出都是 JSON（UTF-8）。不联网、不调外部工具、不修改输入文件。
  - 语义抽取（一句话总结、定义、结论等）由 LLM/Agent 完成；本脚本只负责
    机械校验、启发式定位、归并计划与报告，绝不替 Agent 编造科学内容。
  - 本文件可独立运行：`python3 notes.py self-test` 验证核心逻辑。

命令速览：
  python3 notes.py self-test
  python3 notes.py extract-fields   --source source.json --out report.json
  python3 notes.py check-sections   --notes notes.json --source source.json --out report.json
  python3 notes.py check-fields     --notes notes.json --out report.json
  python3 notes.py check-anchors    --notes notes.json --source source.json --out report.json
  python3 notes.py dedupe-kps       --notes notes.json --out report.json
  python3 notes.py build-result     --notes notes.json --case-id <id> --out result.json
"""

import argparse
import json
import re
import sys
import unicodedata

SCHEMA_VERSION = "1.0.0"

# 论文卡片必须覆盖的字段族（与 rubric「留得住」对齐）
FIELD_KEYS = ("research_question", "data", "method", "findings", "limitations", "conditions")
FIELD_STATUS = {"reported", "partial", "not_reported", "conflict"}
KP_TYPES = {"concept", "variable", "method", "claim", "condition", "abbreviation", "dataset", "other"}
UNCERTAINTY_KINDS = {
    "unreadable", "not_reported", "conflict", "ambiguous",
    "heuristic_guess", "missing_data", "unverified", "other",
}
CONFIDENCE_VALUES = {"high", "medium", "low", "unknown"}
ANCHOR_REQUIRED_KEYS = ("locator", "section_id", "page")

# 章节标题 -> 论文卡片字段 的启发式映射（只做预填建议，须由 Agent 确认，标记 heuristic_guess）
FIELD_SECTION_PATTERNS = (
    ("research_question", re.compile(
        r"\bintro|introduction|objective|research question|problem statement|"
        r"motivation|background|aim|purpose|significance|"
        r"引言|绪论|研究问题|研究目标|研究目的|研究背景|研究意义|前言", re.I)),
    ("data", re.compile(
        r"\bdata\b|material|dataset|sample|participant|study population|cohort|"
        r"survey|administrative|数据|材料|样本|研究对象|资料|数据来源|样本来源", re.I)),
    ("method", re.compile(
        r"\bmethod|experiment|design|procedure|protocol|model|estimation|"
        r"identification|statistical analysis|regression|framework|"
        r"方法|实验|设计|流程|模型|分析|估计|识别|框架|研究设计", re.I)),
    ("findings", re.compile(
        r"\bresult|finding|outcome|结果|发现|研究发现", re.I)),
    ("limitations", re.compile(
        r"limitation|caveat|weakness|future work|robustness|sensitivity|"
        r"局限|不足|展望|未来工作|稳健性|敏感性", re.I)),
    ("conditions", re.compile(
        r"assumption|condition|scope|validity|premise|前提|假设|条件|适用范围|"
        r"成立|边界", re.I)),
)

# 章节在论证中的作用（role 提示，不强制，Agent 按原文确认）
SECTION_ROLE_PATTERNS = (
    ("background", re.compile(r"intro|introduction|background|related work|引言|绪论|背景|相关工作", re.I)),
    ("problem", re.compile(r"problem|objective|research question|motivation|问题|目标|研究问题", re.I)),
    ("method", re.compile(r"method|material|data|design|procedure|model|方法|材料|数据|设计|模型", re.I)),
    ("results", re.compile(r"result|finding|结果|发现", re.I)),
    ("discussion", re.compile(r"discussion|implication|解释|讨论|含义", re.I)),
    ("conclusion", re.compile(r"conclusion|summary|结论|总结", re.I)),
    ("limitations", re.compile(r"limitation|caveat|局限|不足", re.I)),
    ("other", re.compile(r".*")),
)


# ---------------------------------------------------------------------------
# 文本归一化（术语、锚点引用、引用串匹配共用）
# ---------------------------------------------------------------------------
def normalize_text(s):
    """NFKC + 非断空格转普通空格 + 连续空白折叠为一个空格 + 去首尾空白。"""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_term(s):
    """术语/标题归一：小写 + 去首尾分隔标点，用于术语归并与章节标题匹配。

    不去括号/方括号：括号内容可能是术语本体（如化学式、缩写展开），
    去掉会破坏匹配。"""
    t = normalize_text(s)
    t = t.lower()
    t = t.strip(".,;:!?\"'`，。；：！？…·-–— ")
    return t


def contains_quote(haystack, quote):
    """判断 quote 是否以「归一化空白后的逐字子串」形式出现在 haystack 中。

    大小写保持敏感（科学术语/变量大小写有意义）；只做 NFKC 与空白折叠，不改写字符。
    空 quote 视为未检查（返回 True，调用方应另行标注）。
    """
    h = normalize_text(haystack)
    q = normalize_text(quote)
    if not q:
        return True
    return q in h


# ---------------------------------------------------------------------------
# 源文件（source.json）索引
# ---------------------------------------------------------------------------
def _index_blocks(source):
    """把 source 的 sections[].blocks 与顶层 blocks 拍平成 {block_id: {...}}。"""
    idx = {}
    for sec in source.get("sections", []) or []:
        for b in sec.get("blocks", []) or []:
            bid = b.get("block_id")
            if bid is not None:
                idx[bid] = {
                    "page": b.get("page"),
                    "text": b.get("text", "") or "",
                    "section_id": sec.get("section_id"),
                }
    for b in source.get("blocks", []) or []:
        bid = b.get("block_id")
        if bid is not None:
            idx.setdefault(bid, {"page": b.get("page"), "text": b.get("text", "") or "",
                                 "section_id": b.get("section_id")})
    return idx


def _source_section_ids(source):
    return [s.get("section_id") for s in (source.get("sections", []) or [])
            if s.get("section_id") is not None]


# ---------------------------------------------------------------------------
# 对得上：章节骨架对齐检查
# ---------------------------------------------------------------------------
def section_alignment_check(notes_sections, source):
    """校验 notes 的章节骨架是否与论文自身章节（source.sections）一致。

    notes_sections: result.json 的 sections[]（含 section_id/title/order/heading_block_id）
    source:         source.json（ground-truth 章节 + blocks）

    返回 report：
      aligned             是否整体对齐（无漏节/多余节/顺序错/标题块缺失）
      total/matched       笔记章节数 / 能匹配到原文的章节数
      coverage            matched / source 章节数
      extra_section       笔记里有、原文没有的章节（通用模板套用 → 最危险的对不上）
      missing_sections    原文有、笔记漏掉的章节
      order_errors        笔记章节顺序与原文顺序不一致
      heading_not_found   笔记声称的标题块在原文里不存在
    """
    src = {}
    for s in (source.get("sections", []) or []):
        if s.get("section_id") is not None:
            src[s.get("section_id")] = s
    src_by_title = {}
    for s in (source.get("sections", []) or []):
        t = normalize_term(s.get("title", ""))
        if t:
            src_by_title[t] = s
    block_idx = _index_blocks(source)

    report = {
        "aligned": False,
        "total": len(notes_sections),
        "matched": 0,
        "coverage": 0.0,
        "extra_section": [],
        "missing_sections": [],
        "order_errors": [],
        "heading_not_found": [],
    }

    # 按 order 排序；order 缺失的按输入顺序
    ordered = sorted(
        enumerate(notes_sections),
        key=lambda iv: (iv[1].get("order") if isinstance(iv[1].get("order"), int)
                        else 10 ** 9, iv[0]),
    )
    seen_src = set()
    src_pos = {sid: i for i, sid in enumerate(_source_section_ids(source))}
    last_src_pos = -1
    last_order = -1

    for _input_idx, ns in ordered:
        sid = ns.get("section_id")
        title = ns.get("title", "")
        match = None
        if sid in src:
            match = src[sid]
        else:
            match = src_by_title.get(normalize_term(title))
        if match is None:
            report["extra_section"].append({"section_id": sid, "title": title})
            continue
        matched_id = match.get("section_id")
        if matched_id in seen_src:
            report["order_errors"].append({
                "section_id": sid,
                "title": title,
                "error": "duplicate_mapping",
            })
        seen_src.add(matched_id)
        report["matched"] += 1

        hb = ns.get("heading_block_id")
        if hb and hb not in block_idx:
            report["heading_not_found"].append({
                "section_id": sid, "heading_block_id": hb,
            })

        o = ns.get("order")
        if isinstance(o, int):
            if o <= last_order:
                report["order_errors"].append({
                    "section_id": sid, "order": o,
                    "error": "order_not_strictly_increasing",
                    "expected_greater_than": last_order,
                })
            last_order = o
        if matched_id in src_pos:
            if src_pos[matched_id] <= last_src_pos:
                report["order_errors"].append({
                    "section_id": sid, "title": title,
                    "error": "order_differs_from_source",
                    "source_position": src_pos[matched_id],
                })
            last_src_pos = src_pos[matched_id]

    report["missing_sections"] = [
        {"section_id": s.get("section_id"), "title": s.get("title")}
        for s in (source.get("sections", []) or [])
        if s.get("section_id") is not None and s.get("section_id") not in seen_src
    ]
    n_src = len((source.get("sections", []) or []))
    report["coverage"] = (report["matched"] / n_src) if n_src else 1.0
    report["aligned"] = bool(
        report["matched"] == n_src
        and not report["extra_section"]
        and not report["missing_sections"]
        and not report["order_errors"]
        and not report["heading_not_found"]
    )
    return report


# ---------------------------------------------------------------------------
# 留得住：字段抽取（启发式定位）与字段完整性校验
# ---------------------------------------------------------------------------
def extract_fields(source):
    """把 source.sections 的标题按关键词启发式映射到论文卡片字段。

    只输出「哪个字段应由哪个 section_id 提供素材」的预填建议；是否采纳、如何总结
    由 Agent 判定。结果 confidence 恒为 heuristic_guess，避免被当作事实。
    """
    mapping = {k: [] for k, _ in FIELD_SECTION_PATTERNS}
    for sec in (source.get("sections", []) or []):
        title = sec.get("title") or ""
        sid = sec.get("section_id")
        if not title:
            continue
        for field, pat in FIELD_SECTION_PATTERNS:
            if pat.search(title):
                mapping[field].append(sid)
    return {
        "method": "heading-keyword-heuristic",
        "confidence": "heuristic_guess",
        "note": "仅按章节标题关键词建议字段来源；未命中的字段可能来自正文非标题段落或未报告，需 Agent 逐字段确认。",
        "field_sections": mapping,
    }


def _has_anchor(anchor):
    return isinstance(anchor, dict) and anchor.get("locator")


def _field_anchored(field):
    """判断一个字段（field 对象）是否带锚点。"""
    if _has_anchor(field.get("anchor")):
        return True
    items = field.get("items") or []
    return bool(items) and all(_has_anchor(it.get("anchor")) for it in items)


def check_fields(card, section_ids=None):
    """校验论文卡片字段族是否齐备、非空、带锚点、findings.condition_ids 可解析。

    card: result.json 的 paper_card。
    返回 report.complete 与逐字段/逐 finding 的错误列表。机器可判定，不需语义。
    """
    report = {"complete": False, "fields": {}, "errors": []}
    for k in FIELD_KEYS:
        f = card.get(k) if isinstance(card, dict) else None
        if f is None:
            report["fields"][k] = "missing"
            report["errors"].append({"field": k, "error": "missing_field"})
            continue
        if not isinstance(f, dict):
            report["fields"][k] = "bad_type"
            report["errors"].append({"field": k, "error": "field_not_object"})
            continue
        status = f.get("status")
        if status not in FIELD_STATUS:
            report["fields"][k] = "bad_status"
            report["errors"].append({"field": k, "error": "bad_status", "status": status})
            continue
        if status == "not_reported":
            report["fields"][k] = "not_reported_ok"
            continue
        items = f.get("items") or []
        value = f.get("value")
        if not items and not (value and str(value).strip()):
            report["fields"][k] = "empty"
            report["errors"].append({"field": k, "error": "empty_reported_field",
                                     "status": status})
            continue
        anchored = _field_anchored(f)
        if k == "method":
            # method 用 components/conditions 承载子项，而非 items
            sub = (f.get("components") or []) + (f.get("conditions") or [])
            if sub:
                anchored = anchored or all(
                    _has_anchor(c.get("anchor")) for c in sub if isinstance(c, dict))
        report["fields"][k] = "anchored" if anchored else "unanchored"
        if not anchored:
            report["errors"].append({"field": k, "error": "unanchored_reported_field",
                                     "status": status})

    # findings 的条件引用必须能落到 conditions 字段的 items
    cond_field = card.get("conditions") if isinstance(card, dict) else None
    cond_items = (cond_field.get("items") or []) if isinstance(cond_field, dict) else []
    cond_ids = {c.get("condition_id") for c in cond_items
                if isinstance(c, dict) and c.get("condition_id") is not None}
    findings = ((card.get("findings") or {}).get("items") or []) if isinstance(card, dict) else []
    for fi in findings:
        if not isinstance(fi, dict):
            continue
        for cid in (fi.get("condition_ids") or []):
            if cid not in cond_ids:
                report["errors"].append({
                    "field": "findings",
                    "error": "condition_id_unresolved",
                    "finding_id": fi.get("finding_id"),
                    "condition_id": cid,
                })
    report["complete"] = not report["errors"]
    return report


# ---------------------------------------------------------------------------
# 找得回：锚点校验
# ---------------------------------------------------------------------------
def validate_anchor(anchor, source, section_ids=None):
    """校验单个锚点对象能否回到原文。

    检查：必需键（locator/section_id/page）；page 为 int 且在 [1, page_count]；
    section_id 存在；block_id 存在；quote 在目标块或全文中能找到逐字子串。
    返回 problems 列表；空列表 = 通过。quote 找不到时给 error 但带 warning=True，
    因为引文可能跨块/排版重建，需人工复核而非直接判死。
    """
    problems = []
    if not isinstance(anchor, dict):
        return [{"error": "anchor_not_object"}]
    for k in ANCHOR_REQUIRED_KEYS:
        if k not in anchor:
            problems.append({"error": "missing_required_key", "key": k})

    page = anchor.get("page")
    if page is not None:
        if isinstance(page, bool) or not isinstance(page, int):
            problems.append({"error": "page_not_int", "page": page})
        else:
            pc = source.get("page_count")
            if isinstance(pc, int) and pc > 0 and (page < 1 or page > pc):
                problems.append({"error": "page_out_of_range", "page": page,
                                 "page_count": pc})

    sid = anchor.get("section_id")
    if sid:
        ids = set(_source_section_ids(source))
        if section_ids:
            ids |= set(section_ids)
        if sid not in ids:
            problems.append({"error": "section_id_not_found", "section_id": sid})

    block_idx = _index_blocks(source)
    bid = anchor.get("block_id")
    if bid and bid not in block_idx:
        problems.append({"error": "block_id_not_found", "block_id": bid})

    quote = anchor.get("quote")
    if quote and str(quote).strip():
        found = False
        if bid and bid in block_idx:
            found = contains_quote(block_idx[bid].get("text", ""), quote)
        if not found:
            hay_all = "\n".join(b.get("text", "") for b in block_idx.values())
            if contains_quote(hay_all, quote):
                problems.append({"error": "quote_found_in_other_block",
                                 "quote": str(quote)[:80], "warning": True})
            else:
                problems.append({"error": "quote_not_found",
                                 "quote": str(quote)[:80]})

    conf = anchor.get("confidence")
    if conf is not None and conf not in CONFIDENCE_VALUES:
        problems.append({"error": "bad_confidence", "confidence": conf})
    return problems


def _walk_anchor(anchor, path, results, source, section_ids, inherited=None):
    if anchor is None:
        if inherited is not None:
            results.append({"path": path, "anchor": None,
                            "problems": [{"error": "anchor_missing_uses_field_anchor",
                                          "warning": True}],
                            "ok": True})
        else:
            results.append({"path": path, "anchor": None,
                            "problems": [{"error": "anchor_missing"}],
                            "ok": False})
        return
    probs = validate_anchor(anchor, source, section_ids)
    results.append({"path": path, "anchor": anchor, "problems": probs,
                    "ok": not probs or all(p.get("warning") for p in probs)})


def check_anchors(notes, source):
    """遍历 notes 中所有关键笔记的锚点并逐条校验，返回 problems 列表。"""
    results = []
    section_ids = {s.get("section_id") for s in (notes.get("sections") or [])
                   if isinstance(s, dict) and s.get("section_id") is not None}
    card = notes.get("paper_card") if isinstance(notes.get("paper_card"), dict) else {}

    for k in FIELD_KEYS:
        f = card.get(k)
        if not isinstance(f, dict):
            continue
        if f.get("status") == "not_reported":
            continue
        if _has_anchor(f.get("anchor")):
            _walk_anchor(f.get("anchor"), "paper_card.%s" % k, results, source,
                         section_ids)
        if k == "findings":
            for fi in (f.get("items") or []):
                if not isinstance(fi, dict):
                    continue
                _walk_anchor(fi.get("anchor"),
                             "paper_card.findings.%s" % fi.get("finding_id"),
                             results, source, section_ids, inherited=f.get("anchor"))
        elif k == "method":
            for c in (f.get("components") or []):
                if isinstance(c, dict):
                    _walk_anchor(c.get("anchor"),
                                 "paper_card.method.component.%s" % c.get("name"),
                                 results, source, section_ids, inherited=f.get("anchor"))
            for c in (f.get("conditions") or []):
                if isinstance(c, dict):
                    _walk_anchor(c.get("anchor"),
                                 "paper_card.method.condition", results, source,
                                 section_ids, inherited=f.get("anchor"))
        else:
            for it in (f.get("items") or []):
                if isinstance(it, dict):
                    _walk_anchor(it.get("anchor"), "paper_card.%s.item" % k,
                                 results, source, section_ids, inherited=f.get("anchor"))

    # conditions 字段的 items 已由上面的 FIELD_KEYS 通用 else 分支遍历，不再重复。

    for sec in (notes.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        summ = sec.get("summary") if isinstance(sec.get("summary"), dict) else {}
        _walk_anchor(summ.get("anchor"),
                     "section.%s.summary" % sec.get("section_id"),
                     results, source, section_ids)
        for claim in (summ.get("claims") or []):
            if isinstance(claim, dict):
                _walk_anchor(claim.get("anchor"),
                             "section.%s.claim.%s" % (sec.get("section_id"),
                                                      claim.get("claim_id")),
                             results, source, section_ids,
                             inherited=summ.get("anchor"))

    for kp in (notes.get("knowledge_points") or []):
        if isinstance(kp, dict):
            _walk_anchor(kp.get("anchor"), "kp.%s" % kp.get("kp_id"),
                         results, source, section_ids)
    return results


# ---------------------------------------------------------------------------
# 用得上：知识点归并与冲突检测、缩写展开
# ---------------------------------------------------------------------------
def dedupe_knowledge_points(kps):
    """按 (normalized_term, type) 归组，检测重复与矛盾，产出归并计划。

    规则：
      - 同一组内定义兼容（一个为空 / 相同 / 一个包含另一个）→ 视为重复，保留
        定义更完整的条目，把其它条目并入 merged_from，并合并 synonyms/
        abbreviations/额外锚点。
      - 定义互不包含且都非空 → 视为冲突，保留两条并互相标 conflict_with，
        报告 conflict 供 Agent 复核（可能真是两种含义，也可能有一处抄错）。
    返回：{"input_count", "output_count", "merged", "conflicts", "report"}。
    """
    groups = {}
    for kp in kps:
        if not isinstance(kp, dict):
            continue
        key = (normalize_term(kp.get("term") or kp.get("canonical") or ""),
               kp.get("type"))
        groups.setdefault(key, []).append(kp)

    merged = []
    conflicts = []
    merge_records = []
    for (term, typ), group in groups.items():
        if not term and len(group) == 1:
            merged.append(dict(group[0]))
            continue
        group_sorted = sorted(group, key=lambda k: -len(normalize_text(k.get("definition"))))
        kept = dict(group_sorted[0])
        for other in group_sorted[1:]:
            dk = normalize_text(kept.get("definition"))
            dk2 = normalize_text(other.get("definition"))
            compatible = (not dk or not dk2 or dk == dk2 or dk2 in dk or dk in dk2)
            if compatible:
                kept.setdefault("merged_from", [])
                kept["merged_from"].append(other.get("kp_id"))
                kept["merged_from"] = sorted(set(kept["merged_from"]))
                for keyname in ("synonyms", "abbreviations"):
                    kept.setdefault(keyname, [])
                    for v in (other.get(keyname) or []):
                        if v not in kept[keyname]:
                            kept[keyname].append(v)
                if other.get("anchor"):
                    kept.setdefault("additional_anchors", [])
                    kept["additional_anchors"].append(other["anchor"])
                merge_records.append({
                    "kept": kept.get("kp_id"),
                    "merged": other.get("kp_id"),
                    "term": term,
                    "type": typ,
                })
            else:
                kept.setdefault("conflict_with", [])
                kept["conflict_with"].append(other.get("kp_id"))
                kept["conflict_with"] = sorted(set(kept["conflict_with"]))
                conflicts.append({
                    "term": term,
                    "type": typ,
                    "kp_a": kept.get("kp_id"),
                    "kp_b": other.get("kp_id"),
                    "reason": "definitions_contradict",
                })
        merged.append(kept)

    return {
        "input_count": len(kps),
        "output_count": len(merged),
        "merged": merge_records,
        "conflicts": conflicts,
        "report": merged,
    }


def resolve_abbreviations(kps):
    """把 type=abbreviation 的知识点连到其展开的 concept/variable 知识点。

    返回 [{abbreviation, expands_to, relation}]，供 Agent 决定是否并入/建立 relations。
    """
    concepts = [k for k in kps if isinstance(k, dict) and k.get("type") != "abbreviation"]
    links = []
    for k in kps:
        if not isinstance(k, dict) or k.get("type") != "abbreviation":
            continue
        term = normalize_term(k.get("term") or "")
        target = None
        for c in concepts:
            abbrs = [normalize_term(x) for x in (c.get("abbreviations") or [])]
            if term and term in abbrs:
                target = c
                break
        if target is None:
            for c in concepts:
                if term in (normalize_term(c.get("canonical") or ""),
                            normalize_term(c.get("term") or "")):
                    target = c
                    break
        if target:
            links.append({
                "abbreviation": k.get("kp_id"),
                "expands_to": target.get("kp_id"),
                "relation": "is_abbreviation_of",
            })
    return links


# ---------------------------------------------------------------------------
# 结果组装
# ---------------------------------------------------------------------------
RESULT_REQUIRED_KEYS = ("case_id", "schema_version", "status", "document",
                        "paper_card", "sections", "knowledge_points",
                        "evidence", "uncertainty")


def build_result(notes, case_id):
    """把草稿 notes 组装成 result.json：回填 case_id/schema_version、校验必填键、
    补 status 与 warnings。notes 里已有显式 status 则保留（防止覆盖诚实标注）。"""
    out = dict(notes)
    out["case_id"] = case_id
    out.setdefault("schema_version", SCHEMA_VERSION)
    warnings = list(out.get("warnings") or [])
    for k in RESULT_REQUIRED_KEYS:
        if k not in out:
            warnings.append("missing_required_top_level_key:%s" % k)
            out.setdefault(k, [] if k in ("sections", "knowledge_points",
                                          "uncertainty") else None)
    if "status" not in out or out.get("status") is None:
        out["status"] = "partial" if warnings else "success"
    if warnings:
        out["warnings"] = warnings
    return out


# ---------------------------------------------------------------------------
# 自测（内置最小样例，验证四个问题的核心判定逻辑）
# ---------------------------------------------------------------------------
def self_test():
    source = {
        "file": "example.pdf",
        "page_count": 3,
        "sections": [
            {"section_id": "s1", "title": "Introduction", "start_page": 1, "end_page": 1,
             "heading_block_id": "p1-b01",
             "blocks": [{"block_id": "p1-b01", "page": 1, "text": "We study X."},
                        {"block_id": "p1-b02", "page": 1,
                         "text": "Our research question is whether X affects Y."}]},
            {"section_id": "s2", "title": "Data", "start_page": 2, "end_page": 2,
             "heading_block_id": "p2-b01",
             "blocks": [{"block_id": "p2-b01", "page": 2, "text": "We use 100 firms."}]},
            {"section_id": "s3", "title": "Results", "start_page": 3, "end_page": 3,
             "heading_block_id": "p3-b01",
             "blocks": [{"block_id": "p3-b01", "page": 3,
                         "text": "X increases Y by 0.5 (p<0.01)."}]},
        ],
    }
    notes = {
        "sections": [
            {"section_id": "s1", "title": "Introduction", "order": 1,
             "heading_block_id": "p1-b01", "level": 1,
             "summary": {"anchor": {"locator": "s1 p.1", "section_id": "s1", "page": 1}}},
            {"section_id": "s2", "title": "Data", "order": 2,
             "heading_block_id": "p2-b01", "level": 1,
             "summary": {"anchor": {"locator": "s2 p.2", "section_id": "s2", "page": 2}}},
            {"section_id": "s3", "title": "Results", "order": 3,
             "heading_block_id": "p3-b01", "level": 1,
             "summary": {"anchor": {"locator": "s3 p.3", "section_id": "s3", "page": 3}}},
        ],
        "paper_card": {
            "research_question": {
                "status": "reported", "value": "Whether X affects Y.",
                "anchor": {"locator": "s1 ¶2 p.1", "section_id": "s1", "page": 1,
                           "block_id": "p1-b02", "quote": "whether X affects Y"},
            },
            "data": {"status": "reported", "value": "100 firms",
                     "anchor": {"locator": "s2 p.2", "section_id": "s2", "page": 2,
                                "block_id": "p2-b01", "quote": "100 firms"}},
            "method": {"status": "reported", "value": "OLS regression",
                       "anchor": {"locator": "s2 p.2", "section_id": "s2", "page": 2}},
            "findings": {
                "status": "reported",
                "items": [{"finding_id": "f1", "statement": "X increases Y by 0.5.",
                           "condition_ids": ["c1"],
                           "anchor": {"locator": "s3 p.3", "section_id": "s3", "page": 3,
                                      "block_id": "p3-b01", "quote": "X increases Y"}}],
            },
            "conditions": {"status": "reported", "value": "Holds for firms.",
                           "items": [{"condition_id": "c1", "premise": "sample is firms",
                                      "applies_to": ["f1"],
                                      "anchor": {"locator": "s2 p.2", "section_id": "s2",
                                                 "page": 2}}]},
            "limitations": {"status": "not_reported"},
        },
        "knowledge_points": [
            {"kp_id": "kp1", "term": "NaCl", "canonical": "sodium chloride",
             "type": "concept", "definition": "a salt",
             "abbreviations": ["NaCl"],
             "anchor": {"locator": "s1 p.1", "section_id": "s1", "page": 1}},
            {"kp_id": "kp2", "term": "NaCl", "canonical": "sodium chloride",
             "type": "concept", "definition": "a salt used in the experiment",
             "anchor": {"locator": "s2 p.2", "section_id": "s2", "page": 2}},
            {"kp_id": "kp3", "term": "NaCl", "type": "abbreviation",
             "definition": "sodium chloride",
             "anchor": {"locator": "s1 p.1", "section_id": "s1", "page": 1}},
        ],
    }

    # 1) 对得上：对齐检查应通过
    rep = section_alignment_check(notes["sections"], source)
    assert rep["aligned"] is True, rep
    assert rep["coverage"] == 1.0, rep

    # 2) 留得住：字段检查应通过
    rep2 = check_fields(notes["paper_card"])
    assert rep2["complete"] is True, rep2

    # 3) 找得回：锚点应通过
    probs = check_anchors(notes, source)
    assert all(p["ok"] for p in probs), probs

    # 4) 用得上：kp1/kp2 定义兼容应合并；kp3 缩写应链到 concept
    rep3 = dedupe_knowledge_points(notes["knowledge_points"])
    kept_ids = {k.get("kp_id") for k in rep3["report"]}
    assert "kp3" in kept_ids, rep3
    kept_concept = [k for k in rep3["report"] if "merged_from" in k]
    assert len(kept_concept) == 1, rep3
    assert kept_concept[0]["merged_from"] in (["kp1"], ["kp2"]), rep3
    assert rep3["conflicts"] == [], rep3
    links = resolve_abbreviations(notes["knowledge_points"])
    assert any(l["abbreviation"] == "kp3" for l in links), links

    # 反例：锚点引文错误 / 页码越界应被检出
    bad_notes = json.loads(json.dumps(notes))
    bad_notes["paper_card"]["findings"]["items"][0]["anchor"]["quote"] = "not in text"
    probs2 = check_anchors(bad_notes, source)
    finding_probs = [p for p in probs2 if p["path"].startswith("paper_card.findings")]
    assert finding_probs and any(pr.get("error") == "quote_not_found"
                                 for pr in finding_probs[0]["problems"]), probs2

    bad_anchor = {"locator": "x", "section_id": "s1", "page": 99,
                  "quote": "whatever"}
    pa = validate_anchor(bad_anchor, source)
    assert any(p.get("error") == "page_out_of_range" for p in pa), pa

    # 反例：漏掉 Results 章节 → 对不上被检出
    partial_notes = json.loads(json.dumps(notes))
    partial_notes["sections"] = partial_notes["sections"][:2]
    rep4 = section_alignment_check(partial_notes["sections"], source)
    assert rep4["aligned"] is False and rep4["missing_sections"], rep4

    # 反例：套用通用模板多出「Methodology」章节（原文没有）→ extra_section
    tmpl_notes = json.loads(json.dumps(notes))
    tmpl_notes["sections"].append({"section_id": "sx", "title": "Methodology",
                                   "order": 4, "heading_block_id": None})
    rep5 = section_alignment_check(tmpl_notes["sections"], source)
    assert rep5["aligned"] is False and rep5["extra_section"], rep5

    # 归一化与引文匹配
    assert normalize_term("  Sodium  Chloride (NaCl) ") == "sodium chloride (nacl)"
    assert contains_quote("X   increases\nY", "X increases Y") is True
    assert contains_quote("X increases Y", "x increases y") is False  # 大小写敏感

    # 冲突检测：同名同型但定义互不包含
    conflict_kps = [
        {"kp_id": "a", "term": "alpha", "type": "variable",
         "definition": "the intercept", "anchor": None},
        {"kp_id": "b", "term": "alpha", "type": "variable",
         "definition": "the slope coefficient", "anchor": None},
    ]
    rep6 = dedupe_knowledge_points(conflict_kps)
    assert rep6["conflicts"] and rep6["conflicts"][0]["term"] == "alpha", rep6

    print("self-test: OK")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    return path


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(prog="notes.py",
                                description="structured-paper-notes 机械校验工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("self-test", help="运行内置自测")

    sp = sub.add_parser("extract-fields", help="章节标题→卡片字段启发式映射")
    sp.add_argument("--source", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("check-sections", help="章节骨架对齐检查（对得上）")
    sp.add_argument("--notes", required=True)
    sp.add_argument("--source", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("check-fields", help="论文卡片字段完整性检查（留得住）")
    sp.add_argument("--notes", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("check-anchors", help="笔记锚点回链校验（找得回）")
    sp.add_argument("--notes", required=True)
    sp.add_argument("--source", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("dedupe-kps", help="知识点去重与冲突检测（用得上）")
    sp.add_argument("--notes", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("build-result", help="组装 result.json")
    sp.add_argument("--notes", required=True)
    sp.add_argument("--case-id", required=True)
    sp.add_argument("--out", required=True)

    args = p.parse_args(argv)

    if args.cmd == "self-test":
        return self_test()
    if args.cmd == "extract-fields":
        source = _load(args.source)
        _dump(args.out, extract_fields(source))
    elif args.cmd == "check-sections":
        notes = _load(args.notes)
        source = _load(args.source)
        _dump(args.out, section_alignment_check(notes.get("sections", []), source))
    elif args.cmd == "check-fields":
        notes = _load(args.notes)
        card = notes.get("paper_card", {})
        _dump(args.out, check_fields(card))
    elif args.cmd == "check-anchors":
        notes = _load(args.notes)
        source = _load(args.source)
        _dump(args.out, check_anchors(notes, source))
    elif args.cmd == "dedupe-kps":
        notes = _load(args.notes)
        kps = notes.get("knowledge_points", [])
        rep = dedupe_knowledge_points(kps)
        rep["abbreviation_links"] = resolve_abbreviations(kps)
        _dump(args.out, rep)
    elif args.cmd == "build-result":
        notes = _load(args.notes)
        _dump(args.out, build_result(notes, args.case_id))
    print("%s: wrote %s" % (args.cmd, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
