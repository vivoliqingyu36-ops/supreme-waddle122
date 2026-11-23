# Term glossary

<!-- metadata: keys parse into result.json; keep the `- key: value` lines. -->
- source_language: en
- target_language: zh
- domain: (fill in: e.g. materials science / oncology / NLP)

## Terms

<!--
  Column contract (exactly 6 columns; escape a literal pipe as \|):
    term        exact source surface form, case-sensitive for acronyms/formulas
    translation the ONLY allowed translation when status=locked
    variants    other source forms mapping to the SAME translation (comma separated)
    context     a short source snippet for disambiguation
    first_location  first source paragraph id, e.g. P0002
    status      locked | pending | uncertain
  Rules:
    - locked    = enforce this translation everywhere: title, abstract, body,
                  captions, table headers, conclusion. No exception without
                  editing this row first.
    - pending   = candidate, do NOT use yet.
    - uncertain = translation uncertain; every use must be flagged in output.
    - A formula/proper noun kept untranslated still gets a row with
      translation = the term itself, so the checker does not report it as
      "left untranslated".
-->
| term | translation | variants | context | first_location | status |
|---|---|---|---|---|---|
| monolayer | 单层 | single layer | Monolayer molybdenum disulfide | P0002 | locked |
| band gap | 带隙 | bandgap | the band gap of MoS2 | P0002 | locked |
| MoS2 | MoS2 | molybdenum disulfide | MoS2 is a semiconductor | P0002 | locked |
| field-effect transistor | 场效应晶体管 | FET | used for field-effect transistors | P0004 | locked |
| (add more rows here) |  |  |  |  | pending |

## Rules

1. One term = one translation, for the whole paper (title/abstract/body/captions/conclusion).
2. `term` is the source surface form. Matching is case-insensitive for plain
   lowercase words ("monolayer" also matches "Monolayer"); it is case-sensitive
   for terms containing uppercase letters or digits ("MoS2", "TMD", "cm2").
3. `variants` are alternate source spellings that must receive the same
   translation (e.g. "bandgap" for "band gap").
4. To change a locked translation, edit this row first, then re-run the QA
   command. Never introduce a second translation in the target text while a
   locked row says otherwise.
5. New terms discovered mid-translation are appended as `pending`, then either
   promoted to `locked` (with a translation) or left `uncertain`.
