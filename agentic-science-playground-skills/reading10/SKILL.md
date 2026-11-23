---
name: structured-paper-notes
description: >-
  把一篇科研论文变成「与章节对齐、字段齐备、每条可回原文、可继续复用」的结构化笔记。
  触发词：文献总结、结构化笔记、论文笔记、章节总结、论文卡片、知识点提取、术语归一、
  来源回链、研究问题、数据、方法条件、主要发现、结论成立前提、局限、锚点、段落定位、
  literature notes、paper card、structured notes、section summary、knowledge point、
  evidence locator、note anchoring。
  用于「阅读10｜文献总结与结构化笔记」及任何需要把论文做成可复核、可检索、可比较笔记的
  科研阅读任务。不用于：逐字转录 PDF（走 academic-pdf-parser）、网页抓取、翻译整篇、
  生成新论文内容、审稿级逐字符校对。
---

# 用途

把一篇真实论文变成结构化笔记，而不是一段压缩后的通读摘要。四个目标问题与对应硬约束：

1. **对得上**：笔记骨架（`skeleton[]` + `sections[]`）必须来自论文**自身章节标题与论证顺序**；禁止套用「研究背景→方法→结果→结论」这类通用模板。章节小结只写该节内容，并记录节间承接关系（`follows_from`/`leads_to`/`purpose`）。
2. **留得住**：论文卡片固定六字段族——研究问题、数据、方法（含方法条件）、主要发现、局限、**结论成立的前提条件**。每个字段有 `status ∈ {reported, partial, not_reported, conflict}`；`not_reported` 是合法结果，不编造。每条 finding 必须能引用到 `conditions` 里让结论成立的前提。
3. **找得回**：每条关键笔记（卡片字段、字段子项、章节小结断言、知识点）都带 `anchor`：`locator + section_id + page + para/block_id/figure_id/table_id/equation_id + quote`。`quote` 是原文**逐字**片段，可被脚本子串核验。
4. **用得上**：知识点做术语/缩写/同义表述归一，去重与冲突显式标注；字段名、锚点格式、状态枚举固定，多篇论文可并排比较，结果可被脚本再次读入校验。

本 Skill 不做逐字转录（那是 academic-pdf-parser 的职责）；解析 PDF 只做到「够用即可」，
重心在**结构化、回链、可复用**。

# 适用 / 不适用条件

**适用**：有文本层或可 OCR 的科研论文/综述/预印本（中文、英文、中英混合；单栏、双栏、多栏；含表格、公式、图、参考文献）。
**不适用（改走其它 Skill 或人工）**：加密且无口令的 PDF；纯图表海报无正文；需要重排版公式科学含义；需要编辑 Office 源文件而非做笔记。
**触发即用**：`case.json`/`task.md` 出现「文献总结/结构化笔记/章节对齐/字段化/知识点/来源回链/研究问题/方法条件/结论前提」等词，或素材含 `.pdf` 且要求输出可复核笔记。

# 输入契约（运行时）

- 原始输入：`/input/case.json`（含 `case_id`、`output_contract` 要求字段、素材路径）与 `/input/task.md`。
- 工作目录 `/app/work`；最终结果与可编辑产物写 `/app/output`；`result.json` 必须含 `case_id` + `output_contract` 全部字段。
- 平台可用工具（名称即入口，参数先探明）：`pdf-text-tool`（文本层+坐标）、`pdf-render-tool`（页面渲染）、`ocr-tool`（扫描件 OCR）、`font-discovery`（乱码排查）、`office-renderer`、`browser-automation`。
- 本包资源路径（安装后）：`/skills/weekly-skill/src/notes.py`、`/skills/weekly-skill/schema/notes_schema.json`、`/skills/weekly-skill/checks/checklist.md`、`/skills/weekly-skill/templates/paper_card.md`。本地开发用 `src/notes.py` 相对路径。

# 分步操作流程（按序执行，可重复/幂等）

> `/app/work/notes.json` 是逐步累积的草稿：第 3 步先含 `sections`，
> 第 4–6 步依次补 `paper_card`、`knowledge_points`、锚点；每步用对应机检命令校验
> 后继续。最终由 `build-result` 打包成 `/app/output/result.json`。

### 第 0 步 读输入，锁定事实依据
1. 用 read 工具读 `/input/case.json` 与 `/input/task.md`（不要 cat）。
2. 记下 `case_id`、`output_contract` 字段名、素材文件路径。
3. `find /input -type f` 列出全部素材；**以实际文件为准**，不要凭文件名或标签猜内容。
4. 若素材是归档/多文件，先解包到 `/app/work`（`unzip`/`tar`），保留原始文件名映射。

### 第 1 步 探测文档：文本层 vs 扫描件 vs 加密（关键分支）
1. `file <pdf>` 看 `PDF document`；`pdf-text-tool` 试抽第 1–2 页文本。
2. 判据：
   - **有文本层**：每页 ≥ 20 个非空字符、非全 `�`/乱码 → 文本层路径。
   - **扫描件/无文本层**：每页字符 ≈ 0 或只有图片占位 → render+OCR 路径。
   - **混合**：部分页有文本、部分页空白 → 有文本页走文本层，空白页走 OCR，`document.tool_path="mixed"`。
   - **加密**：text/render 报 `encrypted`/`password required` → 见异常矩阵 E1，不要反复重试同一命令。
3. 每次命令看 `[exit code: N]`，非 0 先排查 stderr 再继续。

### 第 2 步 归一化为 source.json（论文的逐字事实层）
把抽取结果统一成 `source.json`（UTF-8，脚本据此做全部机械核验）：

```json
{"file":"paper.pdf","page_count":12,"language":"en|zh|mixed|other",
 "sections":[
   {"section_id":"s1","number":"1","title":"Introduction","level":1,
    "start_page":1,"end_page":2,"heading_block_id":"p1-b01",
    "blocks":[{"block_id":"p1-b01","page":1,"text":"..."}]}],
 "blocks":[{"block_id":"p1-b01","page":1,"text":"..."}]}
```

要点：
- 章节 `title` 用**论文自身标题逐字**（编号从 `^\d+(\.\d+)*\.?\s+` 解析；无编号则 `number:null`）。
- `blocks[].text` 逐字，保留段落内换行；不要 join 相邻段落。
- 双栏阅读顺序：列优先；跨栏通栏标题/图表作锚点；跨页续段在两页都标 `continued`。**只做阅读顺序，不做逐字转录全量校验。**
- 页码用物理页码（1-based，文件内顺序）；若印刷页码错乱另存 `page_reading_order` 映射并写进 `document` 说明。

### 第 3 步 章节骨架提取（对得上）
1. 从 `source.json` 的 `sections[]` 生成 `skeleton[]`：`[{section_id, order}]`，顺序=原文顺序。
2. 每个 `sections[]` 条目填：`title`（逐字）、`level`、`parent_section_id`、`heading_block_id`、`start_page/end_page`、`order`、`role`（background/problem/method/results/discussion/conclusion/limitations/other）、`purpose`（本节在论证中的作用，一句话）、`follows_from`/`leads_to`（节间承接）。
3. 每节写 `summary`：`anchor`（至少 section_id+page）+ `claims[]`（本节关键断言，每条带独立 anchor）。**只写该节页码范围内的内容**。
4. 跑对齐检查（机检）：

```bash
python3 /skills/weekly-skill/src/notes.py check-sections \
  --notes /app/work/notes.json --source /app/work/source.json --out /app/work/rep_sections.json
```

   修到 `rep_sections.json` 里 `aligned=true`、`coverage=1.0`、`extra_section/missing_sections/order_errors/heading_not_found` 全空。

### 第 4 步 字段化论文卡片（留得住）
按 `schema/notes_schema.json` 的 `paperCard` 填六字段族，先跑启发式定位建议：

```bash
python3 /skills/weekly-skill/src/notes.py extract-fields \
  --source /app/work/source.json --out /app/work/rep_fields_hint.json
```

`rep_fields_hint.json.field_sections` 给出「哪个字段应到哪个 section_id 找素材」，仅 `heuristic_guess`，Agent 必须确认。逐字段规则：

- **research_question**：主问题 + 子问题，各带 anchor。缺失标 `not_reported`。
- **data**：数据/样本来源、样本量、时间范围、关键变量，逐条 `items[].text + anchor`。缺哪项就在 `value` 说明并进 `uncertainty[kind=not_reported]`。
- **method**：`components[]`（方法/模型/设计/关键参数，每项 name+detail+anchor）+ `conditions[]`（方法成立的前提：识别假设、分布假设、样本条件、参数设定等，每项 condition+anchor）。
- **findings**：`items[]` 每条 `statement + direction + effect_size/statistics + anchor + condition_ids`。数值、单位、符号、p 值与原文逐字一致。
- **conditions**：结论成立的前提/适用范围，`items[]` 每条 `condition_id + premise + scope + applies_to[] + anchor`；`applies_to` 指向 finding_id。**这是本 Skill 的关键字段：没有条件，结论就不是结论。**
- **limitations**：逐条记录原文局限；原文没写限制则 `status="not_reported"`（不编「样本量小」这类泛化限制）。
- 无法判断/未报告一律 `not_reported`/`uncertainty`，**不静默留空**。

跑字段完整性检查：

```bash
python3 /skills/weekly-skill/src/notes.py check-fields \
  --notes /app/work/notes.json --out /app/work/rep_fields.json
```

   修到 `rep_fields.json.complete=true`、`errors=[]`。

### 第 5 步 知识点提取与术语归一（用得上）
1. 从卡片与各节摘要拆出知识点：概念、变量、方法、结论、条件、缩写、数据集。
2. 每条填：`kp_id`、`term`（原文）、`canonical`（展开缩写后的规范形式，能确定才填）、`abbreviations[]`、`synonyms[]`、`type`、`definition`、`value/unit`（变量/结论时）、`anchor`、`relations[]`、`status`。
3. 术语归一规则：`normalized_term` = 小写 + NFKC + 空白折叠 + 去首尾分隔标点（**不去括号**，括号内容可能是术语本体）。同义改写（「公司」vs「企业」）必须由 Agent 显式写进 `synonyms[]`，脚本不会自动发现语义同义。
4. 跑去重/冲突检测：

```bash
python3 /skills/weekly-skill/src/notes.py dedupe-kps \
  --notes /app/work/notes.json --out /app/work/rep_kps.json
```

   - `rep_kps.json.merged[]`：同 (归一术语, type) 且定义兼容的重复条目，保留定义更完整者，`merged_from` 记录被并者，`abbreviation_links[]` 是缩写→展开的链接建议。
   - `rep_kps.json.conflicts[]`：同名同型但定义互不包含 → 保留两条、互相 `conflict_with`，并在 `uncertainty[kind=conflict]` 给两处原文证据，让 Agent 判定是两种含义还是抄错。

### 第 6 步 锚点回链（找得回）
给**每一条**关键笔记补 anchor，粒度与断言类型匹配：

- 字段级/子项级：具体段落或句，`quote` 逐字。
- 章节小结：section_id + page range；`claims[]` 内每条断言再给独立 anchor。
- 知识点：具体段落 + quote。
- 图表/公式相关：补 `figure_id/table_id/equation_id`。
- `locator` 人类可读格式：`s3 §2.3 ¶2 · p.7 · Fig.2`（章节·段落·页码·图表）。

跑锚点校验：

```bash
python3 /skills/weekly-skill/src/notes.py check-anchors \
  --notes /app/work/notes.json --source /app/work/source.json --out /app/work/rep_anchors.json
```

   - `quote_not_found`：quote 非逐字或 block 归属错 → 回原文复制原句。
   - `page_out_of_range / section_id_not_found / block_id_not_found`：锚点指向不存在位置 → 修正。
   - `quote_found_in_other_block`（warning）：引文跨块/排版重建 → 人工核对后保留或修正，不静默放过。

### 第 7 步 组装 result.json + 可编辑产物
1. 组装 `/app/output/result.json`（结构见 `schema/notes_schema.json`）：顶层必填 `case_id/schema_version/status/document/paper_card/sections/knowledge_points/evidence/uncertainty`；`skeleton[]` 与 `sections[]` 一并给出；`output_contract` 额外字段逐一补齐。

```bash
python3 /skills/weekly-skill/src/notes.py build-result \
  --notes /app/work/notes.json --case-id <CASE_ID> --out /app/output/result.json
```

2. 可编辑产物写 `/app/output`：
   - `notes.md`：全文结构化笔记（章节小结 + 论文卡片 + 知识点 + 未报告项）。
   - `paper_card.md`：用 `templates/paper_card.md` 填充的字段化卡片。
   - 关键图表/公式页渲染预览 PNG（扫描件/低置信区必须给），文件名含 page/block_id 对应关系。
3. `status`：六字段族齐备、sections 完整、锚点全通过=success；部分缺失=partial（`limits[]` 写清缺什么）；整体失败=failed；无法判断=cannot_judge。

### 第 8 步 机械校验（机检汇总，不过不交付）
依次跑第 3–6 步的 `check-sections / check-fields / check-anchors / dedupe-kps`，全部通过后进入第 9 步。任何报错回到对应步骤修 `notes.json` 重跑，**不要手工改机检报告**。

### 第 9 步 自查（用 checks/checklist.md）
逐项执行 `checks/checklist.md`，失败项写进 `result.json.uncertainty[]`（带 kind/page/block_id/section_id）。至少跑 `python3 /skills/weekly-skill/src/notes.py self-test`，并用 `schema/notes_schema.json` 校验 result.json（有 jsonschema 就 `Draft7Validator`，没有就 `python3 -m json.tool` + 手动核对 required 列表）。

# 领域规则（不可违反）

1. **骨架跟原文走**：`sections[].title` 是论文自身标题逐字；`skeleton[]` 不得含原文没有的章节（模板章节=错误）。
2. **留条件**：每条 finding 的 `condition_ids` 必须可解析到 `conditions.items[]`；结论没有前提记录时，在 `conditions.value` 说明「原文未明确」并标 `not_reported`，不编造假设。
3. **逐字 quote**：`quote` 只能来自原文；缺失写 `null` 并标 `unverifiable`，不得改写/翻译/补字。
4. **诚实状态**：`status` 只取 reported/partial/not_reported/conflict；数值/变量/单位与原文一致，转写错误=0 容忍。
5. **机器判定与人工确认分开**：章节对齐、字段非空、锚点键存在、quote 子串匹配、页码范围、知识点去重→机器判定；一句话总结、定义、结论语义、同义改写→人工确认并记 `source=manual`。
6. **幂等**：重跑同一输入产出相同 `section_id/block_id/kp_id` 顺序与机检报告；有差异写 `change_log` 并说明原因（OCR 随机性、工具非确定输出）。

# 输出契约（/app/output）

- `result.json`：符合 `schema/notes_schema.json`，含 `case_id`、`schema_version=1.0.0`、`output_contract` 全部字段。
- `notes.md`、`paper_card.md`（可编辑）；扫描件/低置信区关键页渲染预览 PNG。
- 预览与可编辑产物必须真实生成，不得引用不存在的路径；二进制预览单独保留，不影响 JSON 有效性。

# 证据 / 来源定位规则

- 锚点四要素：`locator`（人类可读）+ `section_id` + `page` + `quote`（逐字）；能给出段落/图/表/公式时补 `para/block_id/figure_id/table_id/equation_id`。
- 粒度匹配：结论级→具体段落/句；章节级→section_id+page range；图表/公式相关→对应 id。
- `evidence.coverage`：`sections_anchored/sections_total`、`fields_anchored/fields_total`、`kps_anchored/kps_total` 必须能对账；缺失项进 `evidence.unverifiable[]` 或 `uncertainty[]`。
- 回不去原文的字段/断言：标 `uncertainty[kind=unverified]`，绝不把回不去的写进结果。

# 不确定性与异常处理

## 不确定性标注模板
```json
{"kind":"unreadable|not_reported|conflict|ambiguous|heuristic_guess|missing_data|unverified|other",
 "detail":"……","page":3,"block_id":"p3-b07","section_id":"s3",
 "anchor":{"locator":"s3 p.3","section_id":"s3","page":3,"block_id":"p3-b07"}}
```
- 读不出/模糊/乱码 → `unreadable`；题面要求但原文没有 → `not_reported`；原文自相矛盾 → `conflict`（两处证据都给）；启发式推断（章节→字段映射、双栏顺序）→ `heuristic_guess`；锚点回不去 → `unverified`。

## 异常矩阵
| 编号 | 异常 | 识别信号 | 处置（按序） | 结果标注 |
|---|---|---|---|---|
| E1 | 加密 PDF | text/render 报 `encrypted`/`password required` | case.json 有口令则带口令重试一次；无口令→停止该文件，写 failed+limits | `document` 说明、`unreadable` |
| E2 | 扫描件/无文本层 | 每页字符≈0、只有图片占位 | `pdf-render-tool` 渲染 200–300 DPI → `ocr-tool` 逐页识别；低置信区标 `unreadable` | `document.tool_path=pdf-render-tool+ocr-tool`、`source=ocr`、`confidence=low` |
| E3 | 双栏错序 | 左右栏内容串栏、跨栏拼接 | 列优先排序，通栏标题/图表作锚点；`--min-gap` 调栏距；仍错按渲染图人工定列界 | `heuristic_guess` |
| E4 | 图表/公式缺失 | 文本层无图/公式 span，但渲染图有 | 渲染裁剪该区域；公式记原字符/Unicode，`latex` 拿不准置 null；图记 `figure_id`+渲染裁剪 | `unreadable`/`heuristic_guess`、`source=render_crop` |
| E5 | 超长论文 | 页数/块数远超预算 | 先产 `skeleton`+六字段卡片+每节一句话 summary（有 anchor）；知识点只做首轮高频项并标 `partial`+`limits`；分批续补，每次补完重跑机检 | `partial`+`limits[]` |
| E6 | 非中文论文 | 语言=en/other，术语为英文 | 术语归一照常（英文小写折叠）；quote 用英文原文逐字；不强行中译，字段值可英文+必要时中文括注；`document.language` 如实写 | `document.language` |
| E7 | 乱码字体（ToUnicode 缺失） | 文本层全是 `�`/无意义符号 | 该页/全文档 render+OCR；保留原文本层样本作 evidence | `unreadable`（原层）+`ocr` |
| E8 | 页码错乱 | 物理页码≠印刷页码、缺页/重页 | 记录 `page_reading_order` 映射；`page` 保留物理页号，`locator` 同时写印刷页并说明 | `uncertainty` |
| E9 | 无显式章节标题 | 标题缺失或只在排版上区分 | 按「页/段落主题块」临时建 section_id，标题写原文首句，`number:null`+`heuristic_guess`，skeleton 说明是推断结构 | `heuristic_guess` |
| E10 | 工具调用失败/超时 | `[exit code: N]` 非 0、输出为空 | 看 stderr；参数重试 1 次；仍失败降级（text→render+OCR→仅 render 供人工）并标 `partial` | `failed/partial`+`limits` |

# 自查清单（精简版，完整见 checks/checklist.md）
1. `check-sections`：aligned=true、coverage=1.0、无 extra/missing/order/heading 错误（对得上）。
2. `check-fields`：complete=true、六字段族齐备、findings.condition_ids 全解析（留得住）。
3. `check-anchors`：全部 ok、无 quote_not_found/page 越界/section 不存在（找得回）。
4. `dedupe-kps`：无未处理重复与冲突；缩写已链到展开项（用得上）。
5. `result.json` 含 case_id+schema_version+output_contract 字段；schema 校验通过；重跑幂等。

# 相比裸 Agent 的质量增益

| 裸 Agent 常见错误 | 本 Skill 如何防止 | 可验证方法 |
|---|---|---|
| 套用「背景/方法/结果/结论」模板，笔记与论文结构脱节 | 骨架必须来自 source.json 原文标题，`check-sections` 检出 `extra_section/missing_sections/order_errors` | `rep_sections.json.aligned=true` 且 coverage=1.0 |
| 漏掉「结论成立的前提条件」 | `conditions` 为必填字段族，`findings.condition_ids` 必须可解析，缺失标 `not_reported` | `check-fields` 无 `condition_id_unresolved` |
| 数值/变量/单位抄错 | 字段与 finding 强制 `effect_size/statistics` + 逐字 quote，规则「转写错误=0 容忍」 | quote 子串匹配 + 抽查原文数值 |
| 只给「参见论文」这类笼统出处 | anchor 四要素强制 + `quote` 逐字 + 脚本 `check-anchors` | `rep_anchors.json` 全部 ok、coverage=1.0 |
| 术语/缩写重复、自相矛盾不处理 | `dedupe-kps` 按 (归一术语,type) 归并/冲突检测，缩写链接 | `rep_kps.json.merged/conflicts/abbreviation_links` 可对账 |
| 未报告内容被悄悄跳过 | 六字段族 status 枚举 + `not_reported` 合法 + 空字段报错 | `check-fields` 无 `empty_reported_field` |
| 扫描件/加密/超长/非中文直接失败或瞎编 | 异常矩阵 E1–E10 逐条处置，`document.tool_path` 记录实际路径 | `document` + `limits[]` 与异常编号对得上 |

**公平自评方法**：同输入、同工具、同预算跑「裸 Agent（无本 SKILL）」与「加载本 SKILL」，
比较：(1) `check-sections` 的 `aligned/coverage`（裸 Agent 常因模板章节 < 1）；(2) 六字段族
非空率与 `conditions` 是否被记录；(3) `check-anchors` 的 quote 命中率；(4) 知识点
`merged/conflicts` 数量（裸 Agent 常出现重复条目）；(5) 端到端耗时与人工补写/返工次数。
以上均可从 `result.json` 与 `rep_*.json` 机械计算，无需主观判断。
