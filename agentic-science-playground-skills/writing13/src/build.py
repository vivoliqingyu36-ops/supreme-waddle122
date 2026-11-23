#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build.py — LaTeX compile loop, log triage, and convergence report.

Standard library only.  It invokes AT MOST the TeX binaries expected at runtime:
``pdflatex`` / ``xelatex`` / ``lualatex`` (one engine), ``bibtex`` / ``biber``
(bibliography tool), and ``latexmk`` (optional wrapper that decides passes).
No other external process is spawned, so the script runs on a bare TeX Live /
MiKTeX image.

What it does
------------
1. Detects the main .tex file (the one holding ``\\documentclass`` and not
   ``\\input``/``\\include``d by another file).
2. Decides whether a bibliography tool is needed (``\\bibliography``,
   ``\\cite``, ``\\nocite``, or an existing ``.bbl``).
3. Runs a controlled pass sequence and stops when the build *converges*:
   the auxiliary files (``.aux``, ``.toc``, ``.lof``, ``.lot``, ``.bbl``,
   ``.out``) are byte-identical between two consecutive engine passes AND the
   log no longer contains "Rerun to get ..." messages AND no reference/citation
   stays undefined.
4. Parses ``jobname.log`` for EVERY error and warning, locating each one to
   ``file:line`` where the engine reported it (``-file-line-error``), and
   classifies each into a fix category (missing class/package/font, undefined
   control sequence, undefined reference/citation, bad math, table overflow,
   runaway argument, capacity exceeded, ...).
5. Extracts the package/font inventory from the log (``Package: name date ver``
   and ``File: font.ext`` / ``Using font ...``) so the build record is
   reproducible.
6. Writes a structured JSON build report to ``--report`` (default
   ``build_report.json``) and mirrors it on stdout.

Exit codes
----------
0  converged build (no error lines; references/citations all resolved)
1  engine ran but the build did NOT converge (errors remain, rerun messages
   persist, or references stay undefined past --max-passes)
2  environment/usage problem (engine not found, no main file, bad arguments)

The JSON report is always written (when possible) even on failure, so a caller
can read the exact error list, ``category`` per error, and the fix hint instead
of stopping at the first message.

Usage examples
--------------
    python3 build.py --workdir . --main main.tex
    python3 build.py --workdir . --main main.tex --engine xelatex --max-passes 6
    python3 build.py --workdir . --latexmk
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

SCHEMA_VERSION = "1.0"
AUX_EXTS = (".aux", ".toc", ".lof", ".lot", ".bbl", ".out")
BROKEN_REF_CATEGORIES = {"UNDEFINED_REFERENCE", "UNDEFINED_CITATION", "MULTIPLY_DEFINED_LABEL"}

# ---------------------------------------------------------------------------
# Diagnostic taxonomy.  ``classify()`` maps a LaTeX diagnostic message to a
# stable category + human-readable root-cause hint used by SKILL.md.
# ---------------------------------------------------------------------------
CATEGORY_HINTS = {
    "MISSING_CLASS": "A .cls template file is absent. Locate the class file, put it on TEXINPUTS, or switch templates.",
    "MISSING_PACKAGE": "A .sty package is absent. Install it (tlmgr) or use an equivalent package; record the change.",
    "MISSING_FONT": "A font is absent. Install the font or map to an available one; record the substitution.",
    "UNDEFINED_CONTROL_SEQUENCE": "A command/environment is undefined: typo, missing package, or wrong engine.",
    "UNDEFINED_REFERENCE": "A \\ref/\\pageref targets a label that is not defined. Often a convergence or missing-\\label issue.",
    "UNDEFINED_CITATION": "A \\cite key has no .bib entry, or BibTeX/biber was not run.",
    "MULTIPLY_DEFINED_LABEL": "Two \\label commands share the same key. Rename one.",
    "BAD_MATH": "Math-mode delimiter/brace/subscript problem. Check $...$, \\(...\\), ^/_ usage.",
    "TABLE_OVERFLOW": "Tabular is too wide or a dimension exploded. Fix column widths / use tabularx / longtable.",
    "RUNAWAY_ARGUMENT": "Unbalanced braces or a macro argument not terminated.",
    "FILE_ENDED_SCANNING": "Unclosed environment or brace at end of input.",
    "CAPACITY_EXCEEDED": "TeX memory limit hit; restructure the offending construct (e.g. too-deep nesting).",
    "EMERGENCY_STOP": "Fatal abort. See preceding error lines for the real root cause.",
    "OTHER": "Unclassified diagnostic; quote the full message verbatim in the report.",
}


def classify(message: str) -> str:
    m = message or ""
    low = m.lower()
    if "not found" in low and ".cls" in m:
        return "MISSING_CLASS"
    if ".sty" in m and ("not found" in low or "not available" in low):
        return "MISSING_PACKAGE"
    if "font" in low and ("not found" in low or "not loadable" in low or "cannot be found" in low or "not available" in low):
        return "MISSING_FONT"
    if "undefined control sequence" in low:
        return "UNDEFINED_CONTROL_SEQUENCE"
    if "reference" in low and "undefined" in low:
        return "UNDEFINED_REFERENCE"
    if "citation" in low and "undefined" in low:
        return "UNDEFINED_CITATION"
    if "multiply defined" in low:
        return "MULTIPLY_DEFINED_LABEL"
    if ("missing $ inserted" in low or "missing } inserted" in low or "extra }" in low
            or "double superscript" in low or "double subscript" in low
            or "extra alignment tab" in low or "misplaced alignment tab" in low
            or "display math should end" in low or "bad math environment" in low
            or "missing \\right" in low or "extra \\right" in low or "missing \\left" in low):
        return "BAD_MATH"
    if "dimension too large" in low:
        return "TABLE_OVERFLOW"
    if "runaway argument" in low:
        return "RUNAWAY_ARGUMENT"
    if "file ended while scanning" in low or "file ended within" in low:
        return "FILE_ENDED_SCANNING"
    if "tex capacity exceeded" in low or "capacity exceeded" in low:
        return "CAPACITY_EXCEEDED"
    if "emergency stop" in low:
        return "EMERGENCY_STOP"
    return "OTHER"


# Error lines emitted with ``-file-line-error``:  "./main.tex:42: Undefined control sequence."
ERR_LINE_RE = re.compile(
    r"^(?:\./)?(?P<file>[A-Za-z0-9_./\\:-]+?\.[A-Za-z]{1,8}):(?P<line>\d+):\s*(?P<msg>.*)$"
)
# Classic form without -file-line-error:  "! LaTeX Error: File `x.sty' not found."
BANG_RE = re.compile(r"^!\s*(?P<msg>.*)$")
# Context form:  "l.42 ..."
L_RE = re.compile(r"^l\.(?P<line>\d+)\s+(?P<text>.*)$")
PKG_RE = re.compile(
    r"^Package:\s+(?P<name>[A-Za-z0-9@._-]+)\s+(?P<date>\d{4}/\d{2}/\d{2})\s+(?P<ver>v?[0-9A-Za-z][0-9A-Za-z.-]*)"
)
FONT_FILE_RE = re.compile(r"^File:\s+(?P<font>\S+\.(?:pfb|pfa|ttf|otf|woff2?))")
FONT_USE_RE = re.compile(r"Using font\s+[`'](?P<font>[^'\s]+)'")
RERUN_RE = re.compile(r"Rerun to get (cross-references|citations|references|the cross-references)")

WARN_PATTERNS = [
    ("UNDEFINED_REFERENCE", re.compile(r"Reference [`'](?P<key>[^']+)' on page \d+ undefined"), "Missing or not-yet-resolved \\label."),
    ("UNDEFINED_CITATION", re.compile(r"Citation [`'](?P<key>[^']+)' on page \d+ undefined"), "Missing .bib entry or BibTeX/biber not run."),
    ("MULTIPLY_DEFINED_LABEL", re.compile(r"Label [`'](?P<key>[^']+)' multiply defined"), "Duplicate \\label key."),
    ("OVERFULL", re.compile(r"Overfull \\hbox \((?P<pt>[\d.]+)pt too wide\)"), "Content wider than the box; check tables/figures/math."),
    ("UNDERFULL", re.compile(r"Underfull \\hbox \((badness \d+)\)"), "Stretched/loose line; usually cosmetic."),
    ("RERUN", RERUN_RE, "Another pass is required for cross-references/citations to settle."),
]


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def sh(command: list, cwd: str, timeout: int = 600) -> dict:
    """Run one command; never raise. Returns command, exit_code, out/err, seconds."""
    start = time.time()
    try:
        proc = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return {
            "command": " ".join(command),
            "exit_code": proc.returncode,
            "stdout": proc.stdout.decode("utf-8", "replace"),
            "stderr": proc.stderr.decode("utf-8", "replace"),
            "duration_s": round(time.time() - start, 3),
        }
    except subprocess.TimeoutExpired:
        return {"command": " ".join(command), "exit_code": 124, "stdout": "", "stderr": "TIMEOUT", "duration_s": round(time.time() - start, 3)}
    except OSError as exc:  # engine missing, permission denied, ...
        return {"command": " ".join(command), "exit_code": 127, "stdout": "", "stderr": str(exc), "duration_s": round(time.time() - start, 3)}


def find_binary(name: str) -> str | None:
    return shutil.which(name)


def read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def hash_file(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_main(workdir: str) -> str | None:
    """Return the main .tex path, or None when ambiguous/absent."""
    tex_files = []
    for root, _dirs, files in os.walk(workdir):
        for f in files:
            if f.lower().endswith(".tex") and not f.lower().startswith("."):
                tex_files.append(os.path.join(root, f))
    if not tex_files:
        return None
    candidates = [p for p in tex_files if "\\documentclass" in read_text(p)]
    if not candidates:
        candidates = [p for p in tex_files if "\\begin{document}" in read_text(p)]
    if len(candidates) == 1:
        return candidates[0]
    # Multiple candidates: drop any file referenced via \input/\include from another.
    referenced = set()
    for p in candidates:
        for m in re.finditer(r"\\(?:input|include)\{([^}]+)\}", read_text(p)):
            base = m.group(1).strip()
            if not base.endswith(".tex"):
                base += ".tex"
            for q in candidates:
                if q.endswith(base):
                    referenced.add(q)
    unreferenced = [p for p in candidates if p not in referenced]
    if len(unreferenced) == 1:
        return unreferenced[0]
    return None


def needs_bibtex(workdir: str, main_file: str) -> bool:
    for root, _dirs, files in os.walk(workdir):
        for f in files:
            if f.lower().endswith((".tex", ".aux")):
                body = read_text(os.path.join(root, f))
                if "\\bibliography{" in body or "\\bibdata{" in body or "\\cite" in body or "\\nocite" in body:
                    return True
    return False


def snapshot(workdir: str, jobname: str) -> dict:
    return {ext: hash_file(os.path.join(workdir, jobname + ext)) for ext in AUX_EXTS}


def engine_version(engine_bin: str) -> str:
    r = sh([engine_bin, "--version"], os.getcwd(), timeout=60)
    first = (r["stdout"] or "").splitlines()
    return first[0].strip() if first else "unknown"


def distro_name(engine_bin: str) -> str:
    r = sh([engine_bin, "--version"], os.getcwd(), timeout=60)
    text = (r["stdout"] or "") + "\n" + (r["stderr"] or "")
    m = re.search(r"TeX Live\s+\d{4}[^\n]*", text)
    if m:
        return m.group(0).strip().rstrip(",)")
    m = re.search(r"MiKTeX[^\n]*", text)
    if m:
        return m.group(0).strip().rstrip(",)")
    return text.splitlines()[0].strip() if text.strip() else "unknown"


def _skip_noise(msg: str) -> bool:
    s = (msg or "").strip()
    return s.startswith("==>") or "fatal error occurred" in s.lower() or "no output pdf" in s.lower()


def parse_log(log_path: str) -> dict:
    """Parse a .log into errors, warnings, packages, fonts, rerun flag."""
    text = read_text(log_path)
    lines = text.splitlines()
    errors = []
    warnings = []
    packages = {}
    fonts = []
    rerun_needed = False

    for idx, line in enumerate(lines):
        # --- file:line error form (only errors carry this prefix) ---
        em = ERR_LINE_RE.match(line)
        if em:
            msg = em.group("msg").strip()
            if _skip_noise(msg):
                continue
            errors.append({
                "file": em.group("file").lstrip("./"),
                "line": int(em.group("line")),
                "message": msg,
                "category": classify(msg),
            })
            continue
        # --- bang form:  "! Undefined control sequence." / "! LaTeX Error: ..." ---
        bm = BANG_RE.match(line)
        if bm:
            msg = bm.group("msg").strip()
            if _skip_noise(msg):
                continue
            line_no = 0
            for j in range(idx + 1, min(idx + 8, len(lines))):
                lm = L_RE.match(lines[j])
                if lm:
                    line_no = int(lm.group("line"))
                    break
            errors.append({"file": "<main>", "line": line_no, "message": msg, "category": classify(msg)})
            continue
        # --- package inventory:  "Package: geometry 2020/01/02 v5.9 Geometry" ---
        pm = PKG_RE.match(line)
        if pm:
            packages[pm.group("name")] = {"name": pm.group("name"), "date": pm.group("date"), "version": pm.group("ver")}
            continue
        # --- font inventory ---
        fm = FONT_FILE_RE.match(line)
        if fm:
            fonts.append({"name": fm.group("font"), "kind": "file"})
            continue
        fu = FONT_USE_RE.match(line)
        if fu:
            fonts.append({"name": fu.group("font"), "kind": "declared"})
            continue
        # --- warnings ---
        for cat, pat, hint in WARN_PATTERNS:
            if pat.search(line):
                warnings.append({"category": cat, "message": line.strip(), "hint": hint})
                break
        if RERUN_RE.search(line):
            rerun_needed = True

    # De-duplicate errors (a message may be emitted twice across passes).
    seen_e = set()
    dedup_errors = []
    for e in errors:
        key = (e["file"], e["line"], re.sub(r"`.+'", "`<x>'", e["message"]))
        if key not in seen_e:
            seen_e.add(key)
            dedup_errors.append(e)

    # De-duplicate warnings that differ only in the cite/ref key.
    seen_w = set()
    dedup_warn = []
    for w in warnings:
        key = (w["category"], re.sub(r"[`']([^']+)'", "'<key>'", w["message"]))
        if key not in seen_w:
            seen_w.add(key)
            dedup_warn.append(w)

    dedup_errors.sort(key=lambda e: (e["file"], e["line"]))
    return {
        "errors": dedup_errors,
        "warnings": dedup_warn,
        "packages": sorted(packages.values(), key=lambda p: p["name"].lower()),
        "fonts": fonts,
        "rerun_needed": rerun_needed,
    }


def broken_ref_count(warnings: list) -> int:
    return sum(1 for w in warnings if w["category"] in BROKEN_REF_CATEGORIES)


def build_report(payload: dict) -> None:
    report_path = payload.get("_report_path")
    if report_path:
        payload = {k: v for k, v in payload.items() if k != "_report_path"}
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    else:
        payload = {k: v for k, v in payload.items() if k != "_report_path"}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LaTeX compile loop + log triage + convergence report.")
    ap.add_argument("--workdir", default=".", help="Project directory (default: current).")
    ap.add_argument("--main", help="Main .tex file (auto-detected when omitted).")
    ap.add_argument("--engine", default="pdflatex", choices=["pdflatex", "xelatex", "lualatex"],
                    help="TeX engine (default: pdflatex).")
    ap.add_argument("--bib", default="auto", choices=["auto", "bibtex", "biber", "none"],
                    help="Bibliography tool (default: auto-detect).")
    ap.add_argument("--latexmk", action="store_true", help="Use latexmk to decide passes instead of manual sequence.")
    ap.add_argument("--max-passes", type=int, default=5, help="Maximum engine passes in manual mode (default: 5).")
    ap.add_argument("--report", default="build_report.json", help="JSON report path (default: build_report.json).")
    args = ap.parse_args(argv)

    def fail(msg: str, code: int = 2) -> int:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "generated_at": now(), "error": msg}, ensure_ascii=False, indent=2))
        return code

    workdir = os.path.abspath(args.workdir)
    if not os.path.isdir(workdir):
        return fail(f"workdir does not exist: {workdir}")

    engine_bin = find_binary(args.engine)
    if not engine_bin:
        return fail(f"engine not found: {args.engine}")

    main_file = args.main or detect_main(workdir)
    if not main_file:
        return fail("cannot detect a unique main .tex; pass --main")
    main_file = os.path.join(workdir, main_file) if not os.path.isabs(main_file) else main_file
    if not os.path.isfile(main_file):
        return fail(f"main file not found: {main_file}")

    jobname = os.path.splitext(os.path.basename(main_file))[0]
    report_path = os.path.abspath(args.report)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now(),
        "jobname": jobname,
        "main_file": os.path.relpath(main_file, workdir),
        "engine": args.engine,
        "distro": distro_name(engine_bin),
        "engine_version": engine_version(engine_bin),
        "commands": [],
        "passes": [],
        "converged": False,
        "rerun_needed": False,
        "error_count": 0,
        "warning_count": 0,
        "broken_reference_count": 0,
        "errors": [],
        "warnings": [],
        "packages": [],
        "fonts": [],
        "bib_tool": None,
        "aux_snapshot": {},
        "pdf_bytes": None,
        "reproducibility": {
            "exact_commands": [],
            "clean_rebuild_advised": True,
            "note": "Re-run after deleting *.aux *.toc *.lof *.lot *.bbl *.out to confirm a clean build reproduces the same PDF (compare PDF hashes ignoring /CreationDate, /ModDate and /ID)."
        },
        "_report_path": report_path,
    }

    use_bib = args.bib
    if use_bib == "auto":
        use_bib = "bibtex" if needs_bibtex(workdir, main_file) else "none"
    bib_bin = find_binary(use_bib) if use_bib in ("bibtex", "biber") else None
    payload["bib_tool"] = use_bib if use_bib != "none" else None

    run_engine = [engine_bin, "-interaction=nonstopmode", "-file-line-error", "-recorder"]

    def finalize(parsed: dict, converged: bool) -> int:
        payload["errors"] = parsed["errors"]
        payload["warnings"] = parsed["warnings"]
        payload["packages"] = parsed["packages"]
        payload["fonts"] = parsed["fonts"]
        payload["rerun_needed"] = parsed["rerun_needed"]
        payload["error_count"] = len(parsed["errors"])
        payload["warning_count"] = len(parsed["warnings"])
        payload["broken_reference_count"] = broken_ref_count(parsed["warnings"])
        payload["converged"] = converged
        payload["pdf_bytes"] = os.path.getsize(os.path.join(workdir, jobname + ".pdf")) if os.path.isfile(os.path.join(workdir, jobname + ".pdf")) else None
        payload["reproducibility"]["exact_commands"] = [c["command"] for c in payload["commands"]]
        build_report(payload)
        return 0 if converged else 1

    # --- latexmk mode -------------------------------------------------------
    if args.latexmk:
        latexmk_bin = find_binary("latexmk")
        if not latexmk_bin:
            return fail("latexmk requested but not found")
        cmd = [latexmk_bin, "-pdf", "-interaction=nonstopmode", "-file-line-error",
               f"-pdflatex={engine_bin} -interaction=nonstopmode -file-line-error -recorder %O %S",
               os.path.basename(main_file)]
        r = sh(cmd, workdir)
        payload["commands"].append(r)
        payload["passes"].append({"tool": "latexmk", "command": r["command"], "exit_code": r["exit_code"], "duration_s": r["duration_s"]})
        parsed = parse_log(os.path.join(workdir, jobname + ".log"))
        converged = (r["exit_code"] == 0 and len(parsed["errors"]) == 0
                     and not parsed["rerun_needed"] and broken_ref_count(parsed["warnings"]) == 0)
        return finalize(parsed, converged)

    # --- manual pass sequence ----------------------------------------------
    def run_pass(desc: str) -> dict:
        r = sh(list(run_engine) + [os.path.basename(main_file)], workdir)
        r["desc"] = desc
        payload["commands"].append(r)
        payload["passes"].append({"desc": desc, "command": r["command"], "exit_code": r["exit_code"], "duration_s": r["duration_s"]})
        return r

    def run_bib() -> dict:
        r = sh([bib_bin, jobname], workdir)
        payload["commands"].append(r)
        payload["passes"].append({"desc": use_bib, "command": r["command"], "exit_code": r["exit_code"], "duration_s": r["duration_s"]})
        if r["exit_code"] not in (0, 1):
            payload["warnings"].append({"category": "BIBTOOL_ERROR", "message": (r["stderr"] or "").strip()[:400], "hint": "Bibliography tool failed; check .bib syntax and \\bibliography{...}."})
        return r

    pass_no = 0
    converged = False
    prev_snap = snapshot(workdir, jobname)

    while pass_no < args.max_passes:
        pass_no += 1
        run_pass(f"pass{pass_no}: {args.engine}")
        if use_bib in ("bibtex", "biber") and bib_bin and pass_no == 1:
            run_bib()

        cur_snap = snapshot(workdir, jobname)
        parsed = parse_log(os.path.join(workdir, jobname + ".log"))
        stable = all(cur_snap.get(ext) == prev_snap.get(ext) for ext in AUX_EXTS)
        if stable and not parsed["rerun_needed"]:
            # Once aux files are stable and nothing asks for a rerun, further
            # passes cannot fix anything; exit the loop and grade convergence.
            converged = len(parsed["errors"]) == 0 and broken_ref_count(parsed["warnings"]) == 0
            break
        prev_snap = cur_snap

    parsed = parse_log(os.path.join(workdir, jobname + ".log"))
    payload["aux_snapshot"] = snapshot(workdir, jobname)
    return finalize(parsed, converged)


if __name__ == "__main__":
    sys.exit(main())
