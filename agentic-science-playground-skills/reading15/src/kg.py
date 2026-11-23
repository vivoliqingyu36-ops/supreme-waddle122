#!/usr/bin/env python3
"""
Literature knowledge-graph validator and query engine (reading15).

Stdlib-only. Two jobs:

  1. validate  -- check a graph JSON (nodes/edges + optional alignments/sources)
                  for structural problems, missing evidence, dangling endpoints,
                  forbidden weak-evidence edges, duplicate/homonym nodes.
  2. query     -- run graph queries (neighborhood/trace/path/node_by_name/
                  node_by_type/edges_by_type) and emit evidence-bound result
                  subgraphs.

Exit codes (validate only): 0 = clean, 1 = errors, 2 = warnings only.

The controlled vocabularies are read from schema/kg_schema.json when available
and fall back to the constants below otherwise. Formal edges may only carry
strength `direct` or `paraphrase`; `cooccurrence` / `speculation` / `inferred`
claims belong in `non_edges` and are rejected from the edge table.
"""

import argparse
import json
import re
import sys
from collections import defaultdict, deque

# ---------------------------------------------------------------------------
# Fallback controlled vocabularies (mirror schema/kg_schema.json $defs)
# ---------------------------------------------------------------------------
ENTITY_TYPES = {"researcher", "material", "method", "task", "metric", "conclusion"}
RELATION_TYPES = {"USES", "COMPARES", "OUTPERFORMS", "SUPPORTS", "CONTRADICTS",
                  "SAME_AS", "DISTINCT_FROM"}
EVIDENCE_STRENGTHS = {"direct", "paraphrase", "inferred", "cooccurrence", "speculation"}
DIRECTIONS = {"out", "in"}
QUERY_TYPES = {"neighborhood", "trace", "path", "node_by_name", "node_by_type",
               "edges_by_type"}
# These must never appear as the strength of a formal edge.
FORBIDDEN_EDGE_STRENGTHS = {"cooccurrence", "speculation", "inferred"}

PAGE_PATTERN = re.compile(r"^\s*(?:page|p\.?)\s*[0-9]+\s*$", re.IGNORECASE)


def norm_name(s):
    """Normalize a canonical name for duplicate/homonym detection."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def load_enums(schema_path):
    """Extract enum vocabularies from a JSON-Schema file. Returns merged dict."""
    enums = {}
    if not schema_path:
        return enums
    try:
        with open(schema_path, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
    except Exception as exc:  # pragma: no cover - schema is optional
        print(f"[warn] could not load schema {schema_path}: {exc}", file=sys.stderr)
        return enums
    defs = schema.get("$defs") or schema.get("definitions") or {}
    for key, defn in defs.items():
        if isinstance(defn, dict) and "enum" in defn:
            enums[key] = defn["enum"]
    return enums


def build_vocab(schema_path):
    enums = load_enums(schema_path)
    return {
        "entity_type": enums.get("entity_type") or sorted(ENTITY_TYPES),
        "relation_type": enums.get("relation_type") or sorted(RELATION_TYPES),
        "evidence_strength": enums.get("evidence_strength") or sorted(EVIDENCE_STRENGTHS),
        "direction": ["out", "in"],
        "query_type": enums.get("query_type") or sorted(QUERY_TYPES),
    }


def load_graph(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(graph, vocab):
    errors, warnings, info = [], [], []

    if not isinstance(graph, dict):
        return (["graph root must be a JSON object"], [], [], {})
    if "nodes" not in graph or "edges" not in graph:
        errors.append("graph must contain 'nodes' and 'edges' arrays")

    nodes = graph.get("nodes", []) or []
    edges = graph.get("edges", []) or []
    alignments = graph.get("alignments", []) or []
    sources = graph.get("sources", []) or []

    if not isinstance(nodes, list):
        errors.append("'nodes' must be an array")
        nodes = []
    if not isinstance(edges, list):
        errors.append("'edges' must be an array")
        edges = []

    # ---- nodes ----
    node_ids = {}
    for i, n in enumerate(nodes):
        where = f"node[{i}]"
        if not isinstance(n, dict):
            errors.append(f"{where} is not an object")
            continue
        nid = n.get("id")
        if not nid or not isinstance(nid, str):
            errors.append(f"{where} missing string 'id'")
        elif nid in node_ids:
            errors.append(f"duplicate node id '{nid}' (also at node[{node_ids[nid]}])")
        else:
            node_ids[nid] = i

        for field in ("type", "canonical_name", "source_id", "paragraph_id", "quote"):
            if not isinstance(n.get(field), str) or not n[field].strip():
                errors.append(f"{where} ('{nid or '?'}') missing/empty '{field}'")
        if n.get("type") not in vocab["entity_type"]:
            errors.append(f"{where} ('{nid or '?'}') unknown entity_type '{n.get('type')}'")
        if n.get("strength") and n.get("strength") not in vocab["evidence_strength"]:
            errors.append(f"{where} ('{nid or '?'}') unknown strength '{n.get('strength')}'")
        if n.get("paragraph_id") and PAGE_PATTERN.match(n.get("paragraph_id", "")):
            warnings.append(
                f"{where} ('{nid or '?'}') paragraph_id '{n['paragraph_id']}' looks like a "
                f"page number; JATS paragraph IDs must be used, never PDF pages")
        q = n.get("quote", "")
        if q and len(q) > 500:
            warnings.append(f"{where} ('{nid or '?'}') quote is {len(q)} chars (>500); keep it short")
        if nid and "aliases" in n and n.get("canonical_name") and \
                norm_name(n["canonical_name"]) in {norm_name(a) for a in n.get("aliases", [])}:
            warnings.append(f"{where} ('{nid}') alias duplicates its canonical_name")

    # ---- edges ----
    edge_ids = {}
    adjacency = defaultdict(list)  # node id -> list of (neighbor, edge)
    for i, e in enumerate(edges):
        where = f"edge[{i}]"
        if not isinstance(e, dict):
            errors.append(f"{where} is not an object")
            continue
        eid = e.get("id")
        if not eid or not isinstance(eid, str):
            errors.append(f"{where} missing string 'id'")
        elif eid in edge_ids:
            errors.append(f"duplicate edge id '{eid}' (also at edge[{edge_ids[eid]}])")
        else:
            edge_ids[eid] = i

        for field in ("type", "source", "target", "direction", "source_id",
                      "paragraph_id", "quote", "strength"):
            if not isinstance(e.get(field), str) or not e[field].strip():
                errors.append(f"{where} ('{eid or '?'}') missing/empty '{field}'")
        if e.get("type") not in vocab["relation_type"]:
            errors.append(f"{where} ('{eid or '?'}') unknown relation_type '{e.get('type')}'")
        if e.get("direction") not in vocab["direction"]:
            errors.append(f"{where} ('{eid or '?'}') unknown direction '{e.get('direction')}'")
        if e.get("strength") in FORBIDDEN_EDGE_STRENGTHS:
            errors.append(
                f"{where} ('{eid or '?'}') strength '{e['strength']}' is forbidden on a formal "
                f"edge; move it to 'non_edges' (co-occurrence/speculation/inference are not evidence)")
        elif e.get("strength") and e.get("strength") not in vocab["evidence_strength"]:
            errors.append(f"{where} ('{eid or '?'}') unknown strength '{e.get('strength')}'")

        s, t = e.get("source"), e.get("target")
        if s and t:
            if s not in node_ids:
                errors.append(f"{where} ('{eid or '?'}') source '{s}' is not a node id")
            if t not in node_ids:
                errors.append(f"{where} ('{eid or '?'}') target '{t}' is not a node id")
            if s == t:
                warnings.append(f"{where} ('{eid or '?'}') is a self-loop ({s} -> {t})")
            if s in node_ids and t in node_ids:
                adjacency[s].append((t, e))
                adjacency[t].append((s, e))

    # ---- duplicate canonical names / homonyms ----
    by_name = defaultdict(list)
    for n in nodes:
        if isinstance(n, dict) and n.get("canonical_name") and n.get("id"):
            by_name[norm_name(n["canonical_name"])].append(n["id"])
    for name, ids in by_name.items():
        if len(ids) > 1:
            connected = set()
            for e in edges:
                if not isinstance(e, dict):
                    continue
                if e.get("type") in ("SAME_AS", "DISTINCT_FROM") and \
                        e.get("source") in ids and e.get("target") in ids:
                    connected.add((e.get("source"), e.get("target")))
            unaligned = []
            for a in range(len(ids)):
                for b in range(a + 1, len(ids)):
                    if (ids[a], ids[b]) not in connected and (ids[b], ids[a]) not in connected:
                        unaligned.append(f"{ids[a]}<->{ids[b]}")
            if unaligned:
                warnings.append(
                    f"nodes share canonical name '{name}': {', '.join(unaligned)} have no "
                    f"SAME_AS/DISTINCT_FROM edge; record merge justification or keep-separate note")

    # ---- SAME_AS / DISTINCT_FROM need an alignment record ----
    if alignments:
        align_ids = set()
        for a in alignments:
            if isinstance(a, dict):
                align_ids.update(a.get("merged_ids") or [])
                align_ids.update(a.get("ids") or [])
                if a.get("canonical_id"):
                    align_ids.add(a["canonical_id"])
        for e in edges:
            if isinstance(e, dict) and e.get("type") in ("SAME_AS", "DISTINCT_FROM"):
                if e.get("source") not in align_ids or e.get("target") not in align_ids:
                    warnings.append(
                        f"edge '{e.get('id')}' is {e.get('type')} but its endpoints are not "
                        f"covered by an alignments entry; add justification/conflict_note")
    else:
        for e in edges:
            if isinstance(e, dict) and e.get("type") in ("SAME_AS", "DISTINCT_FROM"):
                warnings.append(
                    f"edge '{e.get('id')}' is {e.get('type')} but graph has no 'alignments'; "
                    f"provide justification (merge) or conflict_note (keep_separate)")

    # ---- sources coverage ----
    if sources:
        source_ids = {s.get("source_id") for s in sources if isinstance(s, dict)}
        for n in nodes:
            if isinstance(n, dict) and n.get("source_id") and n["source_id"] not in source_ids:
                warnings.append(f"node '{n.get('id')}' source_id '{n['source_id']}' not in sources")
        for e in edges:
            if isinstance(e, dict) and e.get("source_id") and e["source_id"] not in source_ids:
                warnings.append(f"edge '{e.get('id')}' source_id '{e['source_id']}' not in sources")

    counts = {"nodes": len([n for n in nodes if isinstance(n, dict)]),
              "edges": len([e for e in edges if isinstance(e, dict)]),
              "sources": len(sources), "alignments": len(alignments)}
    return errors, warnings, info, counts


# ---------------------------------------------------------------------------
# Query engine
# ---------------------------------------------------------------------------
def node_by_id(nodes, nid):
    for n in nodes:
        if isinstance(n, dict) and n.get("id") == nid:
            return n
    return None


def edge_by_id(edges, eid):
    for e in edges:
        if isinstance(e, dict) and e.get("id") == eid:
            return e
    return None


def evidence_of_node(n):
    return {
        "element": n.get("id"),
        "kind": "node",
        "type": n.get("type"),
        "source_id": n.get("source_id"),
        "paragraph_id": n.get("paragraph_id"),
        "quote": n.get("quote"),
        "strength": n.get("strength", "direct"),
    }


def evidence_of_edge(e):
    return {
        "element": e.get("id"),
        "kind": "edge",
        "type": e.get("type"),
        "source_id": e.get("source_id"),
        "paragraph_id": e.get("paragraph_id"),
        "quote": e.get("quote"),
        "strength": e.get("strength", "direct"),
    }


def run_query(q, graph, vocab):
    nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict)]
    edges = [e for e in graph.get("edges", []) if isinstance(e, dict)]
    params = q.get("params") or {}
    qtype = q.get("type")
    result = {"id": q.get("id"), "type": qtype, "params": params,
              "status": "empty", "result_nodes": [], "result_edges": [], "evidence": []}
    if q.get("question"):
        result["question"] = q["question"]

    adjacency = defaultdict(list)
    for e in edges:
        adjacency[e.get("source")].append((e.get("target"), e))
        adjacency[e.get("target")].append((e.get("source"), e))

    if qtype == "neighborhood":
        start = params.get("node")
        max_depth = int(params.get("max_depth", 1))
        if start and node_by_id(nodes, start):
            seen = {start}
            frontier = [start]
            for _ in range(max_depth):
                nxt = []
                for u in frontier:
                    for v, e in adjacency.get(u, []):
                        if v not in seen:
                            seen.add(v)
                            nxt.append(v)
                frontier = nxt
            result["result_nodes"] = [n for n in nodes if n.get("id") in seen]
            result["result_edges"] = [e for e in edges
                                      if e.get("source") in seen and e.get("target") in seen]
        else:
            result["empty_reason"] = f"start node '{start}' not found"

    elif qtype == "trace":
        el = params.get("element")
        n = node_by_id(nodes, el)
        if n:
            result["result_nodes"] = [n]
            result["result_edges"] = [e for e in edges
                                      if e.get("source") == el or e.get("target") == el]
        else:
            e = edge_by_id(edges, el)
            if e:
                result["result_edges"] = [e]
                result["result_nodes"] = [n for n in nodes
                                          if n.get("id") in (e.get("source"), e.get("target"))]
            else:
                result["empty_reason"] = f"element '{el}' not found"

    elif qtype == "path":
        src, dst = params.get("from"), params.get("to")
        max_hops = int(params.get("max_hops", 3))
        if src and dst and node_by_id(nodes, src) and node_by_id(nodes, dst):
            prev = {src: None}
            prev_edge = {}
            dq = deque([src])
            while dq and dst not in prev:
                u = dq.popleft()
                for v, e in adjacency.get(u, []):
                    if v not in prev:
                        prev[v] = u
                        prev_edge[v] = e
                        dq.append(v)
            if dst in prev:
                path = []
                cur = dst
                while cur is not None:
                    path.append(cur)
                    cur = prev[cur]
                path.reverse()
                hops = len(path) - 1
                if hops <= max_hops:
                    path_edges = []
                    for a, b in zip(path, path[1:]):
                        for v, e in adjacency.get(a, []):
                            if v == b and e.get("id") not in {x.get("id") for x in path_edges}:
                                path_edges.append(e)
                                break
                    result["result_nodes"] = [n for n in nodes if n.get("id") in path]
                    result["result_edges"] = path_edges
                else:
                    result["empty_reason"] = f"shortest path length {hops} exceeds max_hops {max_hops}"
            else:
                result["empty_reason"] = f"no path between '{src}' and '{dst}'"
        else:
            result["empty_reason"] = f"endpoint(s) not found: from='{src}' to='{dst}'"

    elif qtype == "node_by_name":
        text = (params.get("text") or "").strip().lower()
        limit = int(params.get("limit", 10))
        if text:
            hits = []
            for n in nodes:
                hay = [n.get("canonical_name", "")] + list(n.get("aliases") or [])
                if any(text in (h or "").lower() for h in hay):
                    hits.append(n)
            result["result_nodes"] = hits[:limit]
            if not hits:
                result["empty_reason"] = f"no node name/alias contains '{params.get('text')}'"
        else:
            result["empty_reason"] = "node_by_name requires params.text"

    elif qtype == "node_by_type":
        et = params.get("entity_type")
        if et and et in vocab["entity_type"]:
            result["result_nodes"] = [n for n in nodes if n.get("type") == et]
            if not result["result_nodes"]:
                result["empty_reason"] = f"no nodes of type '{et}'"
        else:
            result["empty_reason"] = f"node_by_type requires valid params.entity_type (got '{et}')"

    elif qtype == "edges_by_type":
        rel = params.get("relation")
        if rel and rel in vocab["relation_type"]:
            result["result_edges"] = [e for e in edges if e.get("type") == rel]
            involved = set()
            for e in result["result_edges"]:
                involved.add(e.get("source"))
                involved.add(e.get("target"))
            result["result_nodes"] = [n for n in nodes if n.get("id") in involved]
            if not result["result_edges"]:
                result["empty_reason"] = f"no edges of type '{rel}'"
        else:
            result["empty_reason"] = f"edges_by_type requires valid params.relation (got '{rel}')"

    else:
        result["empty_reason"] = f"unknown query type '{qtype}'"
        result["status"] = "empty"
        return result

    if result["result_nodes"] or result["result_edges"]:
        result["status"] = "answered"
        # attach evidence for every returned element, deduplicated
        seen_ev = set()
        for n in result["result_nodes"]:
            ev = evidence_of_node(n)
            key = json.dumps(ev, sort_keys=True, ensure_ascii=False)
            if key not in seen_ev:
                seen_ev.add(key)
                result["evidence"].append(ev)
        for e in result["result_edges"]:
            ev = evidence_of_edge(e)
            key = json.dumps(ev, sort_keys=True, ensure_ascii=False)
            if key not in seen_ev:
                seen_ev.add(key)
                result["evidence"].append(ev)
    else:
        result["status"] = "empty"
        if not result.get("empty_reason"):
            result["empty_reason"] = "no results"
    return result


# ---------------------------------------------------------------------------
# Self-test (synthetic EXAMPLE graph, NOT a formal case)
# ---------------------------------------------------------------------------
EXAMPLE_GRAPH = {
    "case_id": "EXAMPLE",
    "status": "success",
    "sources": [
        {"source_id": "primary", "title": "Example paper A", "doi": "10.0000/EXAMPLE.A",
         "authors": ["A. Author"], "source_hash": "0xdeadbeef", "license": "CC-BY"}
    ],
    "nodes": [
        {"id": "primary.method.001", "type": "method", "canonical_name": "citrate reduction",
         "source_id": "primary", "paragraph_id": "p-sec2-para1",
         "quote": "AuNPs were synthesized by citrate reduction.", "aliases": [],
         "strength": "direct", "note": ""},
        {"id": "primary.material.001", "type": "material", "canonical_name": "gold nanoparticles (AuNPs)",
         "source_id": "primary", "paragraph_id": "p-sec2-para1",
         "quote": "gold nanoparticles (AuNPs) of ~13 nm diameter", "aliases": ["AuNPs"],
         "strength": "direct", "note": ""},
        {"id": "primary.conclusion.001", "type": "conclusion",
         "canonical_name": "citrate reduction yields ~13 nm AuNPs",
         "source_id": "primary", "paragraph_id": "p-sec4-para2",
         "quote": "citrate reduction yielded AuNPs of about 13 nm.", "aliases": [],
         "strength": "direct", "note": ""}
    ],
    "edges": [
        {"id": "E001", "type": "USES", "source": "primary.method.001",
         "target": "primary.material.001", "direction": "out", "source_id": "primary",
         "paragraph_id": "p-sec2-para1",
         "quote": "AuNPs were synthesized by citrate reduction.", "strength": "direct",
         "conditions": "not stated", "note": ""},
        {"id": "E002", "type": "SUPPORTS", "source": "primary.material.001",
         "target": "primary.conclusion.001", "direction": "out", "source_id": "primary",
         "paragraph_id": "p-sec4-para2",
         "quote": "citrate reduction yielded AuNPs of about 13 nm.", "strength": "direct",
         "conditions": "not stated", "note": ""}
    ]
}


def self_test():
    vocab = build_vocab(None)
    errors, warnings, info, counts = validate(EXAMPLE_GRAPH, vocab)
    print("== self-test validate ==")
    print(json.dumps({"errors": errors, "warnings": warnings, "info": info,
                      "counts": counts}, ensure_ascii=False, indent=2))
    queries = [
        {"id": "Q1", "question": "Which materials does citrate reduction use?",
         "type": "neighborhood", "params": {"node": "primary.method.001", "max_depth": 1}},
        {"id": "Q2", "question": "Trace evidence for edge E001",
         "type": "trace", "params": {"element": "E001"}}
    ]
    results = [run_query(q, EXAMPLE_GRAPH, vocab) for q in queries]
    print("== self-test query ==")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")

    pv = sub.add_parser("validate", help="validate a graph JSON")
    pv.add_argument("--graph", required=True)
    pv.add_argument("--schema", default=None)
    pv.add_argument("--out", default=None, help="write report JSON here")

    pq = sub.add_parser("query", help="run queries and emit result subgraphs")
    pq.add_argument("--graph", required=True)
    pq.add_argument("--queries", required=True)
    pq.add_argument("--out", required=True)
    pq.add_argument("--schema", default=None)

    parser.add_argument("--self-test", action="store_true",
                        help="run synthetic EXAMPLE graph through validate+query")

    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    vocab = build_vocab(args.schema)

    if args.command == "validate":
        graph = load_graph(args.graph)
        errors, warnings, info, counts = validate(graph, vocab)
        report = {"errors": errors, "warnings": warnings, "info": info, "counts": counts}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2)
        if errors:
            return 1
        if warnings:
            return 2
        return 0

    if args.command == "query":
        graph = load_graph(args.graph)
        with open(args.queries, "r", encoding="utf-8") as fh:
            qdoc = json.load(fh)
        qlist = qdoc.get("queries", qdoc) if isinstance(qdoc, dict) else qdoc
        results = [run_query(q, graph, vocab) for q in qlist]
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)
        answered = sum(1 for r in results if r.get("status") == "answered")
        empty = sum(1 for r in results if r.get("status") == "empty")
        print(json.dumps({"executed": len(results), "answered": answered,
                          "empty": empty}, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
