#!/usr/bin/env python3
"""
Nanopublication validator, normalizer and assertion-decomposition helper (reading14).

Stdlib-only. Three jobs:

  1. validate   -- check a result.json draft for assertion granularity (split fine),
                   evidence binding (bind evidence), provenance completeness
                   (trace back) and machine readability (readable export). Optionally
                   cross-check that every verbatim quote is a substring of the
                   extracted paper text.
  2. export     -- validate, then re-emit a normalized result.json (sorted keys,
                   indent=2, ensure_ascii=False) that downstream tools can parse
                   without manual cleanup.
  3. decompose  -- heuristic marker scan on one source sentence: detect clause-level
                   coordination, causal chaining, compound subject/object and
                   condition phrases, and emit *suggestions* the agent must verify
                   against the source before committing.

Exit codes (validate only): 0 = clean, 1 = errors, 2 = warnings only.

The controlled vocabularies are hard-coded below as the authoritative copy and can
be overridden by enums read from schema/nanopub_schema.json (--schema) to stay in
sync with the documented field dictionary. Relation is a recommended closed set:
an out-of-vocabulary verb is a WARNING (the assertion must carry a note), never a
silent hard failure, so the skill stays general to unseen papers.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Controlled vocabularies (mirror schema/nanopub_schema.json $defs)
# ---------------------------------------------------------------------------
TOP_STATUS = {"success", "partial", "failed"}
ASSERTION_STATUS = {"supported", "unsupported", "conflict", "not_extractable"}
RELATION_TYPES = {"causal", "associative", "comparative", "definitional",
                  "quantitative", "methodological"}
POLARITY = {"affirmative", "negated"}
DIRECTION = {"positive", "negative", "neutral", "not_applicable"}
QUANTIFIER = {"all", "some", "none", "specific", "not_stated", "none_reported"}
CERTAINTY_LEVEL = {"reported", "inferred", "speculative"}
QUOTE_TYPES = {"verbatim", "paraphrase", "figure_description",
               "table_description", "equation"}
REL_TO_ASSERTION = {"direct", "inferred", "context"}
SUFFICIENCY = {"sufficient", "partial", "insufficient"}
ENTITY_TYPES = {"gene", "protein", "drug", "compound", "disease", "phenotype",
                "cell_type", "cell_line", "organism", "pathway", "process",
                "method", "metric", "dataset", "model", "other"}
CONDITION_SLOTS = {"organism", "cell_line", "dosage", "exposure", "time",
                   "temperature", "context", "comparator", "setting",
                   "population", "other"}
DECOMP_METHODS = {"direct", "coordination_split", "causal_split",
                  "condition_extraction"}
SOURCE_KIND = {"paper", "preprint", "dataset", "figure", "supplement"}
SOURCE_STATUS = {"ok", "missing", "unreachable", "unparseable"}
ISSUE_TYPES = {"over_broad_assertion", "insufficient_evidence",
               "wrong_relation_type", "subject_confusion", "missing_source",
               "other"}

# relation verb -> relation_type. Also used for relation<->type consistency.
RELATION_VOCAB = {
    # causal, positive sign
    "increases": "causal", "promotes": "causal", "induces": "causal",
    "activates": "causal", "upregulates": "causal", "enhances": "causal",
    "accelerates": "causal", "stimulates": "causal",
    # causal, negative sign
    "decreases": "causal", "inhibits": "causal", "suppresses": "causal",
    "downregulates": "causal", "blocks": "causal", "reduces": "causal",
    "impairs": "causal", "prevents": "causal", "attenuates": "causal",
    # causal, sign-unspecified
    "causes": "causal", "leads_to": "causal", "results_in": "causal",
    "contributes_to": "causal", "requires": "causal", "mediates": "causal",
    "modulates": "causal", "regulates": "causal", "depends_on": "causal",
    "drives": "causal", "triggers": "causal",
    # associative
    "associated_with": "associative", "correlates_with": "associative",
    "predicts": "associative", "linked_to": "associative",
    # comparative
    "greater_than": "comparative", "less_than": "comparative",
    "equivalent_to": "comparative", "differs_from": "comparative",
    # definitional / structural
    "is_a": "definitional", "part_of": "definitional", "expresses": "definitional",
    "encodes": "definitional", "binds": "definitional",
    "localizes_to": "definitional", "interacts_with": "definitional",
    "composes": "definitional", "contains": "definitional",
    "has_property": "definitional",
    # quantitative
    "measured_as": "quantitative", "has_value": "quantitative",
    "has_rate": "quantitative", "has_prevalence": "quantitative",
    "has_sensitivity": "quantitative",
    # methodological
    "evaluated_by": "methodological", "detected_by": "methodological",
    "measured_by": "methodological", "treated_with": "methodological",
    "compared_against": "methodological",
}
POSITIVE_RELATIONS = {"increases", "promotes", "induces", "activates",
                      "upregulates", "enhances", "accelerates", "stimulates",
                      "greater_than"}
NEGATIVE_RELATIONS = {"decreases", "inhibits", "suppresses", "downregulates",
                      "blocks", "reduces", "impairs", "prevents",
                      "attenuates", "less_than"}

# ---------------------------------------------------------------------------
# Decomposition markers (heuristic; suggestions only, never auto-committed)
# ---------------------------------------------------------------------------
CAUSAL_CHAIN_RE = re.compile(
    r"\bwhich\s+(?:leads? to|led to|causes?d?|results? in|resulted in|"
    r"resulting in|promotes?|promoted|triggers?|triggered|induces?|induced|"
    r"in turn|increases?d?|decreases?d?|reduces?d?)\b|"
    r"\b(?:leading to|resulting in|thereby|consequently|,?\s*causing)\b",
    re.IGNORECASE)

# "and/or + verb" coordination between two verb phrases (no comma required).
# Explicit present/past forms so common past-tense verbs are not missed.
COORD_VERB_FOLLOW = re.compile(
    r"\b(and|or)\s+(?:increases?|increased|decreases?|decreased|inhibits?|"
    r"inhibited|suppresses?|suppressed|promotes?|promoted|induces?|induced|"
    r"activates?|activated|enhances?|enhanced|reduces?|reduced|improves?|"
    r"improved|impairs?|impaired|blocks?|blocked|upregulates?|upregulated|"
    r"downregulates?|downregulated|modulates?|modulated|regulates?|regulated|"
    r"leads? to|led to|results? in|resulted in|causes?|caused|triggers?|"
    r"triggered|correlates? with|correlated with|is associated with|"
    r"are associated with|was associated with)\b",
    re.IGNORECASE)

CONDITION_PHRASES = [
    "in vitro", "in vivo", "ex vivo", "in situ", "in silico",
    "in the presence of", "in the absence of",
    "in patients with", "in mice", "in rats", "in humans", "in animals",
    "under", "among", "after", "before", "during", "upon", "when",
    "compared to", "compared with", "relative to", "in response to",
    "at a dose", "at a concentration", "at a temperature",
    "in a dose-dependent", "in a time-dependent",
]

# Sentence-ending split, after protecting common abbreviations and decimals.
_ABBREV = re.compile(r"\b(e\.g\.|i\.e\.|et al\.|vs\.|cf\.|fig\.|figs\.|eq\.|eqs\.|"
                     r"etc\.|ref\.|refs\.|al\.)", re.IGNORECASE)


def sentence_count(text):
    """Rough sentence count after protecting abbreviations and decimals."""
    if not text:
        return 0
    t = _ABBREV.sub(lambda m: m.group(1).replace(".", "\u0000"), text)
    t = re.sub(r"(\d)\.(\d)", lambda m: m.group(1) + "\u0000" + m.group(2), t)
    parts = [p for p in re.split(r"[.!?]+[\s)\]]*", t) if p.strip()]
    return len(parts)


def clause_coordination(text):
    """Return clause- and verb-phrase-level coordinating conjunctions."""
    hits = []
    for m in re.finditer(r"(?:,|;)\s*(and|or|but|as well as)\b", text or "",
                         re.IGNORECASE):
        hits.append({"conjunction": m.group(1).lower(), "at": m.start(),
                     "kind": "clause"})
    for m in COORD_VERB_FOLLOW.finditer(text or ""):
        hits.append({"conjunction": m.group(1).lower(), "at": m.start(),
                     "kind": "verb_phrase"})
    return hits


def compound_entities(text):
    """Possible '<NP> and <NP>' compounds (capitalized noun phrases only).

    These are *candidates*: the agent must decide whether the two are one
    combined entity (keep together) or two separate claims (split).
    """
    pat = re.compile(
        r"\b([A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,2})\s+and\s+"
        r"([A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,2})\b")
    return [{"left": m.group(1), "right": m.group(2), "at": m.start()}
            for m in pat.finditer(text or "")]


def condition_phrases(text):
    """Return condition/qualifier phrases present in the sentence."""
    low = (text or "").lower()
    found = []
    for phrase in CONDITION_PHRASES:
        if phrase in low:
            found.append(phrase)
    return found


def causal_chain_markers(text):
    return [m.group(0) for m in CAUSAL_CHAIN_RE.finditer(text or "")]


def scan_sentence(text):
    """Marker scan used by the `decompose` command. Suggestions only."""
    text = (text or "").strip()
    coord = clause_coordination(text)
    chains = causal_chain_markers(text)
    compounds = compound_entities(text)
    conds = condition_phrases(text)
    units, warnings = [], []

    split_points = sorted({c["at"] for c in coord} |
                          {m.start() for m in CAUSAL_CHAIN_RE.finditer(text)})
    if split_points:
        bounds = [0] + split_points + [len(text)]
        segs = []
        for a, b in zip(bounds, bounds[1:]):
            seg = text[a:b].strip(" ,;.")
            seg = re.sub(r"^(and|or|but|which|that|as well as)\s+", "",
                         seg, flags=re.IGNORECASE)
            if seg:
                segs.append(seg)
        if len(segs) > 1:
            units = segs
    if coord:
        warnings.append("coordinating conjunction detected: split into one "
                        "assertion per coordinated claim, then verify each "
                        "fragment still carries subject+relation+object.")
    if chains:
        warnings.append("causal chain detected: emit the cause and the effect "
                        "as separate assertions linked by their own evidence.")
    if compounds:
        warnings.append("possible compound subject/object detected: split only "
                        "if the two are separate claims; keep together if they "
                        "are one combined entity.")
    return {
        "text": text,
        "sentence_count": sentence_count(text),
        "clause_coordination": coord,
        "causal_chain_markers": chains,
        "compound_entities": compounds,
        "condition_phrases": conds,
        "suggested_split_units": units,
        "suggested_conditions": conds,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Schema enum loading (optional; schema is the documented field dictionary)
# ---------------------------------------------------------------------------
def load_enums(schema_path):
    enums = {}
    if not schema_path:
        return enums
    try:
        with open(schema_path, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
    except Exception as exc:
        print(f"[warn] could not load schema {schema_path}: {exc}",
              file=sys.stderr)
        return enums
    defs = schema.get("$defs") or schema.get("definitions") or {}
    for key, defn in defs.items():
        if isinstance(defn, dict) and "enum" in defn:
            enums[key] = set(defn["enum"])
    return enums


def build_vocab(schema_path):
    enums = load_enums(schema_path)
    return {
        "status": enums.get("status") or TOP_STATUS,
        "assertion_status": enums.get("assertion_status") or ASSERTION_STATUS,
        "relation_type": enums.get("relation_type") or RELATION_TYPES,
        "polarity": enums.get("polarity") or POLARITY,
        "direction": enums.get("direction") or DIRECTION,
        "quantifier": enums.get("quantifier") or QUANTIFIER,
        "certainty_level": enums.get("certainty_level") or CERTAINTY_LEVEL,
        "quote_type": enums.get("quote_type") or QUOTE_TYPES,
        "relation_to_assertion": (enums.get("relation_to_assertion")
                                  or REL_TO_ASSERTION),
        "sufficiency": enums.get("sufficiency_judgment") or SUFFICIENCY,
        "entity_type": enums.get("entity_type") or ENTITY_TYPES,
        "condition_slot": enums.get("condition_slot") or CONDITION_SLOTS,
        "decomposition_method": (enums.get("decomposition_method")
                                 or DECOMP_METHODS),
        "source_kind": enums.get("source_kind") or SOURCE_KIND,
        "source_status": enums.get("source_status") or SOURCE_STATUS,
        "issue_type": enums.get("issue_type") or ISSUE_TYPES,
    }


# ---------------------------------------------------------------------------
# Text matching helpers
# ---------------------------------------------------------------------------
def norm_match(s):
    s = (s or "").strip()
    s = s.strip("""'"\u201c\u201d\u2018\u2019""")
    s = re.sub(r"\s+", " ", s)
    s = s.replace("\u00ad", "")          # soft hyphen
    s = re.sub(r"-\s*\n\s*", "", s)      # line-broken hyphenation
    return s.lower()


def quote_in_text(quote, text):
    q = norm_match(quote)
    if not q:
        return False
    return q in norm_match(text)


def mentions_label(quote, label):
    """Whether a quote contains the label or one of its content words."""
    q = norm_match(quote)
    lab = norm_match(label)
    if not lab:
        return False
    if lab in q:
        return True
    tokens = [t for t in re.findall(r"[a-z0-9]+", lab) if len(t) >= 3]
    return any(t in q for t in tokens)


def _has(items, *substrs):
    """True if any item contains any of the substrings."""
    return any(any(s in it for s in substrs) for it in items)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _add_check(checks, cid, question, name, result, detail):
    checks.append({"id": cid, "question": question, "name": name,
                   "result": result, "detail": detail})


def validate(result, vocab, text=None):
    errors, warnings, checks = [], [], []
    issues = []

    def issue(assertion_id, issue_type, detail, fix=""):
        issues.append({"assertion_id": assertion_id, "issue_type": issue_type,
                       "detail": detail, "fix": fix})

    if not isinstance(result, dict):
        return (["result root must be a JSON object"], [], [], {}, [])

    # ---- machine_readable: top level ----
    if result.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}, got "
                      f"{result.get('schema_version')!r}")
    if not isinstance(result.get("case_id"), str) or not result["case_id"].strip():
        errors.append("missing/empty 'case_id' (copy it from /input/case.json)")
    if result.get("status") not in vocab["status"]:
        errors.append(f"status must be one of {sorted(vocab['status'])}")
    _add_check(checks, "M1", "machine_readable", "top-level fields present",
               "fail" if _has(errors, "schema_version", "missing/empty 'case_id'",
                              "status must be") else "pass",
               "schema_version, case_id, status present and valid")

    sources = result.get("sources", []) or []
    assertions = result.get("assertions", []) or []
    if not isinstance(sources, list) or not sources:
        errors.append("'sources' must be a non-empty array")
    if not isinstance(assertions, list):
        errors.append("'assertions' must be an array")
        assertions = []

    source_ids = {}
    for s in sources:
        if not isinstance(s, dict):
            continue
        sid = s.get("source_id")
        if not sid:
            errors.append("source missing 'source_id'")
        elif sid in source_ids:
            errors.append(f"duplicate source_id '{sid}'")
        else:
            source_ids[sid] = s

    # ---- machine_readable: id uniqueness across assertions ----
    aid_seen, eid_seen = {}, {}
    for i, a in enumerate(assertions):
        if not isinstance(a, dict):
            errors.append(f"assertion[{i}] is not an object")
            continue
        aid = a.get("assertion_id")
        if not aid:
            errors.append(f"assertion[{i}] missing 'assertion_id'")
        elif aid in aid_seen:
            errors.append(f"duplicate assertion_id '{aid}' "
                          f"(also at assertion[{aid_seen[aid]}])")
        else:
            aid_seen[aid] = i
        eb = a.get("evidence_binding") or {}
        eid = eb.get("evidence_id")
        if eid:
            if eid in eid_seen:
                errors.append(f"duplicate evidence_id '{eid}'")
            else:
                eid_seen[eid] = aid

    # ---- per-assertion checks ----
    for i, a in enumerate(assertions):
        if not isinstance(a, dict):
            continue
        where = f"assertion '{a.get('assertion_id') or f'#{i}'}'"
        aid = a.get("assertion_id", "")

        sf_err, sf_warn = [], []   # split_fine
        be_err, be_warn = [], []   # bind_evidence
        tp_err, tp_warn = [], []   # trace_provenance

        # ----- split_fine: granularity -----
        text_a = a.get("text")
        if not isinstance(text_a, str) or not text_a.strip():
            sf_err.append("missing/empty 'text'")
        elif len(text_a) > 600:
            sf_err.append(f"text is {len(text_a)} chars (>600): a whole "
                          f"paragraph was dumped into one field; split it")
            issue(aid, "over_broad_assertion",
                  f"text {len(text_a)} chars, likely multiple claims",
                  "split into single claims")
        elif len(text_a) > 280:
            sf_warn.append(f"text is {len(text_a)} chars (>280): verify it is "
                           f"still one claim, not several")
            issue(aid, "over_broad_assertion",
                  f"text {len(text_a)} chars, check for hidden compound claims",
                  "split further if needed")
        if isinstance(text_a, str) and sentence_count(text_a) > 1:
            sf_err.append(f"text contains {sentence_count(text_a)} sentences; "
                          f"one assertion = one sentence/claim")
            issue(aid, "over_broad_assertion", "multiple sentences in one assertion",
                  "split into one assertion per sentence")
        if isinstance(text_a, str) and clause_coordination(text_a):
            sf_warn.append("text contains a coordinating conjunction joining two "
                           "claims; split into one assertion per claim")
            issue(aid, "over_broad_assertion",
                  "compound coordination inside one assertion",
                  "split at the conjunction; keep each claim with its own evidence")
        if isinstance(text_a, str) and causal_chain_markers(text_a):
            sf_warn.append("text contains a causal chain; emit cause and effect "
                           "as separate assertions")
            issue(aid, "over_broad_assertion",
                  "causal chain packed into one assertion",
                  "split cause and effect into two assertions")

        subj = a.get("subject") or {}
        obj = a.get("object") or {}
        for role, ent in (("subject", subj), ("object", obj)):
            if not isinstance(ent.get("label"), str) or not ent["label"].strip():
                sf_err.append(f"missing/empty {role}.label")
            if ent.get("type") and ent.get("type") not in vocab["entity_type"]:
                sf_warn.append(f"{role}.type '{ent.get('type')}' not in "
                               f"entity_type vocabulary")
        if (isinstance(subj.get("label"), str) and isinstance(obj.get("label"), str)
                and subj["label"].strip() and obj["label"].strip()
                and norm_match(subj["label"]) == norm_match(obj["label"])):
            sf_err.append(f"subject and object have the same label "
                          f"'{subj['label']}' (subject/object confusion)")
            issue(aid, "subject_confusion", "subject == object",
                  "re-read the source; fix direction")

        rel = a.get("relation")
        if not isinstance(rel, str) or not rel.strip():
            sf_err.append("missing 'relation'")
        elif not re.match(r"^[a-z][a-z0-9_]{1,39}$", rel):
            sf_err.append(f"relation '{rel}' must be lowercase snake_case")
        elif rel not in RELATION_VOCAB:
            sf_warn.append(f"relation '{rel}' is not in the controlled "
                           f"vocabulary; add decomposition.note with the mapping")
        if a.get("relation_type") not in vocab["relation_type"]:
            sf_err.append(f"unknown relation_type '{a.get('relation_type')}'")
        elif rel in RELATION_VOCAB and RELATION_VOCAB[rel] != a.get("relation_type"):
            sf_err.append(f"relation '{rel}' maps to {RELATION_VOCAB[rel]!r} "
                          f"but relation_type is {a.get('relation_type')!r}")
            issue(aid, "wrong_relation_type",
                  f"verb {rel} conflicts with relation_type "
                  f"{a.get('relation_type')}",
                  "align relation_type with the verb's class")

        if a.get("polarity") not in vocab["polarity"]:
            sf_err.append(f"unknown polarity '{a.get('polarity')}'")
        if a.get("direction") not in vocab["direction"]:
            sf_err.append(f"unknown direction '{a.get('direction')}'")
        else:
            d = a.get("direction")
            if rel in POSITIVE_RELATIONS and d != "positive":
                sf_warn.append(f"relation '{rel}' is positive-sign but "
                               f"direction is '{d}'")
            if rel in NEGATIVE_RELATIONS and d != "negative":
                sf_warn.append(f"relation '{rel}' is negative-sign but "
                               f"direction is '{d}'")
        if "quantifier" in a and a["quantifier"] is not None and \
                a["quantifier"] not in vocab["quantifier"]:
            sf_warn.append(f"unknown quantifier '{a.get('quantifier')}'")
        if a.get("certainty", {}).get("level") not in vocab["certainty_level"]:
            sf_err.append(f"unknown certainty.level "
                          f"'{a.get('certainty', {}).get('level')}'")
        if a.get("decomposition", {}).get("method") not in vocab["decomposition_method"]:
            sf_err.append(f"unknown decomposition.method "
                          f"'{a.get('decomposition', {}).get('method')}'")

        conds = a.get("conditions") or []
        if not isinstance(conds, list):
            sf_err.append("'conditions' must be an array")
            conds = []
        for c in conds:
            if isinstance(c, dict) and c.get("slot") not in vocab["condition_slot"]:
                sf_warn.append(f"unknown condition.slot '{c.get('slot')}'")
        src_text = a.get("source_text") or ""
        if src_text and not conds and condition_phrases(src_text):
            sf_warn.append(f"source_text contains qualifier phrases "
                           f"{condition_phrases(src_text)} but conditions[] is "
                           f"empty; keep conditions/qualifiers")
            issue(aid, "over_broad_assertion",
                  "qualifiers present in source but dropped from conditions[]",
                  "lift qualifiers into conditions[]")

        # ----- bind_evidence: evidence binding -----
        eb = a.get("evidence_binding")
        if not isinstance(eb, dict) or not eb:
            be_err.append("missing 'evidence_binding'")
        else:
            st = a.get("status")
            quote = eb.get("quote")
            quote_missing = not isinstance(quote, str) or not quote.strip()
            if quote_missing:
                if st in ("unsupported", "not_extractable"):
                    be_warn.append(f"no quote bound; expected for status='{st}' "
                                   f"— record the reason in unreported/uncertainty")
                else:
                    be_err.append("missing/empty evidence_binding.quote")
                    issue(aid, "insufficient_evidence", "empty evidence quote",
                          "find the minimal supporting fragment or set "
                          "status='unsupported'")
            elif text is not None and eb.get("quote_type") == "verbatim" and \
                    not quote_in_text(quote, text):
                be_err.append("quote is not a substring of the provided text "
                              "file; it cannot be pointed back to the source")
                issue(aid, "insufficient_evidence",
                      "quote not found in paper text",
                      "copy the quote verbatim from the extracted text")
            elif text is None and eb.get("quote_type") == "verbatim":
                be_warn.append("no --text supplied; quote could not be verified "
                               "against the paper text")
            if eb.get("quote_type") not in vocab["quote_type"]:
                be_err.append(f"unknown quote_type '{eb.get('quote_type')}'")

            loc = eb.get("location") or {}
            loc_fields = ["page", "section", "paragraph", "sentence", "figure",
                          "table", "equation", "pointer"]
            if not any(loc.get(k) for k in loc_fields) and not quote_missing:
                be_err.append("evidence location has no page/section/paragraph/"
                              "sentence/figure/table/equation/pointer")
            if eb.get("quote_type") == "figure_description" and not loc.get("figure"):
                be_warn.append("quote_type=figure_description but location.figure "
                               "is empty; add the figure/panel id")

            rta = eb.get("relation_to_assertion")
            if rta not in vocab["relation_to_assertion"]:
                be_err.append(f"unknown relation_to_assertion '{rta}'")
            suff = eb.get("sufficiency") or {}
            if suff.get("judgment") not in vocab["sufficiency"]:
                be_err.append(f"unknown sufficiency.judgment "
                              f"'{suff.get('judgment')}'")
            if rta in ("inferred", "context") or \
                    (suff.get("judgment") != "sufficient"):
                if not (suff.get("reason") or "").strip():
                    be_err.append("sufficiency.reason required when "
                                  f"relation_to_assertion={rta!r} or judgment="
                                  f"{suff.get('judgment')!r}")
            if rta == "context" and a.get("status") == "supported":
                be_err.append("relation_to_assertion='context' cannot support "
                              "status='supported'; context is not evidence")
                issue(aid, "insufficient_evidence", "context quote used as support",
                      "use direct/inferred or downgrade status")

            if st not in vocab["assertion_status"]:
                be_err.append(f"unknown status '{st}'")
            if st == "supported" and suff.get("judgment") == "insufficient":
                be_err.append("status='supported' but sufficiency.judgment="
                              "'insufficient'")
                issue(aid, "insufficient_evidence",
                      "assertion marked supported with insufficient evidence",
                      "downgrade status or find better quote")
            if st == "unsupported" and suff.get("judgment") == "sufficient":
                be_err.append("status='unsupported' but sufficiency.judgment="
                              "'sufficient'")
            if st == "unsupported" and quote and quote.strip():
                be_warn.append("status='unsupported' but a quote is bound; "
                               "record why it does not support (or set status "
                               "to 'conflict' if it contradicts)")

            if isinstance(quote, str):
                qlen = len(quote)
                if qlen > 1000:
                    be_err.append(f"quote is {qlen} chars (>1000): not a minimal "
                                  f"fragment")
                elif qlen > 500:
                    be_warn.append(f"quote is {qlen} chars (>500): trim to the "
                                   f"minimal sufficient span")
                mentions = 0
                if mentions_label(quote, subj.get("label", "")):
                    mentions += 1
                if mentions_label(quote, obj.get("label", "")):
                    mentions += 1
                if mentions == 0 and qlen > 0 and rta == "direct":
                    be_warn.append("quote mentions neither subject nor object; "
                                   "verify it really supports this assertion")
                    issue(aid, "subject_confusion",
                          "quote does not mention subject or object",
                          "re-check the binding; maybe wrong quote")
                elif mentions == 1 and rta == "direct":
                    be_warn.append("quote mentions only one endpoint; verify "
                                   "the relation is actually stated")

        # ----- trace_provenance -----
        prov = a.get("provenance") or {}
        if not isinstance(prov, dict) or not prov:
            tp_err.append("missing 'provenance'")
        else:
            chain = prov.get("chain")
            expected = [prov.get("assertion_id"), prov.get("evidence_id"),
                        prov.get("source_id")]
            if not isinstance(chain, list) or len(chain) != 3 or chain != expected:
                tp_err.append(f"provenance.chain must be exactly "
                              f"[assertion_id, evidence_id, source_id] = "
                              f"{expected}; got {chain}")
            if prov.get("assertion_id") != a.get("assertion_id"):
                tp_err.append(f"provenance.assertion_id "
                              f"'{prov.get('assertion_id')}' != assertion_id "
                              f"'{a.get('assertion_id')}'")
            if prov.get("evidence_id") != eb.get("evidence_id"):
                tp_err.append(f"provenance.evidence_id '{prov.get('evidence_id')}'"
                              f" != evidence_binding.evidence_id "
                              f"'{eb.get('evidence_id')}'")
            if prov.get("source_id") not in source_ids:
                tp_err.append(f"provenance.source_id '{prov.get('source_id')}' "
                              f"not found in sources[]")
                issues.append({"assertion_id": aid, "issue_type": "missing_source",
                               "detail": f"provenance source_id "
                                         f"{prov.get('source_id')!r} not in sources",
                               "fix": "create the source entry or fix the reference"})

        errors.extend(sf_err + be_err + tp_err)
        warnings.extend(sf_warn + be_warn + tp_warn)

        _add_check(checks, f"S-{aid}", "split_fine",
                   "single claim, conditions kept",
                   "fail" if sf_err else ("warn" if sf_warn else "pass"),
                   "; ".join(sf_err + sf_warn) or "one subject/relation/object, "
                   "no compound coordination, qualifiers attached")
        _add_check(checks, f"E-{aid}", "bind_evidence",
                   "minimal sufficient fragment bound",
                   "fail" if be_err else ("warn" if be_warn else "pass"),
                   "; ".join(be_err + be_warn) or "quote+location+"
                   "relation_to_assertion present")
        _add_check(checks, f"P-{aid}", "trace_provenance",
                   "provenance chain complete",
                   "fail" if tp_err else ("warn" if tp_warn else "pass"),
                   "; ".join(tp_err + tp_warn) or "chain [assertion, evidence, "
                   "source] verified")

    # ---- source-level provenance completeness ----
    doi_re = re.compile(r"^10\.\d{4,9}/\S+$")
    for sid, s in source_ids.items():
        where_src = f"source '{sid}'"
        for field in ("title", "version", "identifiers"):
            if not s.get(field):
                errors.append(f"{where_src} missing '{field}'")
        if not s.get("authors"):
            errors.append(f"{where_src} missing 'authors'")
            issues.append({"assertion_id": None, "issue_type": "missing_source",
                           "detail": f"{where_src}: no authors",
                           "fix": "add author names"})
        y = s.get("year")
        if not isinstance(y, int) or not (1400 <= y <= 2100):
            errors.append(f"{where_src} year must be an integer 1400-2100, got "
                          f"{y!r} (use null+note only when unknown)")
        if s.get("kind") and s.get("kind") not in vocab["source_kind"]:
            warnings.append(f"{where_src} unknown kind '{s.get('kind')}'")
        idents = s.get("identifiers") or {}
        if isinstance(idents, dict) and not any(idents.get(k) for k in idents):
            errors.append(f"{where_src} identifiers must contain at least one of "
                          f"doi/pmid/pmcid/arxiv/url/publisher_id")
        doi = (idents or {}).get("doi")
        if doi and not doi_re.match(doi):
            warnings.append(f"{where_src} doi '{doi}' does not look like "
                            f"10.xxxx/...; verify, do not invent")
    _add_check(checks, "P0", "trace_provenance", "source metadata complete",
               "fail" if _has(errors, "missing 'authors'", "year must be",
                              "identifiers must", "missing 'title'",
                              "missing 'version'") else "pass",
               "each source has title+author+year+version+identifier")

    # orphan sources / unreferenced sources
    referenced = set()
    for a in assertions:
        if isinstance(a, dict):
            p = a.get("provenance") or {}
            if p.get("source_id"):
                referenced.add(p["source_id"])
    for sid in source_ids:
        if sid not in referenced:
            warnings.append(f"source '{sid}' is not referenced by any assertion "
                            f"(orphan source; remove or bind it)")

    _add_check(checks, "M2", "machine_readable", "ids unique",
               "fail" if _has(errors, "duplicate source_id",
                              "duplicate assertion_id",
                              "duplicate evidence_id") else "pass",
               "no duplicate source/assertion/evidence ids")

    counts = {
        "sources": len(source_ids),
        "assertions": len([a for a in assertions if isinstance(a, dict)]),
        "supported": sum(1 for a in assertions if isinstance(a, dict)
                         and a.get("status") == "supported"),
        "unsupported": sum(1 for a in assertions if isinstance(a, dict)
                           and a.get("status") == "unsupported"),
        "conflict": sum(1 for a in assertions if isinstance(a, dict)
                        and a.get("status") == "conflict"),
        "not_extractable": sum(1 for a in assertions if isinstance(a, dict)
                               and a.get("status") == "not_extractable"),
        "direct_evidence": sum(1 for a in assertions if isinstance(a, dict)
                               and (a.get("evidence_binding") or {}).get(
                                   "relation_to_assertion") == "direct"),
        "inferred_evidence": sum(1 for a in assertions if isinstance(a, dict)
                                 and (a.get("evidence_binding") or {}).get(
                                     "relation_to_assertion") == "inferred"),
    }
    return errors, warnings, checks, counts, issues


# ---------------------------------------------------------------------------
# Normalization / export
# ---------------------------------------------------------------------------
def sort_keys(obj):
    if isinstance(obj, dict):
        return {k: sort_keys(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [sort_keys(v) for v in obj]
    return obj


def normalize(result):
    """Deterministic, parseable re-emission with defaults filled in."""
    out = dict(result)
    out.setdefault("schema_version", SCHEMA_VERSION)
    out.setdefault("generated_at",
                   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    for a in out.get("assertions", []):
        if isinstance(a, dict):
            a.setdefault("language", "en")
            a.setdefault("quantifier", "not_stated")
            a.setdefault("conditions", [])
    return sort_keys(out)


# ---------------------------------------------------------------------------
# Self-test (synthetic EXAMPLE, NOT a formal case)
# ---------------------------------------------------------------------------
def _example_source():
    return {
        "source_id": "src-1",
        "kind": "paper",
        "title": "Example Paper on Example Kinase (synthetic)",
        "authors": ["Doe, Jane", "Roe, Richard"],
        "year": 2024,
        "version": "published",
        "identifiers": {"doi": "10.0000/EXAMPLE.000001"},
        "container": {"journal": "Journal of Examples", "volume": "1",
                      "pages": "1-10"},
        "language": "en",
        "status": "ok",
        "note": "Synthetic data used only to exercise the validator."
    }


def _example_assertion():
    return {
        "assertion_id": "a1",
        "text": "In HEK293T cells, kinase X increases phosphorylation of Y.",
        "language": "en",
        "source_text": "In HEK293T cells, kinase X increased the phosphorylation "
                       "of Y (Fig. 2B).",
        "subject": {"label": "kinase X", "type": "protein", "normalized": "X"},
        "relation": "increases",
        "relation_type": "causal",
        "direction": "positive",
        "polarity": "affirmative",
        "object": {"label": "phosphorylation of Y", "type": "phenotype",
                   "normalized": "Y phosphorylation"},
        "quantifier": "not_stated",
        "conditions": [{"slot": "cell_line", "value": "HEK293T",
                        "verbatim": "In HEK293T cells"}],
        "certainty": {"level": "reported", "basis": "verbatim sentence in Results"},
        "decomposition": {"method": "condition_extraction",
                          "note": "qualifier lifted into conditions[]"},
        "evidence_binding": {
            "evidence_id": "e1",
            "quote": "In HEK293T cells, kinase X increased the phosphorylation "
                     "of Y (Fig. 2B).",
            "quote_type": "verbatim",
            "location": {"page": 3, "section": "Results", "paragraph": 2,
                         "sentence": 1, "figure": None, "table": None,
                         "equation": None,
                         "pointer": "p.3, Results, para 2, sent 1"},
            "relation_to_assertion": "direct",
            "sufficiency": {"judgment": "sufficient",
                            "reason": "quote states the causal relation verbatim",
                            "minimality_note": "single sentence carrying "
                                               "subject+verb+object"}
        },
        "provenance": {"source_id": "src-1", "evidence_id": "e1",
                       "assertion_id": "a1",
                       "chain": ["a1", "e1", "src-1"]},
        "status": "supported"
    }


EXAMPLE_TEXT = ("In HEK293T cells, kinase X increased the phosphorylation of Y "
                "(Fig. 2B). Kinase Z did not change it.\n")


def self_test():
    vocab = build_vocab(None)
    clean = {"schema_version": SCHEMA_VERSION, "case_id": "EXAMPLE",
             "status": "success", "sources": [_example_source()],
             "assertions": [_example_assertion()]}
    errors, warnings, checks, counts, issues = validate(clean, vocab,
                                                        text=EXAMPLE_TEXT)
    print("== self-test: clean example ==")
    print(json.dumps({"errors": errors, "warnings": warnings, "counts": counts,
                      "checks": len(checks), "issues": issues},
                     ensure_ascii=False, indent=2))

    # A broken draft exercising the failure paths.
    a_bad_coord = _example_assertion()
    a_bad_coord["assertion_id"] = "a2"
    a_bad_coord["text"] = "Kinase X increases Y and decreases Z"
    a_bad_coord["evidence_binding"]["evidence_id"] = "e2"
    a_bad_coord["provenance"] = {"source_id": "src-1", "evidence_id": "e2",
                                 "assertion_id": "a2",
                                 "chain": ["a2", "e2", "src-1"]}
    a_missing_src = _example_assertion()
    a_missing_src["assertion_id"] = "a3"
    a_missing_src["provenance"] = {"source_id": "src-9", "evidence_id": "e1",
                                   "assertion_id": "a3",
                                   "chain": ["a3", "e1", "src-9"]}
    bad = {"schema_version": SCHEMA_VERSION, "case_id": "EXAMPLE",
           "status": "success", "sources": [_example_source()],
           "assertions": [a_bad_coord, a_missing_src]}
    errs, warns, checks2, counts2, issues2 = validate(bad, vocab, text=EXAMPLE_TEXT)
    print("== self-test: broken draft ==")
    print(json.dumps({"errors": errs, "warnings": warns, "counts": counts2,
                      "issues": issues2}, ensure_ascii=False, indent=2))

    print("== self-test: decompose ==")
    scan = scan_sentence("Drug A and Drug B both increased survival in mice, "
                         "which led to prolonged remission.")
    print(json.dumps(scan, ensure_ascii=False, indent=2))

    ok = (len(errors) == 0 and len(warnings) == 0
          and any("coordination" in w.lower() or "coordinating" in w.lower()
                  for w in warns)
          and any("src-9" in e for e in errs)
          and len(scan["suggested_split_units"]) >= 2)
    print("== self-test verdict ==", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")

    pv = sub.add_parser("validate", help="validate a result.json draft")
    pv.add_argument("--result", required=True, help="draft result.json")
    pv.add_argument("--schema", default=None, help="optional schema for enums")
    pv.add_argument("--text", default=None,
                    help="extracted paper text (UTF-8); used to verify quotes")
    pv.add_argument("--out", default=None, help="write report JSON here")

    pe = sub.add_parser("export", help="validate and re-emit normalized result.json")
    pe.add_argument("--result", required=True)
    pe.add_argument("--out", required=True, help="normalized result.json path")
    pe.add_argument("--schema", default=None)
    pe.add_argument("--text", default=None)
    pe.add_argument("--report", default=None, help="write validation report here")

    pd = sub.add_parser("decompose", help="heuristic marker scan of one sentence")
    pd.add_argument("--text", required=True, help="one source sentence")
    pd.add_argument("--json", action="store_true", help="emit compact JSON")

    parser.add_argument("--self-test", action="store_true",
                        help="run synthetic EXAMPLE through validate+decompose")

    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if args.command == "decompose":
        scan = scan_sentence(args.text)
        print(json.dumps(scan, ensure_ascii=False,
                         indent=(None if args.json else 2)))
        return 0

    vocab = build_vocab(args.schema)

    if args.command in ("validate", "export"):
        result = _load_json(args.result)
        text = None
        if args.text:
            with open(args.text, "r", encoding="utf-8") as fh:
                text = fh.read()
        errors, warnings, checks, counts, issues = validate(result, vocab, text)
        report = {"ok": not errors, "errors": errors, "warnings": warnings,
                  "checks": checks, "counts": counts, "issues": issues}
        if args.command == "validate":
            print(json.dumps(report, ensure_ascii=False, indent=2))
            if getattr(args, "out", None):
                with open(args.out, "w", encoding="utf-8") as fh:
                    json.dump(report, fh, ensure_ascii=False, indent=2)
            if errors:
                return 1
            if warnings:
                return 2
            return 0

        # export
        if args.report:
            with open(args.report, "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2)
        if errors:
            print(json.dumps({"exported": False, "errors": errors},
                             ensure_ascii=False, indent=2))
            return 1
        normalized = normalize(result)
        normalized.setdefault("quality", {})
        normalized["quality"]["checks"] = checks
        normalized["quality"]["issues"] = issues
        normalized["quality"]["summary"] = counts
        normalized = sort_keys(normalized)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(normalized, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(json.dumps({"exported": True, "out": args.out,
                          "errors": len(errors), "warnings": len(warnings),
                          "counts": counts}, ensure_ascii=False, indent=2))
        return 2 if warnings else 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
