---
name: literature-translator
description: >
  Translate academic/scientific papers (PDF or plain text) into a verifiable,
  bilingual paragraph-aligned result. Core guarantees: a real locked term
  glossary (same term -> same translation across title/abstract/body/captions/
  conclusion), 1:1 paragraph numbering across pages/columns/sections, protected
  numbers/units/formulas/citation markers, and per-paragraph traceability with
  explicit uncertainty marking. Triggers on: 文献翻译, 论文翻译, 学术翻译,
  文献翻译技能, 术语表驱动翻译, 术语一致, 术语统一, 段落对照, 双语对照,
  长文分段翻译, 跨页翻译, 翻译核验, 译文质检, translate paper, translate
  manuscript, academic translation, bilingual alignment, glossary-driven
  translation, translation QA. Do NOT trigger for: creative prose, marketing
  copy, chat messages, code, or any text where per-paragraph evidence and term
  locking are not required; for those, use a general translation approach.
---

# literature-translator

## 1. 用途

把一篇科研文献（PDF 或文本）翻译成**可复核**的双语对照结果，并同时交付：
锁定术语表、段号一一对应的译文、受保护的数字/单位/公式/引用标记、每段译法依据、
以及明确标注的译不准项。本 Skill 不追求“译文通顺”，而优先保证四个可测量目标：

1. **术语稳** — 同一术语在标题、摘要、正文、图注、表头、结论中始终用同一译名，
   由一份真实的术语表执行（脚本强制回填与漂移检查），不是写在提示里的空话。
2. **段落全** — 长文跨页、跨栏、跨章节时不漏段、不重段、不错位；目标段号与
   源段号 1:1 且顺序一致。
3. **关系准** — 指代对象、否定与限定、因果与让步、数字与单位、公式与文献编号
   与原文一致。
4. **可核验** — 每段译文能指回源段落（页码/行号/段号）并写明译法依据；译不准
   的部分显式标注，绝不“含糊带过”。

配套资源（与 SKILL.md 同目录）：`src/translate.py`（标准库脚本，负责分段、术语、
保护、对齐、QA）、`templates/term_glossary.md`、`schema/translation_schema.json`、
`checks/checklist.md`。下文 `<SKILL_DIR>` 指 **SKILL.md 所在目录**（例如
`/skills/weekly-skill`）。运行时若某个文件缺失，按本文件内联的手工流程等价执行——
**规则不依赖脚本也能成立**，脚本只是加速与防错。

## 2. 适用 / 不适用

- 适用：期刊论文、预印本、综述、学位论文章节、会议论文；有可定位的段落/图表/
  公式/参考文献；目标语以中文为主（也支持其他目标语，术语表语言可改）。
- 不适用：纯创意文本、营销文案、聊天记录、代码、歌词；或任务只要“大意/摘要式
  翻译”且不要求回到原文。出现这些情况时直接按通用翻译处理，不启用本 Skill。
- 聚焦但可裁剪：允许只翻译一个明确段落区间（如 Results 一节），此时仍须保证
  该区间内段号 1:1、术语锁定、可核验，并在结果中写明覆盖边界。

## 3. 输入契约

- 原始输入在 `/input/case.json` 与 `/input/task.md`；素材按题面提供（通常是
  实际 PDF，**没有预抽取的答案层**，必须读真实文件而不是靠文件名猜测内容）。
- `case.json` 含 `case_id` 和 `output_contract`（要求的字段列表）。任务必读。
- 工作目录 `/app/work`，最终结果与可编辑产物放 `/app/output`。
- 未知的：源语言默认自动判定（见 5.1），目标语言默认中文；若 `task.md` 指定
  其他语言，以 `task.md` 为准。
- 运行预算：64 次模型请求、900 秒、每次回复 ≤16384 token。**先产出可用的部分
  交付物并逐步改进**；每个阶段把中间结果写盘（`/app/work/*`），不要全攒在内存。

## 4. 分步操作流程

### 4.0 装载与定界
1. 读 `/input/case.json`，记录 `case_id` 与 `output_contract` 的全部字段名。
2. 读 `/input/task.md`，确认：要翻译的文献区间（全文或某节）、目标语言、
   额外交付要求。
3. 定位素材路径（`case.json` 中给出或按题面相对路径）。若素材缺失：产出
   `status=failed` 的 result.json，说明缺哪个文件，不臆造内容。

### 4.1 取得源文本层
4. 若素材是 `.txt/.md/.json`：直接读取为 UTF-8 文本。
5. 若素材是 PDF：优先跑
   `python3 <SKILL_DIR>/src/translate.py extract --pdf <pdf> --out /app/work/source.txt`。
   脚本会依次尝试 PyMuPDF → pypdf → pdfminer → 系统 `pdftotext -layout`。
   - 得到文本后**检查是否为空或明显乱码**；空文本=无文本层，转异常矩阵 A-1。
   - 若是扫描件/图片型 PDF，转异常矩阵 A-2（OCR 或手动誊写，标记低置信）。
   - 双栏 PDF：优先用 PyMuPDF 按 block 顺序重排（阅读顺序）；若只有
     `pdftotext -layout`，先确认没有左右栏交错，再分段。**列边界不得当作
     段边界**。
6. 把抽取方式（native-text-layer / pdftotext / pymupdf / pypdf / pdfminer /
   ocr / manual）记入 `result.source.extraction_method`；若用了 OCR，记
   `ocr=true` 且所有段 `confidence=low`。
7. 保留页码证据：抽取时若工具提供页码，写入段落 JSON 的 `page` 字段；至少保证
   每个段落有 `start_line/end_line`，用于回查。

### 4.2 源文分段（段号是全文唯一主键）
8. 跑分段：
   `python3 <SKILL_DIR>/src/translate.py segment --source /app/work/source.txt \
     --out /app/work/source_paragraphs.json --text-out /app/work/source_paragraphs.txt`
   （OCR 文本加 `--ocr`；无空行的密集文本加 `--dense`。）
9. 人工核对 `/app/work/source_paragraphs.txt`：
   - 标题、图注（Fig./Table 开头整行）、表头、公式块、正文段落各得独立段号；
   - 跨页被切断的段仍是**一个**段（段内换行被合并）；
   - 段数 == 文献实际段数；缺段/多段就先修源文本再重跑，不要带病翻译。
10. 段号规则：`P0001` 起连续编号；**全程以它为唯一主键**，页码只是附加证据。

### 4.3 建术语表并在翻译前锁定
11. 生成候选：`python3 <SKILL_DIR>/src/translate.py candidates \
      --source /app/work/source.txt --out /app/work/glossary_draft.md --domain "<学科>"`。
12. 人工/模型审校候选，补充正文中明显重要的领域术语、缩略语、化学式、专有名词，
    填入 `templates/term_glossary.md` 的 6 列表格（term / translation / variants /
    context / first_location / status）。规则：
    - 化学式、基因/蛋白名、专有名词保留不译的：`translation` 直接写等于 `term`
      （如 `MoS2 → MoS2`），避免被 QA 误报“漏译”。
    - 真正要统一的术语：`status=locked`，一个术语只允许一个译名。
    - 尚不确定的：`status=uncertain`（译名不确定但必须标注）或 `pending`（暂不使用）。
    - `first_location` 填首次出现的段号。
13. **锁定即约束**：翻译开始后，任何 locked 术语的译名不得在正文中出现第二种。
    要改译名，必须先改术语表该行，再重跑 QA（4.7）。

### 4.4 抽取并保护数字/单位/公式/引用标记
14. 跑 `python3 <SKILL_DIR>/src/translate.py protect \
      --source /app/work/source.txt --out /app/work/protected.json \
      --mask-out /app/work/masked.txt`。
15. 检查 `/app/work/masked.txt`：数字、单位、`[1,3]`/`(Smith et al., 2019)` 引用、
    `Fig. 1`/`Table 2`/`Equation (2)`/`Section 3.1` 编号、行内公式都应变成
    `⟨NUMBER_0001⟩` 之类的占位符；未被占位的数字/引用要手动补进 protected.json。
    显示公式块保持原样（只译其周围的文字）。

### 4.5 逐段翻译（携带上下文 + 锁定术语 + 占位符）
16. 对 `source_paragraphs.json` 的每个段，按段号顺序，用下面的**固定提示模板**
    发起一次翻译（把模板中的占位符替换为真实内容）。**一次只译一段**；绝不把
    两段合成一段，也不重排顺序。

> 翻译请求模板（每段一条）：
> ```
> 你是学术文献译者。目标语言：<target_language>。只翻译下面这一段，不增删句子，
> 不合并也不拆分段落。
>
> 本段 ID：<P####>（kind=<heading|body|caption|formula|table>）
> 源文（其中 ⟨XXXX_0001⟩ 是受保护占位符，必须原样保留，不得改动或翻译）：
> <source_text_or_masked_text>
>
> 本段会用到的锁定术语（term = 唯一译名，必须照用）：
> <该段出现的每个 locked term 一行：term → translation>
>
> 上文译文结尾（供指代/衔接参考，不要重复其内容）：
> <上一段译文的最后 200 字符，或“（无）”）>
> 下文源文开头（供预判指代，不要翻译它）：
> <下一段源文首句，或“（无）”）>
>
> 输出格式（只输出这个，不要解释）：
> [<P####>] <译文>
> 规则：
> 1. ⟨...⟩ 占位符一字不动、数量不少。
> 2. 术语表里的译名必须逐字使用；术语表没有的词按学科规范翻译。
> 3. 数字、单位、公式、[n]/作者-年份引用、图表/公式编号照抄或按目标语规范局部化
>    （“Fig. 1”可作“图 1”，但编号“1”必须保留）。
> 4. 否定（not/no/without/lack/unable…）和限定（only/all/at least/approximately/
>    must/may…）必须译出，不得漏掉或反向。
> 5. 因果/让步/转折连词（because/therefore/however/although/despite/while…）必须
>    保留关系，不得简化成并列。
> 6. 指代词（it/this/these/the former/the latter/which）在译文中要能指回明确对象；
>    源文有歧义时，译文里补出名词。
> 7. 译不准或看不清的地方，用 ⟦译文或原文⟧【原因】标注；读不出的地方写
>    ⟦未译⟧【原因】，绝不猜一个像样的数字或公式。
> ```
17. 把每段返回的 `[P####] <译文>` 按序拼成 `/app/work/target_masked.txt`。
    如果模板用的是 `masked.txt` 作源文，译文里还是占位符，下一步恢复。

### 4.6 恢复受保护片段 + 组装双语对齐
18. 若用了 masked 流程：
    `python3 <SKILL_DIR>/src/translate.py restore --masked /app/work/target_masked.txt \
      --tokens /app/work/protected.json --out /app/work/target.txt`。
    恢复后**逐段抽查**数字/单位/引用是否回到原文值（尤其 `10^6`、`cm2/Vs` 这类）。
19. 组装对齐与双语稿：
    `python3 <SKILL_DIR>/src/translate.py align --source /app/work/source_paragraphs.json \
      --target /app/work/target.txt --out /app/work/align.json --md-out /app/output/bilingual.md`。
20. 为每个对齐段补 `rationale`（译法依据，例如：“MoS2 保留不译；band gap→带隙
    见术语表；图 1 编号保留”）和 `uncertain`（从译文里 `⟦…⟧【原因】` 解析出的条目）。
    可直接编辑 `align.json`，也可在最后写 result.json 时一并填。

### 4.7 QA 与修复循环（不回绿色不写成功）
21. 跑 `python3 <SKILL_DIR>/src/translate.py qa \
      --source /app/work/source_paragraphs.json --target /app/work/target.txt \
      --glossary /app/work/glossary.md --out /app/work/qa.json`。
    退出码 0=通过；2=有问题（报告仍写入）。逐条处理 qa.json：
    - `paragraph_inventory` → 补译缺失段、删除多余段、恢复顺序；
    - `term_drift` / `term_untranslated` / `term_missing_translation` → 用术语表
      译名回填对应段，或修正术语表后再统一回填；
    - `token_missing` / `number_drift` → 核对该段数字/单位/引用是否被改，改回原文值；
    - `negation_possibly_dropped` / `qualifier_possibly_dropped` → 人工确认该段否定
      或限定是否真的丢了；确认没丢就在 result 里记录“已人工复核，无问题”，
      真丢了就重译该段。
22. 修复后回到步骤 21 重跑，直到 error=0；实在无法消除的项**只能**通过显式
    `uncertain` 标注收口，不能悄悄删掉。

### 4.8 写输出与状态
23. 写 `/app/output/result.json`，字段见第 6 节；`case_id` 必须与输入一致，
    `output_contract` 里要求的字段**原样**也放进 result.json。
24. 可编辑产物：`/app/output/bilingual.md`（必给）；若 `output_contract` 要求
    Office 格式（.docx/.pptx/.xlsx），优先用环境中已有的 python-docx/pptx/openpyxl
    生成并**同时渲染 PDF/PNG 预览**；没有这些库就交付 `.md` + 简单 `.html`，并在
    `change_log` 说明“缺少 Office 库，仅交付 Markdown/HTML 可编辑稿”。
25. 定 `status`：四项目标全过=success；有未覆盖区间或残留 warning=partial（写清
    边界）；无法产出可用译文=failed（写清原因与可人工接管的点）。

## 5. 领域规则

- **术语单一映射**：一个 term（含 variants）↔ 一个 translation，全文唯一；
  标题/摘要/正文/图注/表头/结论共用同一术语表。术语匹配对纯小写词大小写不敏感
  （“monolayer”也命中“Monolayer”），对含大写或数字的术语大小写敏感（“MoS2”≠“mos2”）。
- **数字与单位**：阿拉伯数字、科学计数（6.02e23）、带指数（10^6）、带单位
  （200 cm2/Vs）按原文保留；中文译文可在数字与单位间加空格（“200 cm2/Vs”），但
  数值与单位本身不得改写、不得换算（除非 task 明确要求换算并写明换算依据）。
- **公式**：显示公式原样保留；行内公式按原文符号保留；公式为图片时见异常矩阵 A-3。
- **引用标记**：`[1,3]`、`[1]–[3]`、`(Smith et al., 2019)` 保留编号与作者-年份；
  “Fig./Table/Eq./Section”可局部化为“图/表/式/节”，但编号与字母（1a、S3）必须保留。
- **否定与限定**：not/no/never/without/unless/lack/absent/fails/unable/few(表“少”)
  等否定，only/all/every/any/at least/at most/approximately/exactly/must/may 等限定，
  必须译出且极性（肯定/否定）不变。
- **逻辑关系**：因果（because/since/therefore/thus/hence）、让步
  （although/though/despite/even though）、转折（however/nevertheless/whereas/while
  表对比）、条件（if/unless/provided that）必须保留关系，不合并为“和/并且”。
- **指代**：it/this/these/that/which/former/latter 在译文中指代对象要明确；英文
  省略主语或宾语的地方，中文按需要补出名词，不得产生悬空指代。
- **不擅自改写**：不补写原文没有的结论、数值、引用；不删除原文有的限定。

## 6. 输出契约

`/app/output/result.json` 顶层字段（完整 schema 见 `schema/translation_schema.json`）：

- `case_id`（来自输入）
- `status`：`success | partial | failed`
- `task`：一句话说明做了什么
- `source`：`{file, extraction_method, language, paragraph_count, page_count, ocr}`
- `glossary`：`[{term, translation, variants[], context, first_location, status, note}]`
- `alignment`：`[{source_id, target_id, source_kind, source_text, target_text,
  source_location{page,start_line,end_line}, glossary_terms_used[], rationale, uncertain[]}]`
- `uncertainties`：`[{paragraph_id, span, reason, action, translation_if_any}]`
  （与各段的 `uncertain` 一致，扁平化便于复核）
- `qa`：QA 报告（alignment 清单、issues、term_consistency、summary）
- `protected_tokens`：保护标记清单（可选但推荐）
- `output_contract`：输入要求的全部字段，**原样补齐**
- `change_log`：按顺序记录改了什么、为什么（用于幂等与复现）

`uncertain` 的 `action` 取值：`flagged_only`（标注但给了译文）/ `left_untranslated`
（保留原文）/ `literal_translation`（逐字直译）/ `needs_human`（必须人工）。
`reason` 必须具体：OCR 不清、公式为图片、术语无标准译名、原文残缺、多义等。

## 7. 证据 / 来源定位规则

- 每个关键结论/译法都要能回到源段：给 `P####` + `page` + `start_line-end_line`。
- 术语表每行给 `first_location`；`context` 列放源文片段。
- 数字/单位/引用/公式的保真由 `qa.token_missing` 与 `qa.number_drift` 逐段作证。
- 双语稿 `bilingual.md` 每段并列“Source / Translation / Rationale / Uncertain”。
- 未报告、无法判断、材料冲突三项必须分开写，不得把“无法判断”写成事实。

## 8. 不确定性与异常处理

不确定片段统一语法：`⟦译文或原文⟧【原因】`；读不出写 `⟦未译⟧【原因】`。
每个不确定片段必须进入 `result.uncertainties` 且挂到对应段落。

异常矩阵（遇到即按下表处置，并在 result 中记录）：

| 编号 | 异常 | 处置 |
|---|---|---|
| A-1 | PDF 无文本层 | 先 `pdftotext`/PyMuPDF 确认；确认无文本层则转 OCR 或手动誊写，全部段 `confidence=low`，`extraction_method=ocr/manual`。OCR 失败则 `status=failed`，写明需要人工提供文本。 |
| A-2 | 扫描件 / 模糊 | OCR 且低置信；看不清的数字/公式一律 `⟦未译⟧【OCR不清】`，禁止猜值。 |
| A-3 | 公式 / 表格为图片 | 公式：能读则抄 LaTeX/符号并标 `literal_translation`，读不出标 `⟦未译⟧【公式为图片】`；表格：尽量按行列誊写，列宽错乱标 `uncertain`，不编造缺失单元格。 |
| A-4 | 参考文献无法解析 | 引用标记按原文字符串原样保留（`[12]`、`(Wang et al., 2018)`）；参考文献列表整体保留原文或逐条直译书目字段，不归一化、不猜测 DOI/作者名。 |
| A-5 | 原文残缺 / 被截断 | 只译收到的部分；记录“收到 P0001–P00XX，缺失 P00XX+…”，`status=partial`；不补写缺失内容。 |
| A-6 | 语言混杂 | 目标语之外的引文/术语块视为受保护片段原样保留并注明；同一段落主语言翻译，非主语言块不翻或直译后标注。 |
| A-7 | 加密 PDF / 无法打开 | 有口令则解密再抽取；无口令 `status=failed`，写明文件加密。 |
| A-8 | 段号冲突 / 重复段 | 以源段号为唯一主键重排；重复源段保留一份并记 `change_log`；目标多出的段删除。 |
| A-9 | 模型回复截断（超 token） | 该段标记 `needs_human` 放入 partial，绝不把半句话当整句交付；下次运行续译该段。 |

## 9. 自查清单

见 `checks/checklist.md`（A 输入、B 分段、C 术语、D 保护、E 关系、F 对齐、G 输出）。
提交前至少过一遍 G 组：result.json 合法且含 `case_id`+`output_contract` 全字段；
bilingual.md 每段有源文+译文+依据；`uncertain` 无遗漏；重复运行结构一致。

## 10. 相比裸 Agent 的质量增益

| 裸 Agent 常见错误 | 本 Skill 如何防止 |
|---|---|
| 术语表写进提示但不执行，同一术语译出 3 种名字 | 术语表是数据文件；脚本 `term_drift` 逐段回检，锁定译名缺一次就报错 |
| 长文翻着翻着漏段、重段、错位 | 先分段生成 `P0001…` 主键，目标必须带同号标记；`paragraph_inventory` 比对 1:1 |
| 跨页段被当成两段、跨栏段错序 | 分段器把页/列边界只作证据不作段边界，句中断行合并；QA 检重段/漏段 |
| 数字抄错（200→201）、单位丢失、引用编号漂移 | `protect` 把数字/单位/引用/公式变成占位符，译后 `restore` 原样回填，`number_drift`/`token_missing` 复核 |
| 否定/限定被漏掉或反向 | `negation_possibly_dropped`/`qualifier_possibly_dropped` 触发人工复核 |
| 译文回不到原文、依据靠嘴说 | 每段携带 `source_id`+页码行号+`rationale`+`uncertain`，双语稿逐段并列 |
| 译不准就糊弄过去 | 统一 `⟦…⟧【原因】` 语法，强制进入 `result.uncertainties` |
| 异常输入直接崩 | 异常矩阵 A-1…A-9 逐条给处置，partial/failed 时仍交付边界说明 |

公平自评方法：同一输入、同一术语表口径下，分别记录（a）基础 Agent 与
（b）本 Skill Agent 的三项指标——术语一致率（同一术语全篇译名唯一占比）、
段落完整率（目标段号与源段号 1:1 的占比）、事实保真率（数字/单位/引用/公式
逐段一致占比）。三项都可用 `qa.json` 的 issues 计数直接算出，不靠主观感觉。
