#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ppt_outline.py — paper -> academic PPT: page-level outline + evidence map + deck-contract validator.

Pure Python standard library. Runnable, not a stub.

Purpose
-------
Turn an extracted "paper skeleton" (problem -> method -> key evidence -> conclusion,
each claim carrying a source locator and an evidence index) into a page-level slide
outline where:
  * one page carries exactly one claim,
  * every figure/table/formula/data citation carries a source locator,
  * the slide count respects a hard limit,
  * numbers/units are kept verbatim,
  * schematics are never presented as measured data,
  * third-party results are never attributed to the paper.

This script does NOT parse the PDF and does NOT render PPTX. Those are done by the
platform tools (pdf-text-tool / pdf-render-tool / ocr-tool) and by the deck builder
(python-pptx / libreoffice / office-renderer) at run time, guided by SKILL.md. This
script is the deterministic post-processing + contract gate between extraction and
deck building.

Commands
--------
  build      paper_skeleton.json -> slide_outline.json (allocates pages, binds evidence,
             validates the deck contract, embeds the contract report).
  validate   slide_outline.json -> re-run the contract checks; exits non-zero on errors.
  demo       write a synthetic paper_skeleton demonstrating every contract rule.
  self-test  exercise the validator on pass and fail cases; exit non-zero if any fail.

Exit codes: 0 = contract holds (or self-test passed); 2 = usage error; 3 = contract
violation (errors present); 4 = missing/bad input.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys

SCHEMA_VERSION = "1.0"
MAX_CLAIM_CHARS = 160
MAX_BULLET_CHARS = 120
DEFAULT_MAX_BULLETS = 6
DEFAULT_BODY_BUDGET = 600
DEFAULT_SLIDE_LIMIT = 20

# Figure/table/formula/data id, e.g. fig:2, tab:1, formula:3, data:s1.
EVIDENCE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]*(:[A-Za-z0-9_\-]+)?$")
NUMBER_RE = re.compile(r"[0-9]")

# Canonical speakable narrative order. "evidence:ID" stands for any evidence slide.
CANONICAL_ROLE_ORDER = {
    "title": 0,
    "problem": 1,
    "gap": 2,
    "method": 3,
    "evidence": 4,
    "conclusion": 5,
    "limitations": 6,
    "backup": 7,
    "thanks": 8,
}
REQUIRED_ROLES = ("title", "problem", "method", "conclusion")
NOTES_OPTIONAL_ROLES = ("title", "thanks")

# Roles where the single claim is mandatory and must not be a bare sentence stack.
DATA_USE_ROLES = ("evidence", "conclusion")

# Attribution markers that must appear in notes when a cited/other item is shown.
ATTRIBUTION_MARKERS = (
    "先前", "他人", "此前", "已有", "据文献", "引用", "已有报道", "前人",
    "previously", "prior work", "prior", "others", "reported in", "ref.",
)

VALID_USE = ("data", "context", "reference")
VALID_KIND = ("figure", "table", "formula", "data")
VALID_ROLE = ("data", "schematic", "illustration", "formula", "derivation")
VALID_OWNER = ("paper", "cited", "other")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _err(msg: str):
    print(f"[ERROR] {msg}", file=sys.stderr)


def _warn(msg: str):
    print(f"[WARN]  {msg}", file=sys.stderr)


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level value must be an object, got {type(data).__name__}")
    return data


def write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def locator_ok(loc) -> bool:
    """A locator is usable when it exists and pins at least one anchor."""
    if not isinstance(loc, dict):
        return False
    for key in ("file", "page", "section", "where", "bbox"):
        if loc.get(key) not in (None, "", []):
            return True
    return False


def norm_role(role: str) -> str:
    """Map 'evidence:ev1' -> 'evidence' for ordering purposes."""
    return role.split(":", 1)[0]


def sentence_count(text: str) -> int:
    parts = [p for p in re.split(r"(?<=[.!?。！？])\s+", text.strip()) if p.strip()]
    return max(1, len(parts))


# --------------------------------------------------------------------------- #
# contract checks — each returns (ok: bool, errors: list[str], warnings: list[str])
# --------------------------------------------------------------------------- #
def check_one_claim(slide: dict) -> tuple[bool, list, list]:
    errors, warnings = [], []
    claim = slide.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        return False, [f"slide {slide.get('index')}: claim missing or empty"], warnings
    claim = claim.strip()
    if len(claim) > MAX_CLAIM_CHARS:
        errors.append(f"slide {slide.get('index')}: claim {len(claim)} chars > {MAX_CLAIM_CHARS}")
    if sentence_count(claim) > 2:
        warnings.append(f"slide {slide.get('index')}: claim has >1 sentence; fold the rest into bullets")

    bullets = slide.get("bullets")
    if not isinstance(bullets, list):
        return False, [f"slide {slide.get('index')}: bullets must be a list"], warnings
    if len(bullets) > DEFAULT_MAX_BULLETS:
        errors.append(f"slide {slide.get('index')}: {len(bullets)} bullets > {DEFAULT_MAX_BULLETS}")
    for i, b in enumerate(bullets):
        if not isinstance(b, str) or not b.strip():
            errors.append(f"slide {slide.get('index')}: empty bullet at position {i}")
            continue
        if len(b) > MAX_BULLET_CHARS:
            errors.append(f"slide {slide.get('index')}: bullet {i} {len(b)} chars > {MAX_BULLET_CHARS}")
        if b.rstrip().endswith("."):
            warnings.append(f"slide {slide.get('index')}: bullet {i} ends with '.' (phrase style preferred)")

    body_chars = len(claim) + sum(len(b) for b in bullets)
    if body_chars > DEFAULT_BODY_BUDGET:
        warnings.append(f"slide {slide.get('index')}: body {body_chars} chars > {DEFAULT_BODY_BUDGET} (density)")
    return (len(errors) == 0), errors, warnings


def check_refs_located(slide: dict, index_by_id: dict) -> tuple[bool, list, list]:
    errors, warnings = [], []
    for ev in slide.get("evidence", []):
        if not isinstance(ev, dict):
            errors.append(f"slide {slide.get('index')}: evidence entry not an object")
            continue
        ref = ev.get("ref")
        if not isinstance(ref, str) or not ref.strip():
            errors.append(f"slide {slide.get('index')}: evidence entry missing ref")
            continue
        if not EVIDENCE_ID_RE.match(ref):
            errors.append(f"slide {slide.get('index')}: bad evidence id {ref!r}")
        if ref not in index_by_id:
            errors.append(f"slide {slide.get('index')}: ref {ref!r} not in evidence_index")
            continue
        item = index_by_id[ref]
        if ev.get("use") not in VALID_USE:
            errors.append(f"slide {slide.get('index')}: ref {ref} bad use {ev.get('use')!r}")
        # every citation must carry a locator: inline on the binding or inherited from the index
        if not locator_ok(ev.get("locator")) and not locator_ok(item.get("locator")):
            errors.append(f"slide {slide.get('index')}: ref {ref} has no source locator")
        # figure/table label must not be altered
        lbl = ev.get("label")
        if lbl is not None and lbl != item.get("label"):
            errors.append(f"slide {slide.get('index')}: ref {ref} label {lbl!r} != index label {item.get('label')!r}")
    return (len(errors) == 0), errors, warnings


def check_no_schematic_as_data(slide: dict, index_by_id: dict) -> tuple[bool, list, list]:
    errors = []
    for ev in slide.get("evidence", []):
        ref = ev.get("ref")
        item = index_by_id.get(ref)
        if not item:
            continue
        is_schematic = item.get("kind") == "figure" and item.get("role") in ("schematic", "illustration")
        if is_schematic and ev.get("use") == "data":
            errors.append(f"slide {slide.get('index')}: schematic {ref} ({item.get('label')}) presented as data")
    return (len(errors) == 0), errors, []


def check_no_other_attribution(slide: dict, index_by_id: dict) -> tuple[bool, list, list]:
    errors = []
    notes = (slide.get("notes") or "").strip()
    for ev in slide.get("evidence", []):
        ref = ev.get("ref")
        item = index_by_id.get(ref)
        if not item:
            continue
        if item.get("owner") in ("cited", "other"):
            if ev.get("use") != "reference":
                errors.append(
                    f"slide {slide.get('index')}: third-party {ref} ({item.get('label')}) "
                    f"used as {ev.get('use')!r}, must be 'reference'"
                )
            if not any(m.lower() in notes.lower() for m in ATTRIBUTION_MARKERS):
                errors.append(
                    f"slide {slide.get('index')}: third-party {ref} shown but notes lack "
                    f"attribution marker (先前/他人/prior work/据文献/...)"
                )
    return (len(errors) == 0), errors, []


def check_data_verbatim(slide: dict, index_by_id: dict) -> tuple[bool, list, list]:
    errors = []
    for dv in slide.get("data_verbatim", []):
        if not isinstance(dv, dict):
            errors.append(f"slide {slide.get('index')}: data_verbatim entry not an object")
            continue
        val = dv.get("value")
        if not isinstance(val, str) or not NUMBER_RE.search(val):
            errors.append(f"slide {slide.get('index')}: data_verbatim value not number-like: {val!r}")
        unit = dv.get("unit")
        if unit is None and not dv.get("unit_absent"):
            errors.append(f"slide {slide.get('index')}: data_verbatim {val!r} has null unit but unit_absent not set")
        if not locator_ok(dv.get("locator")):
            errors.append(f"slide {slide.get('index')}: data_verbatim {val!r} has no locator")
        # never alter numbers/units: if it links a source, value must match the source exactly
        ref = dv.get("ref")
        if ref and ref in index_by_id:
            src_vals = [dp.get("value") for dp in (index_by_id[ref].get("data_points") or []) if dp.get("value")]
            if src_vals and val not in src_vals:
                errors.append(
                    f"slide {slide.get('index')}: value {val!r} not verbatim; source {ref} has {src_vals}"
                )
    return (len(errors) == 0), errors, []


def check_notes_non_verbatim(slide: dict) -> tuple[bool, list, list]:
    notes = (slide.get("notes") or "").strip()
    role = slide.get("role")
    if not notes:
        if role in NOTES_OPTIONAL_ROLES:
            return True, [], []
        return False, [f"slide {slide.get('index')}: notes missing (required for {role})"], []
    body = [slide.get("claim", "")] + list(slide.get("bullets", []))
    for b in body:
        b = (b or "").strip()
        if len(b) >= 8 and b in notes:
            return False, [f"slide {slide.get('index')}: notes repeat slide text verbatim: {b[:40]}..."], []
    return True, [], []


def check_coverage(outline: dict) -> tuple[bool, list, list]:
    errors, warnings = [], []
    used = set()
    for s in outline.get("slides", []):
        for ev in s.get("evidence", []):
            if isinstance(ev.get("ref"), str):
                used.add(ev["ref"])
    index_ids = [e.get("id") for e in outline.get("evidence_index", []) if isinstance(e.get("id"), str)]
    map_status = {m.get("ref"): m for m in outline.get("evidence_map", []) if isinstance(m.get("ref"), str)}
    for eid in index_ids:
        if eid not in used:
            st = (map_status.get(eid) or {}).get("status")
            if st != "unused":
                warnings.append(f"evidence {eid} never used and not marked 'unused' in evidence_map")
        else:
            st = (map_status.get(eid) or {}).get("status")
            if st not in ("used", None):
                errors.append(f"evidence {eid} used on slides but evidence_map status={st!r}")
    return (len(errors) == 0), errors, warnings


def check_narrative_order(outline: dict) -> tuple[bool, list, list]:
    errors, warnings = [], []
    seen = [norm_role(s.get("role", "")) for s in outline.get("slides", [])]
    order = [CANONICAL_ROLE_ORDER.get(r, 99) for r in seen]
    if order != sorted(order):
        warnings.append(f"slide roles out of canonical order: {seen}")
    missing = [r for r in REQUIRED_ROLES if r not in seen]
    if missing:
        errors.append(f"missing required mainline pages: {missing}")
    # conclusion must come after at least one evidence page (unless there is no evidence)
    if "evidence" in seen and "conclusion" in seen:
        if order[seen.index("evidence")] > order[seen.index("conclusion")]:
            errors.append("conclusion placed before evidence page(s)")
    return (len(errors) == 0), errors, warnings


# --------------------------------------------------------------------------- #
# validation driver
# --------------------------------------------------------------------------- #
def validate(outline: dict, limit: int | None = None) -> tuple[bool, dict]:
    """Run all contract checks, write the report into outline['contract']."""
    slides = outline.get("slides", [])
    if not isinstance(slides, list):
        slides = []
    index = {e.get("id"): e for e in outline.get("evidence_index", []) if isinstance(e.get("id"), str)}
    lim = int(limit or (outline.get("contract") or {}).get("slide_limit") or DEFAULT_SLIDE_LIMIT)

    errors: list[str] = []
    warnings: list[str] = []
    check_flags: dict[str, bool] = {}

    def run(name, ok, errs, warns):
        check_flags[name] = ok
        errors.extend(errs)
        warnings.extend(warns)

    if len(slides) > lim:
        errors.append(f"slide count {len(slides)} > limit {lim}")
    if len(slides) == 0:
        errors.append("no slides")
    check_flags["count_within_limit"] = len(slides) <= lim

    for s in slides:
        if not isinstance(s, dict):
            errors.append("slide entry not an object")
            continue
        run("one_claim_per_page", *check_one_claim(s))
        run("all_refs_located", *check_refs_located(s, index))
        run("no_schematic_as_data", *check_no_schematic_as_data(s, index))
        run("no_other_attribution", *check_no_other_attribution(s, index))
        run("data_verbatim_ok", *check_data_verbatim(s, index))
        run("notes_non_verbatim", *check_notes_non_verbatim(s))

    run("coverage_complete", *check_coverage(outline))
    run("narrative_order_ok", *check_narrative_order(outline))

    # If a check was never exercised because there was nothing to check, default True.
    for name in ("one_claim_per_page", "all_refs_located", "no_schematic_as_data",
                 "no_other_attribution", "data_verbatim_ok", "notes_non_verbatim",
                 "coverage_complete", "narrative_order_ok"):
        check_flags.setdefault(name, True)

    outline["contract"] = {
        "slide_limit": lim,
        "slide_count": len(slides),
        "checks": check_flags,
        "errors": errors,
        "warnings": warnings,
    }
    return (len(errors) == 0), outline


# --------------------------------------------------------------------------- #
# build: paper skeleton -> slide outline
# --------------------------------------------------------------------------- #
def _copy_locator(dst: dict, item: dict) -> None:
    if not locator_ok(dst.get("locator")) and locator_ok(item.get("locator")):
        dst["locator"] = copy.deepcopy(item.get("locator"))


def _make_binding(item: dict) -> dict:
    """Choose use based on kind/role/owner so the contract rules hold by construction."""
    owner = item.get("owner", "paper")
    kind = item.get("kind")
    role = item.get("role")
    if owner in ("cited", "other"):
        use = "reference"
    elif kind == "figure" and role in ("schematic", "illustration"):
        use = "context"
    elif kind == "table":
        use = "data"
    elif kind == "data":
        use = "data"
    elif kind == "formula":
        use = "context"
    elif kind == "figure" and role == "data":
        use = "data"
    else:
        use = "context"
    return {
        "ref": item.get("id"),
        "use": use,
        "label": item.get("label"),
        "caption_note": None,
        "locator": copy.deepcopy(item.get("locator")) if locator_ok(item.get("locator")) else None,
    }


def _data_verbatim_for(ref: str, item: dict) -> list:
    out = []
    for dp in item.get("data_points") or []:
        out.append({
            "ref": ref,
            "value": dp.get("value"),
            "unit": dp.get("unit"),
            "unit_absent": bool(dp.get("unit_absent")) if dp.get("unit") is None else False,
            "condition": dp.get("condition"),
            "locator": copy.deepcopy(dp.get("locator")) if locator_ok(dp.get("locator"))
                       else copy.deepcopy(item.get("locator")),
        })
    return out


def _stub_note(role: str) -> str:
    """Role-based speaker-note scaffold. Never contains slide text, so it can't repeat
    the claim/bullets verbatim. The runtime agent MUST replace every stub with a real
    transition/emphasis/backup note before finalizing (see SKILL.md step 7)."""
    stubs = {
        "title": "Frame the talk in one line: venue, audience, and why this problem matters now.",
        "problem": "Open with the question the audience should care about. State why it matters and what is at stake.",
        "gap": "Bridge to what is missing. Name the gap concretely so the method reads as the natural answer.",
        "method": "Walk through the core idea once, slowly. Point to the schematic/formula; do not dump equations.",
        "evidence": "Lead with the number the figure/table shows. State the condition (n, seeds, units) before the number. Flag axes and error bars.",
        "conclusion": "Restate the take-home in one sentence and tie it back to the problem. Do not re-list every result.",
        "limitations": "Name the honest boundary: what is assumed, what is not claimed, and what remains open.",
        "backup": "One line per result. Expand only if asked; keep the main talk on the mainline.",
        "thanks": "Open the floor for questions; list backup slides available on request.",
    }
    return stubs.get(role, "Transition, emphasis, and backup evidence for this page.")


def _layout_for(slide: dict, template: dict | None) -> dict:
    """Pick a template layout that fits the page and map placeholders."""
    if template:
        layouts = template.get("layouts") or {}
    else:
        layouts = None
    role = slide.get("role")
    has_figure = any(isinstance(e, dict) and e.get("ref", "").startswith("fig:") for e in slide.get("evidence", []))
    has_table = any(isinstance(e, dict) and e.get("ref", "").startswith("tab:") for e in slide.get("evidence", []))

    if role == "title":
        preferred = ["Title Slide", "Title Only"]
        pmap = {"title": "title", "subtitle": "subtitle"}
    elif role in ("evidence", "backup") and has_figure:
        preferred = ["Picture with Caption", "Title and Content"]
        pmap = {"title": "title", "figure": "picture", "body": "content"}
    elif has_table:
        preferred = ["Title and Content", "Title Only"]
        pmap = {"title": "title", "table": "content"}
    else:
        preferred = ["Title and Content", "Title Only"]
        pmap = {"title": "title", "body": "content"}

    layout_name = None
    if layouts:
        for cand in preferred:
            if cand in layouts:
                layout_name = cand
                break
        if layout_name is None and layouts:
            layout_name = sorted(layouts)[0]
    else:
        layout_name = preferred[0]

    return {
        "layout_name": layout_name,
        "title": slide.get("claim"),
        "placeholder_map": pmap,
        "overflow_plan": None,
    }


def build(skeleton: dict, limit: int, template: dict | None = None) -> dict:
    paper_id = skeleton.get("paper_id", "unknown")
    meta = skeleton.get("meta", {})
    mainline = skeleton.get("mainline", {})
    index_items = skeleton.get("evidence_index", [])
    index_by_id = {e.get("id"): e for e in index_items if isinstance(e.get("id"), str)}

    # Validate that every key_evidence ref exists (fail fast, no silent drop).
    missing_refs = []
    for ke in mainline.get("key_evidence", []):
        for ref in ke.get("refs", []):
            if ref not in index_by_id:
                missing_refs.append(f"key_evidence {ke.get('id')} refs unknown evidence {ref!r}")
    if missing_refs:
        raise ValueError("; ".join(missing_refs))

    slides: list[dict] = []
    idx = 0

    def add(role, claim, *, bullets=None, evidence=None, data_verbatim=None, notes=None, locator=None):
        nonlocal idx
        idx += 1
        slides.append({
            "index": idx,
            "role": role,
            "claim": claim or "",
            "bullets": bullets or [],
            "evidence": evidence or [],
            "data_verbatim": data_verbatim or [],
            "notes": notes if notes is not None else _stub_note(role),
            "layout": {},
            "uncertainty": [],
            "_locator": locator or {},
        })

    # 1) title
    add("title", meta.get("title", ""))

    # 2) problem
    prob = mainline.get("problem") or {}
    add("problem", prob.get("claim", ""), locator=prob.get("locator"))

    # 3) gap (optional but almost always present)
    gap = mainline.get("gap") or {}
    if gap.get("claim"):
        add("gap", gap.get("claim"), locator=gap.get("locator"))

    # 4) method
    meth = mainline.get("method") or {}
    method_ev = []
    for ref in meth.get("refs", []):
        item = index_by_id.get(ref)
        if item:
            method_ev.append(_make_binding(item))
    add("method", meth.get("claim", ""), evidence=method_ev, locator=meth.get("locator"))

    # 5) evidence pages — one key_evidence per page
    key_evidence = mainline.get("key_evidence", [])
    for ke in key_evidence:
        ev_bindings, dv = [], []
        for ref in ke.get("refs", []):
            item = index_by_id.get(ref)
            if not item:
                continue
            ev_bindings.append(_make_binding(item))
            dv.extend(_data_verbatim_for(ref, item))
        add("evidence", ke.get("claim", ""), bullets=ke.get("bullets", []),
            evidence=ev_bindings, data_verbatim=dv, locator=ke.get("locator"))

    # 6) conclusion
    concl = mainline.get("conclusion") or {}
    concl_ev = []
    for ref in concl.get("refs", []):
        item = index_by_id.get(ref)
        if item:
            concl_ev.append(_make_binding(item))
    add("conclusion", concl.get("claim", ""), evidence=concl_ev, locator=concl.get("locator"))

    # 7) limitations
    lims = mainline.get("limitations") or []
    if lims:
        add("limitations", "Limitations and scope", bullets=[l.get("claim", "") for l in lims],
            locator=(lims[0].get("locator") if lims else None))

    # 8) thanks / backup (reserve one page when budget allows)
    if len(slides) + 1 <= limit:
        add("thanks", "Thank you", bullets=["Questions and discussion"], notes="Open floor for questions.")

    # ---- fold when over the hard limit ----
    def make_backup(spill: list) -> dict:
        backup = {
            "index": 0, "role": "backup",
            "claim": "Additional supporting results",
            "bullets": [s.get("claim", "") for s in spill],
            "evidence": [],
            "data_verbatim": [],
            "notes": "Backup slides: one line per result; expand only if asked.",
            "layout": {}, "uncertainty": [],
        }
        for s in spill:
            backup["evidence"].extend(s.get("evidence", []))
            backup["data_verbatim"].extend(s.get("data_verbatim", []))
        return backup

    fold_notes: list[str] = []

    # A: drop thanks
    if len(slides) > limit and any(s.get("role") == "thanks" for s in slides):
        slides = [s for s in slides if s.get("role") != "thanks"]
        fold_notes.append("dropped thanks page")

    # B: fold gap into problem
    if len(slides) > limit:
        gap = [s for s in slides if s.get("role") == "gap"]
        prob = [s for s in slides if s.get("role") == "problem"]
        if gap and prob:
            t = prob[0]
            t["bullets"] = ([gap[0]["claim"]] if gap[0].get("claim") else []) + t.get("bullets", [])
            t["claim_locator"] = t.get("claim_locator") or gap[0].get("claim_locator")
            slides = [s for s in slides if s.get("role") != "gap"]
            fold_notes.append("folded gap into problem page")

    # C: fold limitations into conclusion
    if len(slides) > limit:
        lims = [s for s in slides if s.get("role") == "limitations"]
        concl = [s for s in slides if s.get("role") == "conclusion"]
        if lims and concl:
            t = concl[0]
            for ls in lims:
                t.setdefault("bullets", []).extend(ls.get("bullets", []))
            slides = [s for s in slides if s.get("role") != "limitations"]
            fold_notes.append("folded limitations into conclusion page")

    # D: fit evidence pages (keep full pages while possible, move overflow into one backup page)
    if len(slides) > limit:
        evidence_slides = [s for s in slides if s.get("role") == "evidence"]
        non_evidence = [s for s in slides if s.get("role") != "evidence"]
        slots = limit - len(non_evidence)
        if evidence_slides and slots >= 2:
            keep = evidence_slides[: slots - 1]
            spill = evidence_slides[slots - 1:]
            slides = non_evidence + keep + [make_backup(spill)]
            fold_notes.append(f"kept {len(keep)}/{len(evidence_slides)} evidence pages, rest in one backup page")
        elif evidence_slides and slots == 1:
            slides = non_evidence + [make_backup(evidence_slides)]
            fold_notes.append("no room for individual evidence pages: all results in one backup page")
        elif evidence_slides and slots <= 0:
            # no slot at all: preserve the claims as bullets on the conclusion page
            concl = [s for s in non_evidence if s.get("role") == "conclusion"]
            target = concl[0] if concl else non_evidence[0]
            for es in evidence_slides:
                target.setdefault("bullets", []).append(es.get("claim", ""))
                target.setdefault("evidence", []).extend(es.get("evidence", []))
                target.setdefault("data_verbatim", []).extend(es.get("data_verbatim", []))
            slides = non_evidence
            fold_notes.append("no slot for evidence pages: evidence claims folded into conclusion bullets")

    # E: irreducible — required pages alone exceed the limit
    if len(slides) > limit:
        fold_notes.append(f"IRREDUCIBLE: {len(slides)} required pages > limit {limit}; "
                          f"prioritize problem/method/conclusion and drop gap/supporting pages")

    # re-index
    for i, s in enumerate(slides, 1):
        s["index"] = i

    # layout assignment
    for s in slides:
        s["layout"] = _layout_for(s, template)
        if not template:
            s["layout"]["overflow_plan"] = "no template supplied; use defaults in SKILL.md"
        # carry locator into the slide so every claim is traceable
        loc = s.pop("_locator", None)
        if loc and locator_ok(loc):
            s.setdefault("uncertainty", [])
            # store claim locator on first evidence-free slide via notes? keep it explicit:
            s["claim_locator"] = copy.deepcopy(loc)

    # narrative arc
    arc = []
    for s in slides:
        arc.append(f"{s['role']}" if s["role"] != "evidence" else f"evidence:{s.get('index')}")

    # evidence map
    evidence_map = []
    used_by = {}
    for s in slides:
        for ev in s.get("evidence", []):
            ref = ev.get("ref")
            if ref:
                used_by.setdefault(ref, []).append(s["index"])
    for item in index_items:
        ref = item.get("id")
        slides_using = used_by.get(ref, [])
        evidence_map.append({
            "ref": ref,
            "slides": sorted(slides_using),
            "status": "used" if slides_using else "unused",
            "unused_reason": None if slides_using else "extracted but not required for the mainline",
            "owner": item.get("owner"),
            "kind": item.get("kind"),
            "role": item.get("role"),
            "label": item.get("label"),
            "locator": copy.deepcopy(item.get("locator")),
        })

    outline = {
        "paper_id": paper_id,
        "schema_version": SCHEMA_VERSION,
        "meta": meta,
        "narrative_arc": arc,
        "slides": slides,
        "evidence_index": index_items,
        "evidence_map": evidence_map,
        "contract": {},
    }
    ok, outline = validate(outline, limit)
    for fn in fold_notes:
        if not any(fn in w for w in outline["contract"]["warnings"]):
            outline["contract"]["warnings"].append(fn)
    return outline


# --------------------------------------------------------------------------- #
# demo skeleton (synthetic, never a real case)
# --------------------------------------------------------------------------- #
def demo_skeleton() -> dict:
    return {
        "paper_id": "demo-paper-0001",
        "meta": {
            "title": "Synthetic demonstration of the paper-to-academic-PPT contract",
            "authors": ["A. Example", "B. Sample"],
            "venue": "Demo Journal",
            "doi": None,
            "source_file": "demo_paper.pdf",
            "page_count": 8,
        },
        "mainline": {
            "problem": {
                "claim": "Current method X fails for rare, low-sample-size conditions.",
                "locator": {"page": 1, "section": "Abstract", "where": "last sentence"},
            },
            "gap": {
                "claim": "No existing approach separates the confounding factor C.",
                "locator": {"page": 2, "section": "Introduction", "where": "paragraph 3"},
            },
            "method": {
                "claim": "We propose a two-stage estimator that controls C via stratified re-weighting.",
                "refs": ["formula:1", "fig:1"],
                "locator": {"page": 3, "section": "Methods", "where": "paragraph 1"},
            },
            "key_evidence": [
                {
                    "id": "ev1",
                    "claim": "The proposed estimator reduces bias by 41% versus the baseline.",
                    "refs": ["fig:2", "tab:1"],
                    "bullets": ["bias metric on held-out set", "n=120, five seeds"],
                    "locator": {"page": 4, "section": "Results", "where": "Table 1 caption"},
                },
                {
                    "id": "ev2",
                    "claim": "The method stays stable when sample size drops to n=20.",
                    "refs": ["fig:3"],
                    "locator": {"page": 5, "section": "Results", "where": "Figure 3 caption"},
                },
            ],
            "conclusion": {
                "claim": "Two-stage stratified re-weighting gives lower bias without losing coverage.",
                "refs": ["fig:2"],
                "locator": {"page": 6, "section": "Discussion", "where": "paragraph 1"},
            },
            "limitations": [
                {"claim": "Assumes C is observed; unobserved confounders remain open.",
                 "locator": {"page": 6, "section": "Discussion", "where": "paragraph 3"}},
            ],
        },
        "evidence_index": [
            {
                "id": "fig:1", "kind": "figure", "role": "schematic", "owner": "paper",
                "label": "Figure 1",
                "caption": "Schematic of the two-stage estimator. Arrows show data flow.",
                "locator": {"page": 3, "section": "Methods", "where": "Figure 1"},
                "data_points": [],
            },
            {
                "id": "formula:1", "kind": "formula", "role": "formula", "owner": "paper",
                "label": "(1)",
                "caption": "bias-corrected estimator definition",
                "locator": {"page": 3, "section": "Methods", "where": "equation (1)"},
                "data_points": [],
            },
            {
                "id": "fig:2", "kind": "figure", "role": "data", "owner": "paper",
                "label": "Figure 2",
                "caption": "Bias vs. baseline across five seeds (box plot).",
                "locator": {"page": 4, "section": "Results", "where": "Figure 2"},
                "data_points": [
                    {"value": "41", "unit": "%", "condition": "n=120, five seeds",
                     "locator": {"page": 4, "section": "Results", "where": "Figure 2 y-axis"}},
                ],
            },
            {
                "id": "tab:1", "kind": "table", "role": "data", "owner": "paper",
                "label": "Table 1",
                "caption": "Bias and coverage on the held-out benchmark.",
                "locator": {"page": 4, "section": "Results", "where": "Table 1"},
                "data_points": [
                    {"value": "41", "unit": "%", "condition": "bias reduction, held-out set",
                     "locator": {"page": 4, "section": "Results", "where": "Table 1 row 2"}},
                ],
            },
            {
                "id": "fig:3", "kind": "figure", "role": "data", "owner": "paper",
                "label": "Figure 3",
                "caption": "Stability under decreasing sample size.",
                "locator": {"page": 5, "section": "Results", "where": "Figure 3"},
                "data_points": [
                    {"value": "20", "unit": "samples", "condition": "smallest n",
                     "locator": {"page": 5, "section": "Results", "where": "Figure 3 x-axis"}},
                ],
            },
            {
                "id": "fig:0", "kind": "figure", "role": "data", "owner": "cited",
                "label": "Figure 1 (cited)",
                "caption": "Prior baseline result reproduced from a cited paper.",
                "locator": {"page": 2, "section": "Introduction", "where": "citation [12]"},
                "data_points": [],
            },
        ],
    }


# --------------------------------------------------------------------------- #
# self-test
# --------------------------------------------------------------------------- #
def self_test() -> int:
    failures = []

    def expect(name, cond, detail=""):
        if cond:
            print(f"PASS {name}")
        else:
            failures.append(name)
            print(f"FAIL {name} {detail}")

    # 1) demo builds and validates cleanly
    sk = demo_skeleton()
    outline = build(copy.deepcopy(sk), limit=10)
    ok, outline = validate(outline, 10)
    expect("demo builds and validates cleanly", ok, "; ".join(outline["contract"]["errors"][:3]))

    # 2) one claim per page: too many bullets is an error
    bad = build(copy.deepcopy(sk), limit=10)
    bad["slides"][1]["bullets"] = ["a", "b", "c", "d", "e", "f", "g"]
    ok, _ = validate(bad, 10)
    expect("too many bullets rejected", not ok)

    # 3) schematic presented as data is rejected
    bad = build(copy.deepcopy(sk), limit=10)
    for s in bad["slides"]:
        for ev in s.get("evidence", []):
            if ev.get("ref") == "fig:1":
                ev["use"] = "data"
    ok, _ = validate(bad, 10)
    expect("schematic-as-data rejected", not ok)

    # 4) altered number is rejected
    bad = build(copy.deepcopy(sk), limit=10)
    for s in bad["slides"]:
        for dv in s.get("data_verbatim", []):
            if dv.get("value") == "41":
                dv["value"] = "42"
    ok, _ = validate(bad, 10)
    expect("altered number rejected", not ok)

    # 5) missing locator is rejected
    bad = build(copy.deepcopy(sk), limit=10)
    for s in bad["slides"]:
        for ev in s.get("evidence", []):
            if ev.get("ref") == "fig:2":
                ev["locator"] = None
        # also strip the index locator so no fallback exists
    for e in bad["evidence_index"]:
        if e.get("id") == "fig:2":
            e["locator"] = None
    ok, _ = validate(bad, 10)
    expect("missing locator rejected", not ok)

    # 6) slide count over limit is rejected
    bad = build(copy.deepcopy(sk), limit=10)
    ok, _ = validate(bad, 4)
    expect("slide-count-over-limit rejected", not ok)

    # 7) third-party result without attribution is rejected
    bad = build(copy.deepcopy(sk), limit=10)
    # put a cited figure on a content slide as a reference but leave notes unattributed
    target = next(s for s in bad["slides"] if s["role"] == "method")
    target["evidence"].append({"ref": "fig:0", "use": "reference", "label": "Figure 1 (cited)",
                               "caption_note": None, "locator": {"page": 2}})
    ok, _ = validate(bad, 10)
    expect("third-party result without attribution rejected", not ok)

    # 8) notes repeating slide text verbatim is rejected
    bad = build(copy.deepcopy(sk), limit=10)
    s = bad["slides"][1]
    s["notes"] = s["claim"] + " (verbatim repeat)"
    ok, _ = validate(bad, 10)
    expect("verbatim notes rejected", not ok)

    # 9) unknown evidence ref is rejected
    bad = build(copy.deepcopy(sk), limit=10)
    bad["slides"][1]["evidence"].append({"ref": "fig:999", "use": "data", "label": None, "locator": None})
    ok, _ = validate(bad, 10)
    expect("unknown evidence ref rejected", not ok)

    if failures:
        print(f"\n{len(failures)} self-test(s) FAILED: {failures}")
        return 1
    print(f"\nAll self-tests passed ({9} checks).")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build and validate a page-level slide outline + evidence map for paper→academic PPT.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("build", help="paper_skeleton.json -> slide_outline.json")
    pb.add_argument("skeleton", help="input paper skeleton JSON")
    pb.add_argument("--out", default="slide_outline.json")
    pb.add_argument("--limit", type=int, default=DEFAULT_SLIDE_LIMIT)
    pb.add_argument("--template", help="optional template_spec.json (layouts + placeholders + constraints)")

    pv = sub.add_parser("validate", help="re-run contract checks on a slide_outline.json")
    pv.add_argument("outline", help="input slide outline JSON")
    pv.add_argument("--limit", type=int, default=None)

    pd = sub.add_parser("demo", help="write a synthetic paper_skeleton")
    pd.add_argument("--out", default="demo_skeleton.json")

    sub.add_parser("self-test", help="run built-in validator tests")

    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.cmd == "build":
            skeleton = load_json(args.skeleton)
            template = load_json(args.template) if args.template else None
            outline = build(skeleton, args.limit, template)
            write_json(args.out, outline)
            ok = len(outline["contract"]["errors"]) == 0
            for e in outline["contract"]["errors"]:
                _err(e)
            for w in outline["contract"]["warnings"]:
                _warn(w)
            print(f"wrote {args.out}: {len(outline['slides'])} slides, "
                  f"{len(outline['contract']['errors'])} errors, "
                  f"{len(outline['contract']['warnings'])} warnings")
            return 0 if ok else 3
        if args.cmd == "validate":
            outline = load_json(args.outline)
            ok, outline = validate(outline, args.limit)
            for e in outline["contract"]["errors"]:
                _err(e)
            for w in outline["contract"]["warnings"]:
                _warn(w)
            print(f"{len(outline['slides'])} slides; contract "
                  f"{'HOLDS' if ok else 'VIOLATED'} "
                  f"({len(outline['contract']['errors'])} errors, "
                  f"{len(outline['contract']['warnings'])} warnings)")
            return 0 if ok else 3
        if args.cmd == "demo":
            write_json(args.out, demo_skeleton())
            print(f"wrote synthetic demo skeleton: {args.out}")
            return 0
        if args.cmd == "self-test":
            return self_test()
        return 2
    except FileNotFoundError as e:
        _err(f"missing file: {e}")
        return 4
    except (ValueError, json.JSONDecodeError) as e:
        _err(f"bad input: {e}")
        return 4


if __name__ == "__main__":
    sys.exit(main())
