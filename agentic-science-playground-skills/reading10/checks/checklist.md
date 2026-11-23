# 自查清单：文献总结与结构化笔记「四个问题」逐项核对

本清单是 SKILL.md 第 9 步的执行版。每条要么通过、要么把失败点写进
`result.json` 的 `uncertainty[]`（带 `kind`/`page`/`block_id`/`section_id`），
不要静默放过。「比对原文」指比对 source.json 的逐字块（必要时回到
`pdf-render-tool` 渲染图），不是比对自己的提取结果。

可机械判定的检查直接用脚本（所有命令在 `/skills/weekly-skill/src/notes.py`）：

```bash
python3 src/notes.py self-test
python3 src/notes.py check-sections --notes notes.json --source source.json --out /app/work/rep_sections.json
python3 src/notes.py check-fields     --notes notes.json --out /app/work/rep_fields.json
python3 src/notes.py check-anchors    --notes notes.json --source source.json --out /app/work/rep_anchors.json
python3 src/notes.py dedupe-kps       --notes notes.json --out /app/work/rep_kps.json
```

---

## 问题一「对得上」——骨架与论文自身章节/论证顺序一致

- [ ] 1.1 `sections[].title` 是论文自身章节标题（逐字），不是「研究背景/研究方法/结果/结论」这类通用模板名。
- [ ] 1.2 `skeleton[]` 的顺序与 `source.json` 的章节顺序一致，无缺节、无多出原文没有的章节。
- [ ] 1.3 `check-sections` 结果 `aligned == true`，`coverage == 1.0`，`extra_section/missing_sections/order_errors/heading_not_found` 全为空。
- [ ] 1.4 每个 `section.heading_block_id` 在 source.json 中真实存在，且是标题块（不把正文段落当标题）。
- [ ] 1.5 每节小结 `summary` 只写该节页码范围内的内容；跨节内容不得塞进前一节。
- [ ] 1.6 章节间承接关系已记录：`follows_from`/`leads_to`/`purpose` 非空且与原文论证链一致（“本节解决上一节的什么问题”）。
- [ ] 1.7 子章节 `parent_section_id` 与原文编号层级一致（level 数 = 编号段数）。

## 问题二「留得住」——要素齐备，尤其结论成立的前提条件

- [ ] 2.1 `paper_card` 六个字段族齐全：`research_question / data / method / findings / limitations / conditions`。
- [ ] 2.2 `check-fields` 结果 `complete == true`，`errors` 为空（缺失/空/无锚点/condition_id 未解析都会报错）。
- [ ] 2.3 `research_question` 记录主问题与子问题；子问题各有 anchor。
- [ ] 2.4 `data` 记录数据/样本来源、样本量、时间范围、关键变量；缺哪项标 `not_reported`，不悄悄省略。
- [ ] 2.5 `method` 的 `components` 记录方法/模型/设计/关键参数；`method.conditions` 记录方法成立的前提（识别假设、分布假设、样本条件等）。
- [ ] 2.6 `findings.items[]` 每条含 `statement + direction + effect_size/statistics + anchor`，且数值与原文一致。
- [ ] 2.7 每条 finding 的 `condition_ids` 都落到 `conditions.items[]`；结论成立的前提条件（假设、适用范围、边界）被显式列出，并 `applies_to` 指向对应发现。
- [ ] 2.8 `limitations` 逐条列出原文限制；原文未报告限制时该字段标 `not_reported`（不编造「样本量小」等泛化限制）。
- [ ] 2.9 数值/变量/单位逐字核对：百分比、系数、p 值、单位、符号与原文一致，转写错误为 0。

## 问题三「找得回」——每条关键笔记能指回原文具体位置

- [ ] 3.1 每个 anchor 有 `locator + section_id + page`；能给出段落/图/表/公式时补 `para/block_id/figure_id/table_id/equation_id`。
- [ ] 3.2 `check-anchors` 结果全部 `ok == true`；`page_out_of_range / section_id_not_found / block_id_not_found / quote_not_found` 均不存在（`quote_found_in_other_block` 若出现必须人工核对跨块引文）。
- [ ] 3.3 `quote` 是原文逐字片段（NFKC/空白折叠后能子串匹配），不是转述、翻译或补写。
- [ ] 3.4 字段级 `items[]` 每条都有独立 anchor，不只给字段一个笼统出处。
- [ ] 3.5 章节小结 `summary.claims[]` 每条断言都有独立 anchor；不能整节只给一个 page range。
- [ ] 3.6 知识点 `knowledge_points[].anchor` 全部可回链。
- [ ] 3.7 `evidence.coverage` 对账：`sections_anchored/sections_total`、`fields_anchored/fields_total`、`kps_anchored/kps_total` 均等于 1；缺失项进 `evidence.unverifiable[]` 或 `uncertainty[]`。

## 问题四「用得上」——可检索、可比较、可继续加工

- [ ] 4.1 术语归一：每条知识点的 `normalized_term` 已填（小写、空白折叠、去分隔标点），可作检索键。
- [ ] 4.2 缩写/同义：`abbreviations[]`/`synonyms[]` 与 `canonical` 已填；type=abbreviation 的条目已链到展开项（`dedupe-kps` 的 `abbreviation_links`）。
- [ ] 4.3 去重：`dedupe-kps` 无未处理的重复（`merged[]` 里同义条已并，保留条带 `merged_from`）。
- [ ] 4.4 冲突：同名同型但定义矛盾的条目已互相 `conflict_with`，并写 `uncertainty[kind=conflict]`，给出两处原文证据。
- [ ] 4.5 可比较：同一字段名、同一 anchor 格式、同一 status 枚举，多篇论文可并排比较（无私有字段名）。
- [ ] 4.6 可复用：`notes.md`/`paper_card.md` 为可编辑 Markdown；result.json 可被脚本再次读入校验。
- [ ] 4.7 可继续：`result.json` 记录 `document.tool_path`、`change_log`、`uncertainty`，下一次阅读/写作可直接复用而不必重读原文。

---

## 交付前最后 4 项

- [ ] `result.json` 含 `case_id` + `schema_version=1.0.0` + `output_contract` 要求的全部字段；`python3 -m json.tool` 通过；若环境有 jsonschema，用 `schema/notes_schema.json` 校验 0 错误。
- [ ] `status` 诚实：全部齐备=success；部分=partial（`limits[]` 写清缺什么）；整体失败=failed；无法判断=cannot_judge。
- [ ] 可编辑产物在 `/app/output`：`result.json`、`notes.md`（或 `paper_card.md`）；扫描件等关键页有渲染预览（如需要）。
- [ ] 重跑一遍脚本得到相同报告（幂等）；差异写进 `change_log`。
