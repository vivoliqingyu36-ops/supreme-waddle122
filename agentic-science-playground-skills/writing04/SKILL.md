---
name: citation-manager
description: 参考文献与引用管理 Skill。当任务涉及“参考文献/引用管理/挂得对/编得顺/收得净/对得上/引用插入位置/编号更新/文献去重/格式转换/来源核验/GB/T 7714/APA/顺序编码制/著者-出版年/脚注/DOI 核验/正文与文献表一致性/引用与论断匹配”等触发词时使用。读取一份稿件与一份文献库，完成引用定位、编号同步、条目去重、来源核验，交付可继续编辑的稿件、同步文献表、逐条来源映射记录与 result.json。Triggers（英文触发词）：citation management, reference/bibliography, deduplicate references, renumber citations, DOI verification, in-text vs reference-list consistency, GB/T 7714, APA.
---

# 参考文献与引用管理 Skill（citation-manager）

## 1. 用途

把一份真实稿件和一份真实文献库整理成“挂得对、编得顺、收得净、对得上”的成品：

- **挂得对**：引用插到真正需要来源支撑的那句话、那个位置，而不是整段末尾或图表注附近。
- **编得顺**：插入/删除/调序后，正文编号与文末列表同步更新，编号连续、交叉引用与上标样式一致。
- **收得净**：同一文献的中英文题名、预印本与正式版、期刊与会议版、不同数据库导出重复出现时合并为一条，并给出可解释的合并依据；同名作者的不同文献不误合并。
- **对得上**：每条引用真实存在、元数据准确，正文论断与被引文献的主题和结论真正匹配，逐句可回溯。

本 Skill 不是文献管理软件，而是一套“判定规则 + 可运行脚本 + 结构化 schema + 逐项检查清单”的流水线，Agent 逐条照做即可产出可复核的结果。

## 2. 适用 / 不适用条件

**适用**：稿件为 .md/.txt/.tex/.docx/.pdf（有文本层）；文献库为 BibTeX/RIS/EndNote/CNKI 导出/JSONL/TSV/纯文本列表；目标规范为 GB/T 7714—2015（顺序编码制）、APA 第 7 版（著者—出版年制）或脚注制；语言为中文、英文或中英混排。

**不适用（触发时先说明限制）**：只要求“写一段话”且无引用诉求；加密 PDF 或纯扫描件且无 OCR 工具时；任务要求自动改写科学结论本身（本 Skill 只做引用管理，不改动论断的实质内容，改内容须显式标注为修改）。遇到不适用情形，仍按第 8 节异常矩阵处理并如实报告边界。

## 3. 输入契约

运行期原始输入固定为 `/input/case.json` 与 `/input/task.md`，素材文件按 case.json 声明的路径提供。必读：

1. `case.json` → `case_id`、`output_contract`（result.json 必须原样包含其全部字段）、素材文件清单与路径。
2. `task.md` → 体裁、受众、目标引用规范（GB/T 7714 / APA / 脚注）、交付格式约束。
3. 素材：稿件（manuscript）与文献库（reference library）各至少一份；可能另有图表、附录、已有参考文献表。

Skill 资源与 SKILL.md 安装在同一目录（通常 `/skills/weekly-skill`）：
`src/refs.py`（去重/编号/校验/格式化，stdlib-only）、`schema/citation_schema.json`（记录结构）、`checks/checklist.md`（验收清单）。
先 `ls /skills/weekly-skill` 定位；找不到时 `find /skills -name refs.py`，仍找不到则按第 4 步流程与第 5 节判据手工执行等价步骤（去重键、编号规则、核验规则都在第 5 节给出）。

工作目录：`/app/work`（快照与中间产物）；最终结果与可编辑产物：`/app/output`。

## 4. 分步操作流程（按序执行，每步落盘）

### 步骤 0 — 定位输入与资源
- `ls -la /input`；读 `case.json`、`task.md`；记录 `case_id` 与 `output_contract` 字段名清单。
- 建 `/app/work/orig`（原始快照）与 `/app/work/mid`（中间产物）。
- 把所有输入文件原样复制到 `/app/work/orig/`（校验用，勿覆盖）。

### 步骤 1 — 读取稿件与文献库（读真实文件，不凭文件名猜测）
- 稿件：按扩展名选读取方式。.md/.txt 直接 `read`；.tex 读源码并保留 `\cite{}`/`\ref{}`；.docx 用文本提取（保留标题/段落结构）；.pdf 用 pdf-text-tool 提文本，无文本层用 ocr-tool。
- 文献库：.bib/.ris/.jsonl/.tsv/.txt 直接读文本；CNKI 导出若为 .txt（制表符分隔）按 TSV 处理；.doc/.xls 先转文本。
- 把稿件全文写入 `/app/work/orig/manuscript.txt`；把文献库原文写入 `/app/work/orig/library_raw.txt`（多个文件则多个快照）。

### 步骤 2 — 抽取引用标记并规范化文献库
- 抽取正文中的三类引用标记：数字 `[1]`、`[1,3]`、`[1-3]`、上标 `[1]`；作者-年 `(Smith, 2020)`、`Smith (2020)`；脚注引用。
- 规范化文献库：
  ```
  python3 /skills/weekly-skill/src/refs.py normalize /app/work/orig/library_raw.txt \
      --fmt auto --out /app/work/mid/refs.jsonl
  ```
  若库为多个格式，逐文件 normalize 后合并；对字段缺失的条目，从稿件/材料中补全，找不到就留空并标 `missing_field`（不编造）。

### 步骤 3 — 构建 claim→citation map（挂得对）
- 把稿件按句切分（句号/分号/编号项边界）。
- 识别“需要来源支撑的论断句”，判定条件（命中任一即需引用）：
  1. 含具体数字、比例、测量值、统计结果；
  2. 转述他人工作、结论、方法或数据（“X 提出/发现/证明…”）；
  3. 比较级或因果断言（“优于/导致/与…相关”）；
  4. 术语定义、方法步骤、数据集/材料出处。
- 每条论断写一条 `ClaimSourceMapping`（字段见 schema）：`claim_id`、`claim_text`（原句引用）、`location`（节/段/句号）、`citation_keys`、`relation`、`evidence_quote`（先占位，步骤 6 填）、`claim_match`（先 unknown）。
- 找不到支撑的句子：`unsupported=true`，进 issues，不入 `citation_keys` 空列表造假。

### 步骤 4 — 决定引用位置与形式
- 按 task.md 指定规范选形式：顺序编码制（数字，GB/T 7714 通常上标）、著者—出版年制（APA 内联）、脚注制。
- 落位规则（顺序编码制）：编号放在被支撑句的句末标点**之前**；一句多引写 `[1,3]` 且每个号对应该句内的并列主张；多句一引时在每个被支撑句后各自放号；综述性泛泛句（“近年来受到广泛关注”）不得只挂一个段尾号，应改写成具体主张再引用，或多源 `[2-5]`。
- 作者-年制：`(Smith, 2020)`；同年同作者多条用 a/b/c 消歧，调用库函数：
  `python3 -c "import sys;sys.path.insert(0,'/skills/weekly-skill/src');import refs,json;print(json.dumps(refs.assign_author_year_suffixes(refs.parse_jsonl(open('/app/work/mid/refs.jsonl').read())),ensure_ascii=False))"`。

### 步骤 5 — 文献去重（收得净）
```
python3 /skills/weekly-skill/src/refs.py dedup /app/work/mid/refs.jsonl --out /app/work/mid/dedup.json
```
- `dedup.json.clusters`（same_work）→ 自动合并为一条，代表记录取 `choose_canonical`（优先有 DOI、优先正式版、再按字段完整度）。
- `candidates_need_human`（candidate_merge）→ **不自动合并**，写入 `result.json.human_review`，每条附 `reason`。
- `kept_separate_same_author`（different_work，禁并）→ 保持两条，附禁并依据。
- 合并后每条写 `provenance`（原始文件+条目 key 列表），保证可回溯。

### 步骤 6 — 来源核验（对得上）
对每条去重后文献执行，结果写 `ReferenceRecord.verification`：
1. 有 DOI：`web_fetch` 解析 `https://doi.org/<doi>`（或 Crossref API `https://api.crossref.org/works/<doi>`）。HTTP 404 → 该 DOI 无记录；返回 JSON → 比对题名/作者/年份/出处。
2. 无 DOI 或 DOI 失败：用 `web_search` 检索 `"<题名>" <第一作者姓> <年份>`（中文源用 cn，英文用 global），从返回记录比对。
3. 判定：`field_match` = exact（关键字段一致）/ partial / mismatch（错配，须纠正条目）；查不到任何记录 → `status=fabricated`，该条目移入 issues 并**不得**留在成品文献表。
4. 每条 `claim_mappings[].evidence_quote` 填被引文献原文片段（步骤 6 拿到的摘要/正文短句）+ `evidence_location`（DOI/页码/章节）。找不到原文 → `claim_match=unknown`，标注“证据不足”。

### 步骤 7 — 编号与同步（编得顺）
1. 把稿件里的引用改写成中间键形式 `[CITE:key]`（key 为文献表 key），多引 `[CITE:k1,k2]`。
2. 编号：
   ```
   python3 /skills/weekly-skill/src/refs.py renumber /app/work/mid/manuscript_keys.txt /app/work/mid/refs.jsonl \
       --out-manuscript /app/work/mid/manuscript_renumbered.txt --out-refs /app/work/mid/refs_ordered.jsonl
   ```
3. 图表注、附录、交叉引用中的文献标记用同一 key 一并替换；`--superscript` 仅当目标规范要求上标时使用，全稿统一。
4. 校验（双向）：
   ```
   python3 /skills/weekly-skill/src/refs.py validate /app/work/mid/manuscript_renumbered.txt /app/work/mid/refs_ordered.jsonl
   ```
   要求 `ok=true`：无 `keyed_missing_in_list`、无 `numeric_out_of_range`、无 `numeric_uncited_indices`。若数字制正文，`numeric_uncited_indices` 非空说明列表有未引用条目：删除或补挂引用。

### 步骤 8 — 写交付物
1. **编辑后稿件**：`/app/output/manuscript.<ext>`（保持可编辑；.tex 保留 `\cite`/`\bibitem` 映射，.docx 用文本+结构，.md 直接写）。上标样式在 .docx/.tex 里落实为格式属性，不只写 `^`。
2. **同步文献表**：`/app/output/refs_synced.<ext>`。渲染目标规范：
   ```
   python3 /skills/weekly-skill/src/refs.py format /app/work/mid/refs_ordered.jsonl --style gbt7714 --out /app/output/refs_synced.txt
   ```
   或 `--style apa7`。渲染为纯文本骨架，中文标点/斜体（刊名、卷号）需在编辑器最终排版时复核，并如实注明。
3. **逐条来源映射记录**：`/app/output/source_map.json`（含 references、claim_mappings、dedup_decisions、issues，按 `schema/citation_schema.json` 结构）。
4. **result.json**：见第 6 节。
5. 若交付 .docx/.pptx/.odt 等 Office 产物，用 office-renderer 生成真实 PDF/PNG 预览放 `/app/output/`，并在 result.json 标注预览路径。

### 步骤 9 — 自查
按 `checks/checklist.md` 逐项打勾；未通过项写入 `result.json.issues`，不要静默跳过。

## 5. 领域规则（可直接照做的判据）

### 5.1 引用落位（挂得对）
- 引用紧跟被支撑句的句末标点前；禁止“段尾堆号”当作兜底。
- 一句多引：每个编号对应句内一个并列主张或数据点；列表号顺序按首次出现。
- 多句一引：每一句被同一文献支撑时，逐句重复该编号（顺序编码制）；或第一句落位、后续句改写为“同一研究还表明”，不省略来源。
- 图表注/表内：在“图 1”“表 2”题注处或表内对应单元格标注来源，独立建 claim 记录（`location.section=figure/table`）。
- 泛泛综述句不配引用；先改写为具体主张（谁、在什么条件下、结论是什么），再落位。

### 5.2 编号与交叉引用（编得顺）
- 顺序编码制编号 = 正文首次出现顺序，文末列表同序；任何插入/删除/调序都重跑 renumber，绝不手工改号。
- 连续号折叠：`[2,3,4]`→`[2-4]`；两个号 `[2,3]` 不折叠；区间用半角连字符 `-`（不接受中文破折号）。
- 上标一致性：全稿正文标记统一上标（GB/T 惯例）或统一非上标；文末列表序号不上标。
- 交叉引用（图/表/式/节编号）与文献编号分开，不共用一个计数域；文献表序号从 1 连续递增，无跳号。
- 著者—出版年制：正文 `(作者, 年份)` 与列表 `作者. (年份). …` 一一对应；同年同姓作者用 a/b/c 后缀。

### 5.3 去重判据（收得净，可解释）
四级键按优先级：
1. **DOI 一致** → same_work（置信 0.99）。DOI 都存在但不同 → different_work（0.98，同名同作者论文的强排除证据）。
2. **题名+第一作者+年份一致** → same_work（0.95）。
3. **第一作者+年份+出处一致但题名不同** → candidate_merge（0.70–0.80，中英题名/预印本与正式版/期刊与会议版），交人工，不自动合并。
4. **同名作者同年份、题名相似度 <0.55 且出处不同/缺失** → different_work（禁并，防误合并同名作者的不同文献）。

合并代表记录：优先 published > preprint，优先有 DOI，再按字段完整度。所有判据与置信度由 `src/refs.py pair_match` 输出，直接写入 `dedup_decisions`。

### 5.4 真实性核验（对得上）
- DOI 是主键：解析失败 ≠ 文献不存在，先走 Crossref 检索/数据库检索再下结论。
- “编造”仅在多路检索（DOI + 题名作者检索）均无命中时才可判定为 fabricated；单路失败标 unresolved。
- 元数据错配（DOI 解析返回的题名/作者与条目不符）→ 以解析结果为准纠正条目，保留修改记录。
- 论断—文献匹配判定：`evidence_quote` 必须是被引文献原文片段；拿不到原文的标 `claim_match=unknown`，禁止凭标题“感觉像”标 matches。

### 5.5 格式与字段
- GB/T 7714—2015 顺序编码制：`作者. 题名[文献类型标识]. 刊名, 年, 卷(期): 起止页.`，有 DOI 补 ` DOI:….`；文献类型标识 J/C/M/D/R/EB 由 `type` 映射。
- APA 第 7 版：卷号/书名斜体需在编辑器落实；纯文本渲染仅提供骨架。
- 关键字段（DOI、卷期页、文献类型、作者、年份）缺失时标 `missing_field`，不删除、不猜值。

## 6. 输出契约（/app/output/result.json）

result.json 必须同时满足两层：
1. **原样包含 case.json `output_contract` 的全部字段**（逐个拷贝键名与类型，一个不缺）。
2. **必含 `case_id`**，再加本 Skill 的信封字段：

```json
{
  "case_id": "<来自 /input/case.json>",
  "status": "success | partial | failed",
  "<output_contract 的全部字段>": "...",
  "citation": {
    "references": [],
    "claim_mappings": [],
    "dedup_decisions": [],
    "issues": []
  },
  "uncertainty": [],
  "human_review": [],
  "change_log": [],
  "artifacts": {
    "manuscript": "/app/output/manuscript.<ext>",
    "refs_synced": "/app/output/refs_synced.<ext>",
    "source_map": "/app/output/source_map.json",
    "previews": []
  }
}
```

- `citation.*` 与 `source_map.json` 结构一致，字段见 `schema/citation_schema.json`；可直接复制 `templates/result.json.template` 再填充。
- `uncertainty`：无法判断/证据不足/待确认项，每条带 `message` 与 `location`。
- `human_review`：candidate_merge、mismatch、unsupported、DOI 失败等需人工确认项，逐条列出。
- `change_log`：每条改动（插/删/移引用、合并条目、纠正元数据）记 `{action, before, after, reason}`。
- `status=partial` 时必须写明“已完成哪些、缺哪些、为什么”；`status=failed` 写明失败原因与可人工接管位置。

## 7. 证据 / 来源定位规则

- 每个 `ClaimSourceMapping` 必带 `location`（节/段/句号/字符偏移）与 `evidence_location`（被引文献 DOI/页码/章节）。
- 每条 `ReferenceRecord` 必带 `provenance`（合并前原始文件+条目 key）。
- 数字、术语、图表、关键论断都必须能指回稿件原始位置或文献原文；新增材料外事实一律禁止，发现即标注并回退。
- `source_map.json` 是成品回溯入口：稿件 ↔ claim ↔ 文献 ↔ 原始库，四层可双向追溯。

## 8. 不确定性与异常处理（异常矩阵）

| 异常 | 识别 | 处置 |
|---|---|---|
| 字段缺失（无 DOI/作者/年份/卷期页） | normalize 后字段为空 | 降级用次级去重键；标 `missing_field`；不编造、不删除条目 |
| DOI 解析失败（404/超时/无网络/被限流） | web_fetch 失败或 404 | 改 Crossref 检索 `title+author+year`；仍失败标 `unresolved`，不直接判 fabricated；重试 1 次，避免 64 次请求预算耗尽 |
| 条目歧义/疑似重复（candidate_merge / ambiguous） | dedup 输出非空 | 不自动合并；全部进 `human_review`，附 reason 与 title_similarity |
| 编号冲突（越界/悬空号/列表未引用条目） | `refs.py validate` 非 ok | 定位具体 key/序号，重跑 renumber 或补删条目 |
| 不支持的文件格式（.doc/.xls/.caj/.pages 等二进制） | 无法按文本读取 | 先转文本（office 提取/pdf-text-tool）；转不出标 `failed` 并保留原文件路径，说明缺何种工具 |
| 文件损坏（乱码/截断） | 读取抛错或全是替换符 | 用 `errors=replace` 读能读部分；记录损坏偏移与可读范围；标 `partial` |
| 加密 PDF | pdf-text-tool 无文本输出且提示加密 | 标 `failed`；无法解密则保留原文件并说明“需明文或解密密钥” |
| 无文本层扫描件 | pdf 无文本层 | 用 ocr-tool；OCR 错字在 `evidence_quote` 后加 `[OCR]` 标注 |
| 中文/英文题名互相搜不到 | 检索无命中 | 换语言再搜（cn/global）；两路都无才可判“查不到” |
| 空文献库 / 空稿件 | 读取后条目/正文为空 | 标 `failed` 或 `partial`，明确“无输入可处理”，不生成空占位成品 |

**幂等与可重复**：所有排序确定性（标题/作者/key 排序，不用随机哈希）；同输入重跑 `dedup`/`renumber`/`validate` 结果一致；重跑前不覆盖 `/app/work/orig` 快照。

## 9. 自查清单（写完 result.json 前逐项过）

见 `checks/checklist.md`（四问 4×6 项 + 出口检查）。核心三条硬闸门：
1. `refs.py validate` 必须 `ok=true`（或所有非 ok 项都有对应 issue 与处置）。
2. 成品文献表里不得有 `verification.status=fabricated` 的条目。
3. `result.json` 含 `case_id` 与 `output_contract` 全部字段。

## 10. 相比裸 Agent 的质量增益

| 裸 Agent 常见错误 | 本 Skill 如何防止 | 验证方式 |
|---|---|---|
| 引用堆在段尾/图表注附近 | 步骤 3 逐句 claim map 强制落位到论断句 | checklist §一 1.1–1.5 |
| 插入/删除后编号错乱、列表不同步 | 步骤 7 renumber 脚本统一重排 + validate 双向校验 | checklist §二 2.1–2.6 |
| 重复条目不合并或误合并同名作者 | 步骤 5 四级可解释键 + candidate 交人工 + 禁并守卫 | checklist §三 3.1–3.6 |
| 编造/幻觉引用 | 步骤 6 DOI+数据库双路核验，fabricated 隔离 | checklist §四 4.1–4.6 |
| 论断与文献错配 | evidence_quote 逐条原文匹配，拿不到标 unknown | checklist §四 4.3–4.4 |
| 无法回溯来源 | provenance + source_map 四层双向可追溯 | 输出契约 §7 |
| 格式/标点不一致 | format 统一渲染 + 全文正则核对上标与区间 | checklist §二 2.5 |
| 缺字段静默丢弃或编造 | missing_field 显式标注，不猜值 | 异常矩阵第 1 行 |

**公平自评方法**（用于对比 base Agent，同输入同条件）：
1. 同稿同库同目标规范，分别运行 base 与 Skill Agent。
2. 计数指标：`issues` 数量、`validate.ok`、编号连续性（列表 1..N 无缺）、去重精度（对人工黄金集算合并/禁并的准确率）、编造检出率、claim_match 为 unknown/mismatch 的占比。
3. 效率指标：人工需逐条核对的条目数、返工轮次（以 `change_log` 与 `human_review` 长度近似）。
只报告实际观测，不编造分数；平台提供的白板/基准以平台数据为准。

## 11. 与文件资源的对应关系

- `src/refs.py`：normalize / dedup / renumber / validate / format / self-test 六个子命令，stdlib-only，Python ≥3.8；先 `python3 src/refs.py self-test` 验证环境。
- `schema/citation_schema.json`：ReferenceRecord、ClaimSourceMapping、VerificationRecord、DedupDecision、CitationIssueReport 的字段定义；写 `source_map.json` 与 `result.json.citation` 时对照。
- `checks/checklist.md`：四问逐项验收清单，运行期最后一步执行。
- `templates/result.json.template`：result.json 信封模板（含 output_contract 占位说明），复制后填充。
- `README.md`：调用方式、方法说明、限制与最小示例（标注 EXAMPLE）。
