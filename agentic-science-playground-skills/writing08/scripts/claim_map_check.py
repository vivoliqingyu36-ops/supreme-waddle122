#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_map_check.py — 引言与相关工作 Skill 的结构校验脚本（仅标准库）。

校验 source_map.json（可选 result.json）是否符合 intro-related-work-writer 的
claim→来源、贡献→证据、gap 推导链与引用键集合约束。

退出码:
  0 = 通过（无硬错误；可能有警告）
  1 = 有警告（unverified / author_judgment / uncited / evidence_status=missing / no_basis 等）
  2 = 硬错误（缺必填、claim 无来源、citation_key 未定义、gap 类型非法或依据不足、
      贡献 verified 却无证据、重复 id 等）

用法:
  python3 claim_map_check.py --source-map source_map.json [--references refs.json] [--result result.json]
"""
import argparse
import json
import re
import sys

CLAIM_TYPES = {
    "background_lineage", "background_problem", "prior_work_claim",
    "gap_premise", "gap_statement", "contribution", "fill_relation", "fact",
}
STATUSES = {"cited", "unverified", "author_judgment", "conflict"}
GAP_TYPES = {"shared_limitation", "uncovered_scenario", "conflicting_conclusion", "no_basis"}
EVIDENCE_STATUSES = {"verified", "missing"}
OVERCLAIM_RISKS = {"none", "soften", "drop"}

errors = []    # 硬错误
warnings = []  # 警告


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        err(f"{what}: 文件不存在: {path}")
        return None
    except json.JSONDecodeError as e:
        err(f"{what}: JSON 解析失败 {path}: {e}")
        return None
    if not isinstance(data, dict):
        err(f"{what}: 顶层必须是对象: {path}")
        return None
    return data


def check_source_map(sm, refs_override):
    if "case_id" not in sm or not isinstance(sm.get("case_id"), str) or not sm["case_id"].strip():
        err("source_map 缺少非空 case_id")

    # ---- references ----
    refs = refs_override if refs_override is not None else sm.get("references")
    if not isinstance(refs, list) or len(refs) == 0:
        warn("references 为空：引用核验无法进行；请确认是否属于「文献库为空」异常")
        refs = []
    defined_keys = set()
    seen_ref_keys = set()
    for i, r in enumerate(refs):
        if not isinstance(r, dict):
            err(f"references[{i}] 不是对象")
            continue
        k = r.get("key")
        if not isinstance(k, str) or not k.strip():
            err(f"references[{i}] 缺少非空 key")
            continue
        if k in seen_ref_keys:
            err(f"references 键重复: {k}")
        seen_ref_keys.add(k)
        defined_keys.add(k)

    # ---- claims ----
    claims = sm.get("claims")
    if not isinstance(claims, list):
        err("缺少 claims 数组")
        claims = []
    seen_claim_ids = set()
    cited_keys = set()
    author_judgment_ids = set()
    unverified_count = 0
    for i, c in enumerate(claims):
        loc = f"claims[{i}]"
        if not isinstance(c, dict):
            err(f"{loc} 不是对象")
            continue
        cid = c.get("claim_id")
        if not isinstance(cid, str) or not re.fullmatch(r"c[0-9]+", cid):
            err(f"{loc}: claim_id 必须形如 c01, 实际: {cid!r}")
        else:
            if cid in seen_claim_ids:
                err(f"{loc}: claim_id 重复: {cid}")
            seen_claim_ids.add(cid)
        if not isinstance(c.get("claim_text"), str) or not c["claim_text"].strip():
            err(f"{loc}: 缺少非空 claim_text")
        ct = c.get("claim_type")
        if ct not in CLAIM_TYPES:
            err(f"{loc}: claim_type 非法: {ct!r}; 允许 {sorted(CLAIM_TYPES)}")
        src = c.get("source")
        if not isinstance(src, dict):
            err(f"{loc}: 缺少 source（引用键/文件定位/作者判断 三选一）")
        else:
            kinds = [k for k in ("citation_key", "evidence_loc", "author_judgment") if k in src]
            if len(kinds) != 1:
                err(f"{loc}: source 必须且只能含 citation_key/evidence_loc/author_judgment 之一, 实际: {kinds}")
            else:
                kind = kinds[0]
                if kind == "citation_key":
                    ck = src["citation_key"]
                    if not isinstance(ck, str) or not ck.strip():
                        err(f"{loc}: citation_key 为空")
                    else:
                        if ck not in defined_keys:
                            err(f"{loc}: citation_key {ck!r} 未在 references 中定义")
                        cited_keys.add(ck)
                elif kind == "evidence_loc":
                    if not isinstance(src["evidence_loc"], str) or not src["evidence_loc"].strip():
                        err(f"{loc}: evidence_loc 为空")
                else:  # author_judgment
                    if src.get("author_judgment") is not True or not isinstance(src.get("reason"), str) or not src["reason"].strip():
                        err(f"{loc}: author_judgment 必须为 true 且给出非空 reason")
                    else:
                        author_judgment_ids.add(cid)
        st = c.get("status")
        if st not in STATUSES:
            err(f"{loc}: status 非法: {st!r}; 允许 {sorted(STATUSES)}")
        elif st == "author_judgment":
            author_judgment_ids.add(cid)
        elif st == "unverified":
            unverified_count += 1

    # ---- contributions ----
    contributions = sm.get("contributions")
    if not isinstance(contributions, list):
        err("缺少 contributions 数组")
        contributions = []
    seen_contrib_ids = set()
    for i, g in enumerate(contributions):
        loc = f"contributions[{i}]"
        if not isinstance(g, dict):
            err(f"{loc} 不是对象")
            continue
        gid = g.get("contribution_id")
        if not isinstance(gid, str) or not re.fullmatch(r"g[0-9]+", gid):
            err(f"{loc}: contribution_id 必须形如 g1, 实际: {gid!r}")
        else:
            if gid in seen_contrib_ids:
                err(f"{loc}: contribution_id 重复: {gid}")
            seen_contrib_ids.add(gid)
        if not isinstance(g.get("contribution_text"), str) or not g["contribution_text"].strip():
            err(f"{loc}: 缺少非空 contribution_text")
        ev = g.get("evidence")
        if not isinstance(ev, list):
            err(f"{loc}: evidence 必须是数组")
            ev = []
        es = g.get("evidence_status")
        if es not in EVIDENCE_STATUSES:
            err(f"{loc}: evidence_status 非法: {es!r}; 允许 {sorted(EVIDENCE_STATUSES)}")
        elif es == "verified" and len(ev) == 0:
            err(f"{loc}: evidence_status=verified 但 evidence 为空")
        elif es == "missing":
            warn(f"{loc}: evidence_status=missing; 贡献应已降级为「计划/假设」或删除")
        if g.get("overclaim_risk") not in OVERCLAIM_RISKS and g.get("overclaim_risk") is not None:
            err(f"{loc}: overclaim_risk 非法: {g.get('overclaim_risk')!r}")

    # ---- gaps ----
    gaps = sm.get("gaps")
    if not isinstance(gaps, list):
        err("缺少 gaps 数组")
        gaps = []
    seen_gap_ids = set()
    for i, gp in enumerate(gaps):
        loc = f"gaps[{i}]"
        if not isinstance(gp, dict):
            err(f"{loc} 不是对象")
            continue
        gid = gp.get("gap_id")
        if not isinstance(gid, str) or not re.fullmatch(r"g[0-9]+", gid):
            err(f"{loc}: gap_id 必须形如 g1, 实际: {gid!r}")
        else:
            if gid in seen_gap_ids:
                err(f"{loc}: gap_id 重复: {gid}")
            seen_gap_ids.add(gid)
        gt = gp.get("gap_type")
        if gt not in GAP_TYPES:
            err(f"{loc}: gap_type 非法: {gt!r}; 允许 {sorted(GAP_TYPES)}")
        if not isinstance(gp.get("this_paper_fill"), str) or not gp["this_paper_fill"].strip():
            err(f"{loc}: 缺少非空 this_paper_fill")
        bw = gp.get("basis_works")
        if not isinstance(bw, list):
            bw = []
        for k in bw:
            if not isinstance(k, str):
                err(f"{loc}: basis_works 元素必须是字符串")
            elif k not in defined_keys:
                err(f"{loc}: basis_work {k!r} 未在 references 中定义")
            else:
                cited_keys.add(k)
        if gt == "shared_limitation" and len(bw) < 2:
            err(f"{loc}: shared_limitation 需要 ≥2 篇依据文献, 实际 {len(bw)}")
        if gt == "conflicting_conclusion" and len(bw) < 2:
            err(f"{loc}: conflicting_conclusion 需要 ≥2 篇依据文献, 实际 {len(bw)}")
        if gt == "uncovered_scenario" and len(bw) < 1:
            err(f"{loc}: uncovered_scenario 需要 ≥1 篇依据文献说明覆盖范围")
        if gt == "no_basis" and len(bw) > 0:
            warn(f"{loc}: no_basis 不应挂依据文献, 实际 {len(bw)}; 请确认已标作者判断")

    # ---- related_work ----
    rw = sm.get("related_work")
    if not isinstance(rw, list):
        err("缺少 related_work 数组")
        rw = []
    seen_work_keys = set()
    for i, row in enumerate(rw):
        loc = f"related_work[{i}]"
        if not isinstance(row, dict):
            err(f"{loc} 不是对象")
            continue
        wk = row.get("work_key")
        if not isinstance(wk, str) or not wk.strip():
            err(f"{loc}: 缺少 work_key")
        else:
            if wk in seen_work_keys:
                err(f"{loc}: work_key 重复: {wk}")
            seen_work_keys.add(wk)
        for field in ("problem_setting", "method_route", "data_eval"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                err(f"{loc}: 缺少 {field}")

    # ---- 交叉核对 ----
    uncited = sorted(defined_keys - cited_keys)
    if uncited:
        warn(f"references 中未被任何 claim/gap 引用的键: {', '.join(uncited)}")
    if author_judgment_ids:
        warn(f"存在 {len(author_judgment_ids)} 条作者判断 claim: {', '.join(sorted(author_judgment_ids))}")
    if unverified_count:
        warn(f"存在 {unverified_count} 条 status=unverified 的 claim")


def check_result(res):
    if "case_id" not in res or not isinstance(res.get("case_id"), str) or not res["case_id"].strip():
        err("result.json 缺少非空 case_id")
    if res.get("status") not in {"success", "partial", "failed"}:
        err(f"result.json status 非法: {res.get('status')!r}")
    if "output_contract" not in res or not isinstance(res.get("output_contract"), dict):
        err("result.json 缺少 output_contract 对象（必须包含题面要求的全部字段）")


def main():
    ap = argparse.ArgumentParser(description="校验 intro-related-work-writer 的 source_map.json / result.json")
    ap.add_argument("--source-map", required=True, help="source_map.json 路径")
    ap.add_argument("--references", default=None, help="可选：独立 references.json；缺省用 source_map 内 references")
    ap.add_argument("--result", default=None, help="可选：result.json 路径，做顶层完整性校验")
    args = ap.parse_args()

    sm = load_json(args.source_map, "source_map")
    if sm is None:
        print("\n".join(errors))
        sys.exit(2)

    refs_override = None
    if args.references:
        refs_override = load_json(args.references, "references")
        if refs_override is None:
            print("\n".join(errors))
            sys.exit(2)

    check_source_map(sm, refs_override)

    if args.result:
        res = load_json(args.result, "result")
        if res is None:
            print("\n".join(errors))
            sys.exit(2)
        check_result(res)

    print(f"校验完成: errors={len(errors)}, warnings={len(warnings)}")
    if errors:
        print("--- 硬错误 (exit 2) ---")
        for e in errors:
            print("  [E] " + e)
    if warnings:
        print("--- 警告 (exit 1) ---")
        for w in warnings:
            print("  [W] " + w)

    if errors:
        sys.exit(2)
    if warnings:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
