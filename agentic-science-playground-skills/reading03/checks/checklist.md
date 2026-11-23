# Verification checklist — literature-translator

Use this checklist after every translation run, before writing `/app/output/result.json`.
Each item states the four-question mapping, the concrete check, and how to run it.

Legend: [术语稳]=term stability, [段落全]=paragraph completeness, [关系准]=relation
accuracy, [可核验]=verifiability.

## A. Input and text layer

- [ ] A1 Read `/input/case.json` and record `case_id` + every `output_contract` field. [可核验]
- [ ] A2 Read `task.md` and the material path(s); translate the actual material, never a label. [可核验]
- [ ] A3 Record the extraction method (`native-text-layer` / `pdftotext` / `pymupdf` / `pypdf` / `pdfminer` / `ocr` / `manual`) in `result.source`. [可核验]
- [ ] A4 If the text came from OCR or was manually typed, mark every paragraph `confidence=low` and never treat a guess as fact. [可核验]
- [ ] A5 If the source is truncated or the page count is unknown, record exactly which paragraphs were received and which are missing. [段落全][可核验]

## B. Segmentation (paragraph inventory)

- [ ] B1 Run `segment`; confirm headings, captions, table cells and formula blocks each got their own id. [段落全]
- [ ] B2 Confirm a paragraph split across a page/column boundary stayed ONE paragraph (no duplicate, no gap). Inspect the boundary paragraphs manually. [段落全]
- [ ] B3 Confirm the source paragraph count equals the count of source paragraphs the material actually has (spot-check against the PDF). [段落全]
- [ ] B4 Target paragraph ids must be exactly `P0001..P####` in the same order, 1:1. `qa` reports `missing_target`, `extra_target`, `order_issues`, `duplicate_target_ids`. All must be empty. [段落全]

## C. Glossary build and lock (term stability)

- [ ] C1 Build the glossary BEFORE translating: run `candidates`, then curate; every kept row gets a translation. [术语稳]
- [ ] C2 Formulas/proper nouns kept untranslated get a row with `translation = term` (e.g. `MoS2 → MoS2`), so the checker does not flag them. [术语稳]
- [ ] C3 Every term actually used in the translation has `status=locked`; one term = one translation. [术语稳]
- [ ] C4 Check the same term in title / abstract / body / captions / conclusion uses the SAME translation. `qa` lists `term_drift` and per-term `target_occurrences_of_canonical`. [术语稳]
- [ ] C5 No `term_untranslated` and no `term_missing_translation` issues remain in `qa`. [术语稳]

## D. Protection of numbers / units / formulas / citations (relation accuracy)

- [ ] D1 Run `protect` and eyeball the masked text: every number, unit, citation, figure/table/equation reference, and inline formula is a `⟨...⟩` placeholder; no protected token is left as free text. [关系准]
- [ ] D2 After translation, `restore` must reproduce the source verbatim for the protected spans (the round-trip must be identical for those spans). [关系准]
- [ ] D3 `qa` `token_missing` must be empty. For `ref` tokens (Fig./Table/Eq./Section), the numeric identifier must survive even if "Fig." is localized to "图". [关系准]
- [ ] D4 `qa` `number_drift` must be empty: the multiset of numbers per paragraph matches. [关系准]
- [ ] D5 Display formulas are kept verbatim (only the surrounding prose is translated); if a formula is an image, mark it `uncertain` and do not invent LaTeX. [关系准]

## E. Negation, qualifiers, anaphora, causal/concessive relations (relation accuracy)

- [ ] E1 `qa` `negation_possibly_dropped` must be empty, or each remaining flag must be confirmed by a human and recorded. [关系准]
- [ ] E2 `qa` `qualifier_possibly_dropped` must be empty, or each remaining flag must be confirmed and recorded. [关系准]
- [ ] E3 For each "However / although / despite / because / therefore / since / while" in the source, check the target carries the corresponding 转折/让步/因果 relation; do not flatten it into a plain "and". [关系准]
- [ ] E4 For each pronoun/anaphor ("it", "this", "the former/latter", "which"), confirm the referent is recoverable in the target (repeat the noun where the source is ambiguous). [关系准]

## F. Bilingual alignment and rationale (verifiability)

- [ ] F1 Every target paragraph is paired with exactly one source paragraph (`source_id` == `target_id`). [可核验]
- [ ] F2 Every pair carries `source_text`, `target_text`, `source_location` (page/line), `glossary_terms_used`, and a `rationale`. [可核验]
- [ ] F3 Every uncertain span appears BOTH inline on its paragraph and in the flat `result.uncertainties` list, with `reason` + `action`. [可核验]
- [ ] F4 No uncertain span is silently "smoothed over"; if you cannot read it, write that you cannot read it. [可核验]

## G. Outputs

- [ ] G1 `/app/output/result.json` is valid JSON, contains `case_id`, `status`, `source`, `glossary`, `alignment`, `uncertainties`, `qa`, and every `output_contract` field. [可核验]
- [ ] G2 `/app/output/bilingual.md` (editable artifact) shows, per paragraph: id, source, translation, rationale, uncertain notes. [可核验]
- [ ] G3 `status` is `success` only if all four questions pass; otherwise `partial` with an explicit boundary list. [可核验]
- [ ] G4 Re-running the same commands on the same inputs yields the same structure (idempotent); record any manual edits in `change_log`. [可核验]

## Quick commands

```bash
python3 src/translate.py segment   --source work/source.txt --out work/source.json
python3 src/translate.py candidates --source work/source.txt --out work/glossary_draft.md
python3 src/translate.py protect   --source work/source.txt --out work/protected.json --mask-out work/masked.txt
python3 src/translate.py align     --source work/source.json --target work/target.txt --out work/align.json --md-out work/bilingual.md
python3 src/translate.py qa        --source work/source.json --target work/target.txt --glossary work/glossary.md --out work/qa.json
```
