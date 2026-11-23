# structured-paper-notes — 文献总结与结构化笔记

把一个真实科研论文变成「与章节对齐、字段齐备、每条可回原文、可继续复用」的
结构化笔记。围绕四个问题：

- **对得上**：笔记骨架跟随论文自身章节与论证顺序，不套通用摘要模板。
- **留得住**：研究问题、数据、方法条件、主要发现、局限，以及**结论成立的前提条件**都被记录。
- **找得回**：每条关键笔记指向具体章节/段落/页码/图表，且带原文逐字引文。
- **用得上**：术语/缩写/同义表述归一，去重与冲突显式标注，字段固定可并排比较、可继续加工。

## 包内容

| 路径 | 作用 |
|---|---|
| `SKILL.md` | Skill 本体（frontmatter + 分步操作流程 + 异常矩阵 + 自查）。 |
| `README.md` | 本文件：调用方式、方法、限制、失败处理、自查、最小示例。 |
| `src/notes.py` | 仅标准库的机械校验/抽取/归并工具（可独立运行）。 |
| `schema/notes_schema.json` | result.json / 论文卡片 / 章节小结 / 知识点（含锚点）的 JSON Schema。 |
| `checks/checklist.md` | 四个问题的逐项核对清单。 |
| `templates/paper_card.md` | 可复用的字段化论文卡片模板（可编辑产物骨架）。 |

## 调用方式（运行时）

1. 读 `/input/case.json` 与 `/input/task.md`（read 工具，不要 cat）。
2. 记下 `case_id`、`output_contract` 字段名、素材路径；`find /input -type f` 找实际文件。
3. 把论文转成 `source.json`（章节 + 逐字文本块，见 SKILL.md 第 3 步）。
4. 按 SKILL.md 流程产出 `notes.json`（草稿）。
5. 机械校验（脚本路径安装后为 `/skills/weekly-skill/src/notes.py`，本地为 `src/notes.py`）：

```bash
python3 src/notes.py self-test
python3 src/notes.py extract-fields   --source /app/work/source.json --out /app/work/rep_fields_hint.json
python3 src/notes.py check-sections   --notes /app/work/notes.json --source /app/work/source.json --out /app/work/rep_sections.json
python3 src/notes.py check-fields     --notes /app/work/notes.json --out /app/work/rep_fields.json
python3 src/notes.py check-anchors    --notes /app/work/notes.json --source /app/work/source.json --out /app/work/rep_anchors.json
python3 src/notes.py dedupe-kps       --notes /app/work/notes.json --out /app/work/rep_kps.json
python3 src/notes.py build-result     --notes /app/work/notes.json --case-id <CASE_ID> --out /app/output/result.json
```

6. 把 `rep_*.json` 里报出的问题修进 `notes.json`，再重跑，直到通过。
7. 生成可编辑产物 `/app/output/notes.md`、`/app/output/paper_card.md`（用
   `templates/paper_card.md`），写进 `/app/output/result.json` 的 `change_log`。

## 方法说明

- **章节对齐**（对得上）：`source.json` 存论文自身标题；`skeleton[]` 只允许出现这些
  section_id；`check-sections` 机械判定「漏节 / 多出原文没有的章节（套模板的信号）/
  顺序错 / 标题块不存在」。章节小结必须落在该节页码范围内。
- **字段化卡片**（留得住）：六字段族固定（研究问题/数据/方法/发现/局限/结论成立条件），
  每个字段有 `status ∈ {reported, partial, not_reported, conflict}`；`not_reported`
  是合法结果（不编造），`findings.condition_ids` 必须能落到 `conditions.items`。
- **锚点回链**（找得回）：锚点 = `locator + section_id + page + (para|block_id|
  figure_id|table_id|equation_id) + quote`；`quote` 是原文逐字片段，`check-anchors`
  用 NFKC+空白折叠做子串匹配，发现「引文不在原文/页码越界/章节不存在」等错误。
- **知识点归并**（用得上）：`normalize_term` 做术语归一；`dedupe-kps` 按
  (归一术语, type) 归组，定义兼容→合并（保留更完整者、并入 synonyms/abbreviations/
  额外锚点），定义互不包含→标 `conflict_with`；`resolve_abbreviations` 把缩写条目
  链到展开项。**语义总结（一句话定义、结论表述）由 Agent 完成，脚本只做机械判定。**

## 适用范围与限制

- **适用**：有文本层或可 OCR 的科研论文/综述/预印本（中文/英文/混合；单栏/双栏；含表格、公式、图）。
- **不适用**：加密且无口令的 PDF；纯图表海报；需要重排版公式科学含义而非做笔记；
  需要审稿级逐字符校对（本 Skill 用于「可复核的结构化笔记」，不是逐字转录）。
- **限制**：
  - 术语归一与引文匹配是**字符串**方法，不理解语义；同义改写（如「公司」vs「企业」）
    需要 Agent 在 `synonyms[]` 显式给出，脚本不会自动发现。
  - `extract-fields` 的「章节标题→字段」是关键词启发式，恒标 `heuristic_guess`，
    只作预填建议，必须 Agent 确认。
  - 跨块引文（quote 跨两个 block）会被标 `quote_found_in_other_block`，需人工复核，
    不自动判死。

## 失败处理

- 脚本非 0 退出：看 stderr；`[exit code: N]` 为 N 时先排查参数/文件路径，再重试一次。
- `check-sections` 报 `extra_section`：多半是套了通用模板，回到 `source.json` 用原文
  章节标题重写 skeleton。
- `check-anchors` 报 `quote_not_found`：要么 quote 不是逐字（改写/翻译了），要么
  block 归属错；回到原文块复制原句。
- `check-fields` 报 `unanchored_reported_field`：字段/子项缺 anchor；补上，或确实
  未报告则把 status 改 `not_reported`。
- 扫描件/无文本层：走 `pdf-render-tool + ocr-tool`，锚点 `source=ocr`、`confidence`
  降级为 low，低置信区进 `uncertainty[kind=unreadable]`。

## 自查方法

1. 跑 `python3 src/notes.py self-test`（必须 OK）。
2. 跑上面 6 条机械校验，全部报告通过。
3. 逐项执行 `checks/checklist.md`，失败点写进 `result.json.uncertainty[]`。
4. 抽查 3 条关键结论，按其 `locator/block_id/quote` 回到渲染图核对。
5. 重跑一遍得到相同报告（幂等），差异写 `change_log`。

## 最小示例（EXAMPLE）

**输入**：一份 3 页论文 `example.pdf`，原文三节 Introduction / Data / Results；
`source.json` 由解析步骤得到（示意，非正式案例）：

```json
{
  "file": "example.pdf", "page_count": 3,
  "sections": [
    {"section_id": "s1", "title": "Introduction", "start_page": 1, "end_page": 1,
     "heading_block_id": "p1-b01",
     "blocks": [{"block_id": "p1-b01", "page": 1, "text": "We ask whether X affects Y."}]}
  ]
}
```

**草稿 `notes.json`**（示意，EXAMPLE）：

```json
{
  "case_id": "EXAMPLE", "schema_version": "1.0.0", "status": "partial",
  "document": {"file": "example.pdf", "page_count": 3, "language": "en"},
  "skeleton": [{"section_id": "s1", "order": 1}],
  "paper_card": {
    "research_question": {
      "status": "reported", "value": "Whether X affects Y.",
      "anchor": {"locator": "s1 ¶1 p.1", "section_id": "s1", "page": 1,
                 "block_id": "p1-b01", "quote": "whether X affects Y"}},
    "data": {"status": "not_reported"},
    "method": {"status": "not_reported"},
    "findings": {"status": "not_reported"},
    "conditions": {"status": "not_reported"},
    "limitations": {"status": "not_reported"}
  },
  "sections": [
    {"section_id": "s1", "title": "Introduction", "level": 1, "order": 1,
     "heading_block_id": "p1-b01",
     "summary": {"anchor": {"locator": "s1 p.1", "section_id": "s1", "page": 1}}}
  ],
  "knowledge_points": [],
  "evidence": {"coverage": {}},
  "uncertainty": []
}
```

**调用**：

```bash
python3 src/notes.py build-result --notes notes.json --case-id EXAMPLE --out result.json
python3 src/notes.py check-sections --notes notes.json --source source.json --out rep_sections.json
```

**示意输出**（EXAMPLE，非正式结果）：`result.json` 含 `case_id=EXAMPLE`、
`schema_version=1.0.0`、`status=partial`；`rep_sections.json` 的 `aligned=true`、
`coverage=1.0`。以上为示例，正式案例以平台给定输入为准。
