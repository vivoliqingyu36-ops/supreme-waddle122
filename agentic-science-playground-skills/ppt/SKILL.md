---
name: paper-to-academic-ppt
description: >-
  把一篇科研论文结构性地改写成可讲、可核验、可编辑的学术 PPT（不是把段落切行）。
  触发词：论文转PPT、学术汇报、论文转演示、学术PPT、组会汇报、答辩PPT、论文解读PPT、
  paper to slides、paper to ppt、academic presentation、conference talk、
  research deck、slide outline、speaker notes、figure-to-slide。
  用于「论文转学术PPT」及任何需要把论文组织成「一页一主张 + 每页挂证据 + 讲解备注 +
  模板合规 + 可导出渲染」的科研汇报任务。
  不用于：科研绘图本身的图形美化、论文写作润色、从零生成论文结论、只贴摘要的流水账。
---

# 用途

把一篇论文变成**结构重写后的页级学术汇报**，交付物是：可编辑的 `.pptx`（或按要求改写的
起始 deck）+ 页级大纲/证据映射 `slide_outline.json` + 讲解备注 + 真实渲染的 PDF/PNG 预览
+ 版本记录，全部能按论文的图/表/公式/章节/页码回溯。六个方向与本 Skill 的硬约束一一对应：

1. **主线提取**：提取「问题 → 方法 → 关键证据 → 结论」，形成页序可讲的叙事骨架；主结论与支撑性细节分离。
2. **页结构与信息分层**：一页一条主张，bullets ≤6 且为可讲短语（≤120 字符），长段落改写成短语，不超信息密度。
3. **图表引用与证据保留**：每页绑定具体图/表/公式/数据，保留编号、单位、图注、必要条件；示意图绝不冒充实验数据，数字/单位绝不改写，他人结果绝不归属本文。
4. **讲解逻辑与备注**：备注写过渡/强调/被问时的补充证据，**不得**逐字重复页面文字。
5. **模板约束与版面适配**：在给定 master/layout 的占位符、字号层级、配色、页脚规则内排版，处理长标题、多图并列、大表格。
6. **导出渲染与可编辑性**：交可编辑源 + 真实 PDF/PNG 预览；字体/图形/项目符号跨机不崩；记录模板/字体/软件版本。

本 Skill 只负责「论文内容如何变成可讲、可核验、可编辑的 PPT」，不负责精读结论的生成、
不负责科研绘图美化、不负责学术写作润色。

# 适用 / 不适用条件

**适用**：有文本层或可 OCR 的科研论文/预印本/技术报告（PDF/Markdown/HTML），配一个可编辑的
PPTX 模板或起始 deck；需要页级主张、证据映射、讲解备注和导出预览的场景。

**不适用（改走其它 Skill 或人工）**：加密且无口令的 PDF（见 E1）；纯图形海报无正文；
需要创作论文未给出的新结论；需要做科研绘图的图形美化/重绘（本 Skill 只引用、不重画）；
需要按单位/会议**完全自定义**版式而模板文件缺失（无模板只能退化为纯结构大纲，见 E6）。

**触发即用**：`case.json`/`task.md` 出现「论文/PPT/汇报/演示/幻灯片/讲稿/备注/模板/页数」，
或素材含 `.pdf` + `.pptx`。

# 输入契约（运行时）

- 原始输入：`/input/case.json`（含 `case_id`、`output_contract` 字段、素材路径、页数/时长上限）
  与 `/input/task.md`；素材按题面给（论文 + 模板/起始 deck）。
- 工作目录 `/app/work`，最终结果与可编辑产物写 `/app/output`。
- `result.json` 必须含 `case_id` + `output_contract` 全部字段；结构遵循 `schema/ppt_schema.json` 的 `ResultJson`。
- 平台可用工具（名称即入口，参数先探明）：`pdf-text-tool`（文本层+坐标）、`pdf-render-tool`（页渲染成图）、
  `ocr-tool`（图像 OCR）、`font-discovery`（字体/乱码排查）、`office-renderer`（Office→PDF/PNG）、
  `latex-compiler`（公式预览，可选）、`browser-automation`（网页/在线审阅，可选）、`scientific-python`
  （python-pptx / matplotlib / lxml 等，用于读模板与写 deck）。
- 本包资源路径（安装后）：`/skills/weekly-skill/src/ppt_outline.py`、`/skills/weekly-skill/schema/ppt_schema.json`、
  `/skills/weekly-skill/templates/slide_outline.md`、`/skills/weekly-skill/checks/checklist.md`。

# 分步操作流程（按序执行，可重复/幂等）

### 第 0 步 读输入，锁定事实依据
1. 用 read 工具读 `/input/case.json` 与 `/input/task.md`（不要 cat）。
2. 记下 `case_id`、`output_contract` 字段名、素材路径、`slide_limit`（页数上限）、`audience`/`time`（若有）。
3. `find /input -type f` 列出全部素材；**以实际文件为准**。找到论文（`.pdf/.md/.html`）与模板/起始 deck（`.pptx`）。
4. 归档/多文件先解包到 `/app/work`，保留原始文件名映射。
5. 每次命令看 `[exit code: N]`，非 0 先排查再继续。

### 第 1 步 解析论文（复用阅读 Skill 的抽取思路，产出可定位文本）
1. 对论文 PDF：`pdf-text-tool` 试抽前 1–2 页；判据同「阅读」类 Skill：
   - 每页 ≥20 非空字符且非全 `�` → 有文本层；
   - 每页字符 ≈0 或只有图片占位 → 扫描件 → `pdf-render-tool` 200–300 DPI 渲染 + `ocr-tool` 识别（保留 word box）；
   - 部分页空白 → 混合路径，`document.tool_path="mixed"`。
2. 用 `pdf-render-tool` 把每页渲染成 PNG（200 DPI 起步）存 `/app/work/render/page_%03d.png`，供后续核对图表与版面。
3. 产物：`/app/work/paper_text.json`（正文段落、图表题注、公式、参考文献，均带 `page`，尽量带 `bbox`）。
   数字、单位、图/表编号、方法名、结论表述**逐字**抄录，不翻译、不改写。

### 第 2 步 提取主线（problem → method → evidence → conclusion）写 paper_skeleton
按 `schema/ppt_schema.json` 的 `PaperSkeleton` 组装 `/app/work/paper_skeleton.json`：
1. **problem**：论文要解决的研究问题（从摘要/引言），`claim` 一句，`locator{page,section,where}`。
2. **gap**：现有方法缺什么/为什么重要（引言倒数段落），可空但空要标 `not_reported`。
3. **method**：核心做法一句话 + 它引用的公式/示意图 `refs`（如 `["formula:1","fig:1"]`）。
4. **key_evidence**：每条关键结果一条，`claim` 一句 + `refs`（对应图/表）+ `bullets`（支撑短语）。
   判定主结论 vs 支撑细节：只有能直接回答 problem 的结果进 `conclusion`，其余进 `key_evidence`/backup。
5. **conclusion**：一条 take-home 结论（不是把摘要再抄一遍）。
6. **limitations**：论文自述或可判定的边界（可空标 `not_reported`）。
7. 全部 claim 必须带 `locator`；拿不准写 `confidence:low` 并在 `uncertainty` 标注。

### 第 3 步 建证据索引 evidence_index（图/表/公式/数据）
为论文中每个可引用的对象建一条 `EvidenceItem`，字段见 `ppt_schema.json`：
1. `id`：稳定命名 `fig:N`/`tab:N`/`formula:N`/`data:sN`（N 用论文原始编号）。
2. `kind`：figure/table/formula/data。
3. `role`：**figure 必须区分** `data`（实测结果截图，如折线/柱状/箱线/显微图）与
   `schematic`/`illustration`（原理示意图、流程图、装置示意）。拿不准的标 `role:null` + `uncertainty:ambiguous`，
   **宁可按示意图处理也不许当数据**。table 一律 `data`；formula 用 `formula`/`derivation`。
4. `owner`：`paper`（本文结果）/ `cited`（引用他人）/ `other`（第三方数据）。
5. `label`：逐字编号（`Figure 2`、`Table 1`、`(3)`）；`caption`：逐字题注（可截断标省略号）。
6. `locator`：`{page,section,where}`，能加 `bbox` 就加。
7. `data_points`：从该图/表抄出的关键数字/单位/条件，**逐字**：`{value:"41", unit:"%", condition:"n=120, five seeds", locator}`。
   读不出的数字写 `missing_data`，不猜值。

### 第 4 步 生成页级大纲并校验（跑脚本，这是契约门）
```bash
python3 /skills/weekly-skill/src/ppt_outline.py build /app/work/paper_skeleton.json \
  --out /app/work/slide_outline.json --limit <slide_limit> --template /app/work/template_spec.json
python3 /skills/weekly-skill/src/ppt_outline.py self-test   # 确认校验器可用
```
脚本自动：按 canonical 顺序分页（title→problem→gap→method→每证据一页→conclusion→limitations→thanks）、
给每页绑定证据并复制 locator/label、从 `data_points` 生成 `data_verbatim`、生成 `evidence_map`、
跑契约校验并把报告写入 `slide_outline.json.contract`。校验失败（exit 3）**必须**逐条修正到 exit 0。
页数超限时脚本自动折叠（去 thanks → 限制并入结论 → 多余证据并成 backup 页）并写 warning；
warning 要读，判断是否需要人工调整（见 E7）。

### 第 5 步 读模板/起始 deck（第 0 步找到的 .pptx）
1. 用 `scientific-python`（python-pptx）读模板：
   ```python
   from pptx import Presentation
   prs = Presentation(template_path)
   for i, ly in enumerate(prs.slide_layouts):
       print(i, ly.name, [(ph.placeholder_format.idx, ph.placeholder_format.type, ph.name) for ph in ly.placeholders])
   ```
2. 产出 `/app/work/template_spec.json`：`{template_file, layouts:{layout_name:{placeholders:[...]}}, defaults:{fonts,colors,footer}, constraints:{title_max_chars, body_max_chars, body_max_bullets}}`。
3. 若素材是「起始 deck 需要在其上改写」（而非空白模板）：逐页列出已有 slide 的 layout、shape、text，
   决定「保留哪页、改哪页、新增哪页」，**先复制原 deck 再改**，不要从空白重做（保留单位版式）。
4. 主题字体/配色从 `prs.slide_masters[0]` 与主题 XML 读出，写进 `template_spec.defaults`。

### 第 6 步 逐页写内容与讲解备注（把 stub 换成真备注）
对 `slide_outline.json` 每页：
1. 保底：claim 一句话（≤160 字符）；bullets 短语（≤6 条、≤120 字符、不用句号结尾）；长段落改写为
   「主语+动词+数字/单位」的可讲短语，禁止把正文段落按句号切行。
2. 绑定证据：只引用本页主张真正需要的图/表/公式；`use` 按脚本规则（data/context/reference），不要手改。
3. 重写 `notes`（覆盖脚本生成的 stub，stub 只是占位）：写「过渡到本页的一句话 / 本页要强调的数字与单位 /
   被问时的 backup 证据」，**不得**逐字重复 claim/bullets（≥8 字符子串）。
4. 引用 `cited/other` 结果的页，notes 必须含「先前/他人/据文献/prior work」等归属词。
5. 写完再跑一次 `validate`，确认 0 错误。

### 第 7 步 生成可编辑 .pptx（按模板占位符填，不覆盖主题）
用 python-pptx 写 `/app/output/deck.pptx`，逐页：
1. 选 layout：与 `slide_outline.json` 每页 `layout.layout_name` 一致（脚本已按图/表/内容选好，必要时手调）。
2. 填占位符：title→title placeholder，bullets→body placeholder（每 bullet 一段，保留项目符号），
   图→picture placeholder（**优先用论文原图裁剪**，用 `pdf-render-tool` 按 bbox 裁 PNG，别用低清截图），
   表→content 或独立 table shape（见 E10/E11）。
3. 字体/字号/颜色**沿用模板主题**，不要 set 到硬编码字体覆盖主题；确需覆盖时记进 `versions`。
4. 页脚/页码按模板 footer 规则填（会议名/单位/页码）。
5. 标题过长：先缩短（保留术语）→ 按短语换行 → 降字号到模板允许下限，并写 `overflow_plan`。
6. 每页 notes 写进 slide.notes_slide.notes_text_frame（讲稿跟页走）。
7. 保存二进制 `.pptx` 文件；再用 python-pptx 重新打开验证可编辑、每页 shape 数非 0。

### 第 8 步 导出渲染与可编辑性检查
1. `office-renderer`（或 LibreOffice headless）把 `deck.pptx` 导出 `/app/output/deck.pdf`；
   再对首页/结果页/表格页导出 PNG（至少 3 张，文件名含页号）。
2. 用 `pdf-text-tool` 或 pdftotext 抽 PDF 文本，确认**文本可选**（不是整页图片）、数字/单位未变、bullet 符号在。
3. 用 `font-discovery` 检查导出 PDF 嵌入/替换了哪些字体；缺字体 → 换系统可用等价字体并记录（见 E5）。
4. 逐页目测 PNG：无文本出框、图未越界、标题/表格可读；发现溢出回第 7 步修 `overflow_plan` 重渲。

### 第 9 步 组装 result.json + 版本记录 + 最终自查
1. 按 `ppt_schema.json` 的 `ResultJson` 写 `/app/output/result.json`：
   - `case_id` 原样回填；`output_contract` 字段**逐一补齐**。
   - `status`：全成功 `success`；部分页失败 `partial`（`limits[]` 写页码与原因）；整体失败 `failed`。
   - `artifacts`：`{outline_json, pptx, pdf, png_previews[], notes_md?}`（路径必须真实存在）。
   - `versions`：`{skill_version, template_file, template_sha256(现算 sha256sum), fonts[], software[]}`。
   - `uncertainty[]`、`change_log[]` 见下文。
2. 跑最终检查：`python3 /skills/weekly-skill/src/ppt_outline.py validate /app/work/slide_outline.json --limit N`；
   逐项过 `checks/checklist.md`；把不通过项写进 `result.json.uncertainty[]`，不静默放过。
3. 核对 `/app/output` 下每个声明路径都存在且非空；二进制预览与 JSON 分开，互不影响有效性。

# 领域规则（不可违反）

1. **一页一主张**：每页 `claim` 唯一，bullets 是该主张的支撑，不是第二条主张；超密度拆页或删点。
2. **主线优先**：页序按 problem→method→evidence→conclusion，不按论文段落顺序搬运；主结论只上 conclusion 页。
3. **数字/单位逐字**：任何 `data_verbatim.value/unit` 与原文一致，改一处即错；原文无单位写 `unit_absent:true`，不许补造单位。
4. **编号逐字且对得上**：`label` 用原文 `Figure 2`/`Table 1`/`(3)`，正文引用与证据索引同号，不重号、不指向不存在的图。
5. **示意图≠数据**：`role=schematic/illustration` 的图只允许 `use=context/reference`，不得当 `data` 展示、不得标成实验结果。
6. **归属诚实**：`owner=cited/other` 的结果只能 `use=reference`，且 notes 有归属词；不得把他人结果写成本文结果。
7. **备注不重复**：notes 不得含 claim/bullets 的 ≥8 字符逐字片段；只写过渡/强调/backup。
8. **模板优先**：字体/字号/配色/页脚沿模板主题，不硬覆盖；改主题要记 `versions` 并说明。
9. **可编辑+可渲染**：交 `.pptx` 源（逐页可编辑，不是整页图片）+ 真实 PDF/PNG 预览；两者都要能由他人按 `versions` 复跑。
10. **幂等**：同输入、同模板、同 limit 重跑应得到相同页序/claim/refs；有差异写 `change_log` 并说明（工具非确定输出等）。

# 输出契约（/app/output）

- `result.json`：符合 `schema/ppt_schema.json` 的 `ResultJson`，含 `case_id` + `output_contract` 全部字段。
- `deck.pptx`：可编辑源；`deck.pdf`：整份渲染预览；`preview_p*.png`：至少首页/结果页/表格页预览。
- `slide_outline.json`：页级大纲 + 证据映射 + 契约报告（也放 `/app/output` 供复核）。
- `notes.md`（可选）：按页导出讲解备注。
- `template_spec.json`（可选）：读模板产出的约束记录。
- 所有声明路径必须真实存在；二进制产物单独保留，不影响 JSON 有效性。

# 证据 / 来源定位规则

- 每页主张：`claim_locator{page,section,where,bbox?}`；每处证据：`ref + label + locator`（自页内复制自 evidence_index）。
- 每个数字/单位：`data_verbatim{ref,value,unit,condition,locator}`，`value` 必须等于 evidence_index 里 `data_points.value`。
- `evidence_map` 每条：`ref → slides[] + status(used/unused) + owner/kind/role/label/locator`；`unused` 要写 `unused_reason`。
- 结论性字段（claim/结论/归属/编号）都要能回到一个 locator 或渲染裁剪图；回不去就标 `uncertainty`。
- `coverage_complete` 校验：evidence_index 每条要么被引用要么显式 `unused`；`all_refs_located` 校验：引用必有 locator。

# 不确定性与异常处理

## 不确定性标注模板
```json
{"kind":"unreadable|not_reported|conflict|ambiguous|heuristic_guess|missing_data|other",
 "detail":"……", "locator":{"page":3,"section":"Results","where":"Figure 2"}}
```
- 图/数字读不出 → `unreadable`/`missing_data`；题面要求但原文没有 → `not_reported`；原文自相矛盾 → `conflict`（两处证据都给）；
  角色/归属/字号启发式判断 → `heuristic_guess`；页码或编号拿不准 → `ambiguous`。

## 异常矩阵
| 编号 | 异常 | 识别信号 | 处置（按序） | 结果标注 |
|---|---|---|---|---|
| E1 | 加密 PDF | text/render 报 `encrypted/password` | case.json 给口令则带口令重试 1 次；无口令→停止该论文，`status=failed`+`limits` | `unreadable` |
| E2 | 无文本层/扫描件 | 每页字符≈0 | 走 render+OCR；OCR 前提高 2× 分辨率/去噪重渲一次 | `is_scanned:true`、低置信区 `low` |
| E3 | 公式为图片 | 文本层无公式字符，但渲染图有公式 | 裁剪渲染，`latex-compiler` 或人工核对符号；不能确定就 `latex:null`+`heuristic_guess` | `heuristic_guess` |
| E4 | 编号冲突/图对不上 | 正文引 `Figure 3` 但索引里无 fig:3，或两图同号 | 以渲染图实际编号为准重建索引；仍冲突标 `conflict` 并给两处 locator | `conflict` |
| E5 | 字体缺失/导出替换 | `font-discovery` 报缺，PDF 文本字体被替换 | 换系统可用等价字体（同族/等宽→等宽），记录替换关系进 `versions` | `heuristic_guess` |
| E6 | 模板缺失 | 素材无 .pptx，无法按占位符排版 | 退化为纯结构大纲（slide_outline.json + notes.md + Markdown 预览），`status=partial` 说明无模板 | `not_reported` |
| E7 | 页数超限 | `contract` 报 count>limit 或 build 折叠 warning | 读折叠 warning：先删 backup/thanks，再并限制页，最后多余证据进 backup 页；仍超则按「主结论优先」取舍并写 limits | `limits[]` |
| E8 | 占位符不足 | 模板 layout 缺 title/picture/content | 换 layout；没有可用 layout → 手动 add textbox/picture 到 slide 并标 `heuristic_guess` | `heuristic_guess` |
| E9 | 多图并列溢出 | 图片越画布/被压扁 | 按 picture 占位符数定 `2-up/grid`，保持宽高比，每图保留 `Figure N` 标号；仍放不下分页 | `overflow_plan` 更新 |
| E10 | 大表格溢出 | 表格列/行超出画布 | 节选支持本页主张的列/行，其余放 backup 页并注明「节选，完整见 Table N」 | `overflow_plan` 更新 |
| E11 | 渲染失败 | office-renderer 报错或输出空 | 看 stderr；换 LibreOffice headless 重试 1 次；仍失败交 .pptx + 说明，`status=partial` | `failed/partial` |
| E12 | 重复运行漂移 | 两次 build 输出不一致 | 比对 diff（忽略时间戳）；定位非确定来源（OCR/字体），写 `change_log` | `change_log` |

# 自查清单（精简版，完整见 checks/checklist.md）

1. 主线：narrative 顺序正确、conclusion 回答问题页、主结论与细节分离、每页 claim_locator 可回溯。
2. 页结构：一页一主张、bullets ≤6 且短语化、单页密度 ≤600 字符、无「段落切行」。
3. 证据：引用有 locator、数字/单位逐字、示意图≠数据、他人结果有归属、编号对得上、覆盖完整。
4. 备注：非空（title/thanks 除外）、不逐字重复、说明过渡/强调/backup。
5. 模板：layout 存在于模板、占位符够用、字体字号配色页脚沿主题、无溢出。
6. 导出：.pptx 可逐页编辑、PDF/PNG 真实存在、PDF 文本可选、bullet/图不崩、versions 记录齐。
7. result.json 含 case_id + output_contract 字段；status 如实；uncertainty 全标注；重跑幂等。

# 相比裸 Agent 的质量增益

| 裸 Agent 常见错误 | 本 Skill 如何防止 | 可验证方法 |
|---|---|---|
| 把摘要/正文段落按顺序贴页，主线丢失 | 强制 canonical 页序 + 主结论/支撑分离 + `narrative_order_ok` | `narrative_arc` 与 required roles 检查 |
| 一页塞多个主张、长句溢出 | `one_claim_per_page` + bullet 长度/数量/密度预算 | validate 报错 + 渲染 PNG 目测 |
| 图编号与正文引用错位、指向不存在的图 | 每引用必有 `ref∈evidence_index` + label 逐字比对 | `all_refs_located` 与 label 检查 |
| 示意图当实验数据、数字单位被改写 | `role` 区分 + `no_schematic_as_data` + `data_verbatim` 与源逐字比对 | validate 报错（改一个数字即失败） |
| 他人结果写成本文结果 | `owner` 三分类 + `no_other_attribution` + notes 归属词 | validate 报错 |
| 备注缺失或逐字重复页面 | `notes_non_verbatim` + 非空要求 + stub 换真备注 | 抽查 notes 是否复读页面 |
| 覆盖模板配色/页脚、占位符错用 | 读 master/layout 产 template_spec，按 layout 填占位符，不硬编码字体 | 生成后读 shape 字体/颜色与主题对比 |
| 换机字体崩、交付不可编辑 | 交 .pptx 源 + 真实 PDF/PNG + `versions` 记录模板哈希/字体/软件 | 重新打开 .pptx + 抽 PDF 文本核对 |
| 重跑结果漂移 | 确定性 `build` + `change_log` + 幂等要求 | 两次 build 的 diff 为空 |

**公平自评方法**：同输入（同论文、同模板、同软件版本、同 slide_limit），分别跑「裸 Agent（不加载本 SKILL）」
与「加载本 SKILL」，比较：(1) `contract.errors` 条数（应为 0 vs >0）；(2) 每页 claim 能否回溯到论文
图/表/章节的抽查正确率；(3) 数字/单位与原文逐字一致率（随机抽 10 个数字）；(4) 示意图被误当数据的次数；
(5) 备注重复页面文字的次数；(6) 端到端耗时与人工重排页数。以上均可从 `result.json` 的
`contract/evidence_map/versions/change_log` 机械计算，不依赖主观判断。
