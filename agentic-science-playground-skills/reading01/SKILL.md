---
name: academic-pdf-parser
description: >-
  把科研 PDF 论文解析成可复核的结构化结果。触发词：PDF 解析、文献解析、文档解析、
  论文阅读、PDF 提取、多栏阅读顺序、表格解析、公式提取、希腊字母、上下标、扫描版 OCR、
  页眉页脚、脚注、参考文献提取、parse pdf、extract pdf、reading order、table extraction。
  用于「阅读01｜文献文档解析」及任何需要把 PDF 逐字抽取并按原文页码/区块回证的科研阅读任务。
  不用于：网页抓取、纯文本问答、需要理解公式科学含义的推理、生成新论文内容。
---

# 用途

把一份科研 PDF 变成「逐字可复核 + 顺序正确 + 结构可分 + 每块可回原文」的 JSON 结果。
四个目标问题与对应的硬约束：

1. **提得全**：正文、图表题注、脚注、参考文献逐字提取，不漏行不丢段；页眉页脚/页码必须从正文中**剔除**并单独留存。
2. **排得对**：双栏/多栏按原版面顺序输出（列优先），不串栏、不错行、不把相邻段落拼成一句；跨栏通栏元素作锚点；跨页续段显式标注。
3. **拆得清**：章节层级（编号/父级）、表格行列与单元格归属（含 rowspan/colspan）、公式上下标与希腊字母/特殊符号还原成可继续处理的结构。
4. **核得回**：每个文本块、每张表、每条公式都带 `page + block_id + bbox + span_ids + source`；读不出的地方标 `unreadable`/`heuristic_guess`，**绝不靠上下文猜字补齐**。

本 Skill 不要求理解公式科学含义，不生成新结论，只做结构抽取。

# 适用 / 不适用条件

**适用**：有文本层或可 OCR 的科研论文/综述/预印本 PDF（单栏、双栏、多栏；含表格、公式、参考文献、脚注、页眉页脚）。
**不适用（改走其它 Skill 或人工）**：加密且无口令的 PDF；纯图表海报无正文；需要读公式科学含义做推理；需要编辑 Office 源文件而非解析 PDF。
**触发即用**：case.json/task.md 里出现「PDF/文献/解析/提取/表格/公式/扫描件」等词，或素材含 `.pdf`。

# 输入契约（运行时）

- 原始输入：`/input/case.json`（含 `case_id`、`output_contract` 要求的字段、素材路径）与 `/input/task.md`。
- 工作目录 `/app/work`，最终结果与可编辑产物写 `/app/output`。
- `result.json` 必须含 `case_id` + `output_contract` 全部字段；结构遵循本包 `schema/output_schema.json`。
- 平台可用工具（名称即入口，具体参数先探明）：`pdf-text-tool`（文本层+坐标抽取）、`pdf-render-tool`（页面渲染成图）、`ocr-tool`（图像 OCR）、`font-discovery`（字体/乱码排查）、`latex-compiler`（可选，公式预览）、`office-renderer`、`browser-automation`。
- 本包资源路径（安装后）：`/skills/weekly-skill/src/pdf_parse.py`、`/skills/weekly-skill/schema/*.json`、`/skills/weekly-skill/checks/checklist.md`。

# 分步操作流程（按序执行，可重复/幂等）

### 第 0 步 读输入，锁定事实依据
1. 读 `/input/case.json` 与 `/input/task.md`（用 read 工具，不要 cat）。
2. 记下 `case_id`、`output_contract` 字段名、素材文件路径。
3. 用 `find /input -type f` 列出全部素材；**以实际文件为准**，不要凭文件名或标签猜内容。找到 `.pdf`。
4. 若素材是归档/多文件，先解包到 `/app/work`（`unzip`/`tar`），保留原始文件名映射。

### 第 1 步 探测 PDF：文本层 vs 扫描件（关键分支）
对每个 PDF 依次执行，直到能下结论：
1. `pdf-text-tool` 尝试抽取第 1–2 页文本（或 `file` 看 `PDF document` 元信息）。
2. 判据：
   - **有文本层**：每页抽到 ≥ 20 个非空字符、且非全 `�`/乱码 → 走「文本层路径」。
   - **扫描件/无文本层**：每页字符 ≈ 0 或只抽到图片占位 → 走「OCR 路径」。
   - **混合**：部分页有文本、部分页空白 → 有文本页走文本层，空白页走 OCR，`document.tool_path="mixed"`。
3. 加密 PDF：`pdf-text-tool` 报错 `encrypted/password` → 见异常矩阵 E1，**不要**反复重试同一命令。

### 第 2 步 选择工具路径
| 情形 | 工具链 | 产物 |
|---|---|---|
| 有文本层 | `pdf-text-tool` 抽取 span（含 x0,y0,x1,y1,text,size,font） | span 列表 |
| 无文本层/扫描件 | `pdf-render-tool` 每页渲染 200–300 DPI PNG → `ocr-tool` 逐页识别（保留 word box） | span 列表 |
| 文本层乱码（字体 ToUnicode 缺失） | 先 `font-discovery` 排查；仍乱码则对乱码页走 render+OCR | span 列表 |
| 工具不可用/失败 | 降级：text → render+OCR → 仅 render 供人工；`pdf_parse.py --from-text` 只能做单栏退化 | 见异常矩阵 |

**工具参数先探明再批量跑**：先用 1 页试跑，确认返回的 JSON 字段名（是 `x0/y0/x1/y1` 还是 `x/y/w/h`），再对全文档执行。每次命令看 `[exit code: N]`，非 0 先排查再继续。

### 第 3 步 归一化为 span.json
把第 2 步任何工具的 span 输出统一转成 `schema/span_schema.json` 格式（UTF-8，坐标 pt，原点左上）：
```json
{"source":"paper.pdf","unit":"pt","origin":"top-left",
 "pages":[{"page":1,"width":612.0,"height":792.0,"rotate":0,
   "spans":[{"text":"...","x0":72.0,"y0":100.0,"x1":200.0,"y1":110.5,"size":10.0}]}]}
```
要点：
- 页码用**物理页码**（1-based，按文件内顺序）；若文档页序错乱，另建 `page_reading_order` 映射。
- `rotate != 0` 的页：先把坐标旋回 0° 再写入（否则列判定全错）；不会旋转就标 `uncertainty`。
- 若工具给 `x/y/w/h`，脚本 `normalize_span` 会自动转 `x0/y0/x1/y1`，但 `width/height` 建议补上。

### 第 4 步 文本块组装 + 多栏阅读顺序（跑脚本）
```bash
python3 /skills/weekly-skill/src/pdf_parse.py assemble /app/work/spans.json --out /app/work/blocks.json
```
脚本做的事（`--self-test` 可验证核心逻辑）：
- 纵向投影 + 逐水平条带内部沟槽投票 → 判列带（缩进/通栏标题不会误判成栏）；
- **每个列带独立按 y 聚合行**，避免左右栏同行 y 被并成一行（串栏来源之一）；
- 横跨 ≥2 列带的通栏元素作「锚点」，锚点之间按（列, y, x）排阅读顺序；
- 相邻行垂直间距小且角色/字号一致才并块，否则新块；`lines[]` 保留逐行原文与 `para_break`。

**核对**：打开 `blocks.json` 的 `per_page[].columns`，与 `pdf-render-tool` 该页渲染图比对列边界是否一致。不一致时调 `--min-gap`（默认 12pt；栏间距窄的期刊改 8–10）。

### 第 5 步 表格：行列 + 单元格归属
1. 从 `blocks.json` 的 `per_page[].table_candidates` 拿候选矩形（x0 签名对齐的启发式结果）。
2. 用 `pdf-render-tool` 把候选区域裁剪渲染，目测行列/合并边框，修正 region 四角。
3. 逐表重建：
```bash
python3 /skills/weekly-skill/src/pdf_parse.py table /app/work/spans.json --page 3 --region 60,180,500,600 --out /app/work/table_p3.json
```
4. 校验：`n_rows × n_cols` 与渲染图一致；`rowspan/colspan` 与边框一致；`merged_into` 指向拥有者；空且未解释的格已标 `empty_unexplained`（若渲染图里确实有内容，说明 region 或聚类容差错，修正 `--region`/`--x-tol` 重跑）。
5. 跨页续表：下一页同列签名表格标 `continued_on` 指向上一表；重复表头标 `header_rows`。

### 第 6 步 公式与特殊字符保真
1. `blocks.json` 中 `role=formula` 的块是启发式候选（≥2 个数学/希腊字形，或 `(编号)` + 符号开头）。
2. 对每个候选：用渲染图裁剪公式区，逐字符比对文本层字符。
3. 保真规则：
   - 希腊字母/`± × ≤ ≥ ≈ ≠ ∞ ∂ ∇ ∫ ∑ √ → ∈ ⊂ ∪ ∩ ⊕ ⊗` 保留原 Unicode，`special_chars[]` 给 LaTeX 等价（脚本 `GREEK_MAP`）。
   - 上下标：Unicode 上下标字符（`x²`、`aᵢ`）保留原字符；由排版位移实现的上下标，标 `superscript_note` 并给 `latex` 时用 `^{}`/`_{}`；拿不准写 `latex: null` + `uncertainty: heuristic_guess`。
   - 公式编号 `(3)` 填 `equation_number`，与公式块关联。
4. **不做**完整 LaTeX 重排版，除非该字段明确要求且你逐字符确认过；否则 `latex` 置 null。

### 第 7 步 章节 / 参考文献 / 脚注 / 页眉页脚映射
把 `blocks.json` 的块映射成 `output_schema.json` 结构：
1. **章节**：`role=heading` 的块 → `sections[]`；编号/层级从 `SECTION_RE`（`^\d+(\.\d+)*\.?\s+`）解析，`level`=编号段数；`heading_block_ids` 指向标题块；`parent_section_id` 由编号前缀决定；标题在正文中出现但编号缺时 `number:null` + `uncertainty`。
2. **参考文献**：定位 References/Bibliography 标题后的块，按编号/缩进拆成 `references[]`，每条 `raw_text` 逐字（含标点、DOI 大小写）；`parsed` 只在能确定时填，否则各字段 null + `uncertainty`。
3. **脚注**：`role=footnote_candidate` 的块 → `footnotes[]`，`marker` 取行首标记（`1/*/†/‡/§` 或 `[n]`）；正文中的标记位置记 `page`，正文块该处加注。
4. **页眉页脚**：在 ≥2 页同位置重复出现的行（期刊名、running title、页码）→ `headers_footers[]`，从 `body` 剔除；只出现一次但位于页边 12% 内的页码 → `page_number`。判断用「文本归一化后跨页重复」，不是只看 y 位置。

### 第 8 步 构建 result.json + 可编辑产物
1. 按 `schema/output_schema.json` 组装 `/app/output/result.json`：
   - 顶层必填：`case_id`（原样回填）、`document`、`status`、`body`、`tables`、`formulas`、`figures`、`references`、`evidence`、`uncertainty`。
   - 补 `metadata`（标题/作者/摘要/DOI），只能从原文逐字引用，拿不准置 null + `uncertainty`。
   - `output_contract` 里题目额外要求的字段**逐一补齐**，不得缺字段。
2. 可编辑产物写 `/app/output`：
   - `body.md`（Markdown 正文，按阅读顺序，段落不硬拼）；
   - `tables/*.md` 或 `tables.html`（含 `merged_cells` 注记）；
   - `references.json` / `sections.json`（如需）；
   - 关键页/表格/公式的**渲染预览 PNG**（用 `pdf-render-tool` 裁剪），文件名与 `page/table_id/formula_id` 对应，供人工复核。
3. `status`：全部成功 `success`；部分页失败 `partial`（`limits[]` 写清页码与原因）；整体失败 `failed`。

### 第 9 步 自查（用 checks/checklist.md）
逐项执行 `checks/checklist.md`，把不通过项写进 `result.json.uncertainty[]`（带 `kind/page/block_id`），不要静默放过。至少跑：
```bash
python3 /skills/weekly-skill/src/pdf_parse.py self-test
```
并把 `result.json` 用 `schema/output_schema.json` 校验必填字段（可 `python3 -m json.tool` + 手动核对 required 列表）。

# 领域规则（不可违反）

1. **逐字**：任何 `text` 字段只能来自抽取/OCR 的原文，不得改写、补字、翻译；缺失写 `unreadable`。
2. **保留换行与段落边界**：`body[].lines[]` 保留原行；`body[].text` 用换行连接行，**禁止**把相邻段落 join 成一句。
3. **顺序**：多栏=列优先；单栏=自上而下；通栏元素按其 y 锚定。跨栏拼接是错误。
4. **归属**：单元格只能归属到一行一列（或明确 rowspan/colspan 拥有者），不得把邻行邻列文本塞进一个格。
5. **页眉页脚不入正文**：跨页重复 + 页边 12% 是剔除判据；但正文顶部的章节标题不是页眉（标题不跨页重复）。
6. **诚实**：`confidence` 只能取 high/medium/low/unknown；推断出来的合并单元格、公式候选、OCR 低置信区必须带 `heuristic_guess`/`low`。
7. **幂等**：重跑同一输入应产出相同 `block_id` 顺序与文本；有差异写 `change_log` 并说明原因（工具非确定输出、OCR 随机性等）。

# 输出契约（/app/output）

- `result.json`：符合 `schema/output_schema.json`，含 `case_id` 与 `output_contract` 全部字段。
- `body.md`、`tables/`（Markdown/HTML）、`sections.json`、`references.json`、渲染预览 PNG（文件名含 page/table_id/formula_id）。
- 预览与可编辑产物必须真实生成，不得引用不存在的路径；二进制预览单独保留，不影响 JSON 有效性。

# 证据 / 来源定位规则

- 每个 `body` 块：`page + block_id + bbox + span_ids + source`。
- 每张表：`page + bbox + evidence{block_ids,span_ids}`；每格 `cell_id + span_ids`。
- 每条公式/图：`page + bbox`（图另给 `image_ref` 渲染裁剪）；参考文献：`page + block_id`。
- 结论性字段（标题、DOI、章节归属、公式 LaTeX）都要能回到一个 block 或渲染裁剪图；回不去就标 `uncertainty`。
- `evidence.coverage`：`blocks_with_evidence/total_blocks`、`tables_with_evidence/total_tables` 必须能对账，缺失项进 `unreadable[]`。

# 不确定性与异常处理

## 不确定性标注模板
```json
{"kind":"unreadable|not_reported|conflict|ambiguous|heuristic_guess|missing_data|other",
 "detail":"……", "page":3, "block_id":"p3-b07", "evidence":{"page":3,"block_ids":["p3-b07"]}}
```
- 读不出/模糊/乱码 → `unreadable`；题面要求但原文没有 → `not_reported`；原文自相矛盾 → `conflict`（两处证据都给）；启发式推断（列带、合并单元格、公式角色）→ `heuristic_guess`。

## 异常矩阵
| 编号 | 异常 | 识别信号 | 处置（按序） | 结果标注 |
|---|---|---|---|---|
| E1 | 加密 PDF | text/render 报 `encrypted`、`password required` | 若 case.json 提供口令则带口令重试一次；无口令→停止该文件解析，写 `failed` + `limits` | `is_encrypted:true`、`unreadable` |
| E2 | 无文本层（扫描件） | 每页字符≈0、只有图片占位 | 走 render+OCR；OCR 前可用 `pdf-render-tool` 提 2× 分辨率/去噪重渲染一次 | `is_scanned:true`、`source:ocr`、低置信区 `low` |
| E3 | 图片型表格 | 文本层无该表 span，但渲染图有表 | 裁剪渲染 → OCR 该区域 → 把 OCR word box 转 span 再跑 `table` 子命令 | `source:ocr`、`heuristic_guess`、`low` |
| E4 | 乱码字体（ToUnicode 缺失） | 文本层全是 `�`/无意义符号，或 `font-discovery` 报缺失 | 该页/全文档走 render+OCR；保留原文本层样本作 `evidence` | `unreadable`（原层）+ `ocr`（重识别） |
| E5 | 页码错乱 | 物理页码与印刷页码不一致、缺页/重页 | 记录 `page_reading_order` 映射（物理→印刷）；阅读顺序按印刷序输出，`page` 字段保留物理页号并在 `document` 说明 | `uncertainty` |
| E6 | 旋转页 | `rotate` 非 0，文本坐标错位 | 坐标旋回 0° 再归一化；不会旋转就整页走 render+OCR | `uncertainty`、`source:ocr` |
| E7 | 工具调用失败/超时 | `[exit code: N]` 非 0、输出为空 | 看 stderr；参数重试 1 次；仍失败降级下一工具路径；最后仅 render 供人工并标 `partial` | `failed/partial` + `limits` |
| E8 | 多栏判定错误 | `columns` 与渲染图不符 | 调 `--min-gap`（窄栏 8–10，宽栏 12–16）重跑 `assemble`；仍错则人工按渲染图定列界 | `heuristic_guess` |
| E9 | 合并单元格推断错误 | `rowspan/colspan` 与边框不符 | 用渲染图人工定 owner，覆盖脚本结果并标来源 `manual` | `heuristic_guess`→`manual` |

# 自查清单（精简版，完整见 checks/checklist.md）
1. 页数、行数、题注/脚注/参考文献条数与渲染图一致（提得全）。
2. 每页列数正确、列优先顺序无穿插、无跨栏拼接、通栏元素锚点正确（排得对）。
3. 章节层级/表格行列与归属/公式上下标与希腊字母可还原（拆得清）。
4. 每个块/表/公式有 page+block_id+bbox；读不出的全标 `unreadable`，未报告标 `not_reported`（核得回）。
5. `result.json` 含 `case_id` + `output_contract` 字段；schema 校验通过；重跑幂等。

# 相比裸 Agent 的质量增益

| 裸 Agent 常见错误 | 本 Skill 如何防止 | 可验证方法 |
|---|---|---|
| 只给「看起来像全文」的连续文本，无页码/区块 | 输出契约强制 `block_id/page/bbox/span_ids`，schema 必填 | 抽查任一结论能否按 page+block_id 回到渲染图 |
| 双栏页左右栏混成一行/串栏 | 分带行聚类 + 列优先排序 + 通栏锚点（`pdf_parse.py` 已实现并有自测） | 左栏末段 order < 右栏首段 order |
| 相邻段落被 join 成一句 | `lines[]` 保留逐行与 `para_break`，正文用换行连接 | 抽查 `body[].text` 是否保留原换行 |
| 表格只给扁文本，行列归属丢失 | 独立 `table` 子命令重建网格 + `merged_into` 归属 + Markdown | `n_rows×n_cols` 与渲染图边框一致 |
| 公式希腊字母/上下标失真 | Unicode 保真 + `GREEK_MAP` 给 LaTeX + 上下标标注 | 公式行与渲染图逐字符比对 |
| 扫描件/无文本层直接失败或瞎编 | 探测分支 + render+OCR 降级 + `is_scanned` 标注 | `document.tool_path` 记录实际路径 |
| 读不出靠上下文猜补 | 异常矩阵 + `unreadable/heuristic_guess` 强制标注 | `uncertainty[]` 数量与渲染图模糊区对得上 |
| 重复运行结果漂移 | 确定性 block_id 生成 + `change_log` + 幂等要求 | 重跑 `assemble` 得到相同顺序与文本 |

**公平自评方法**：同输入、同工具、同条件跑「裸 Agent（无本 SKILL）」与「加载本 SKILL」，比较：(1) 抽取块数与渲染图行数的差值（越接近 0 越好）；(2) 双栏顺序抽查错误数；(3) 表格行列对账错误数；(4) 证据覆盖 `blocks_with_evidence/total_blocks` 是否 =1；(5) 端到端耗时与人工校对重跑次数。以上指标都可从 `result.json` 的 `evidence/uncertainty/change_log` 机械计算，无需主观判断。
