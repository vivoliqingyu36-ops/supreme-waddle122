---
name: intro-related-work-writer
description: >-
  撰写、改写、补全或逐条核验学术论文的"引言与相关工作"（研究背景 / 相关工作 / 研究空白 / 贡献），
  并把每条事实、转述、空白和贡献绑定到来源证据，或显式标注为作者判断。
  触发词：写引言、引言写作、introduction、相关工作、related work、研究背景、research background、
  研究空白、research gap、贡献表述、contributions、补引用、核对引用、核对贡献、引用与论断对齐、
  citation check、分不清相关工作、空白缺乏依据、贡献对不上。
  四问判据：立得住、分得清、说得实、对得上。
  不适用于：纯参考文献排版/格式转换（不做内容核验）、没有任何输入材料的凭空写作、
  要求编造实验数据或引用的任务、只翻译不改写的任务。
---

# 引言与相关工作写作 Skill（intro-related-work-writer）

## 1. 用途

把一份科研事实底稿（论文草稿、方法/图表/实验说明、参考文献库）加工成**可以直接进入论文的引言与相关工作**，并且每一步判断都能被复核。产出四件东西：

1. **可编辑草稿**：研究背景 / 相关工作 / 研究空白 / 贡献 四部分齐全、彼此承接的正文。
2. **来源映射记录**：每条论断 → 引用键或文件定位或「作者判断」标记。
3. **比较矩阵**：相关工作按同一维度分组比较，而不是逐篇摘要。
4. **result.json**：含 `case_id` 与题面 `output_contract` 要求的全部字段、运行状态、不确定项与修改记录。

核心原则（贯穿全程）：**事实与来源一一绑定，写不出来源就写成「作者判断/无法判断」，绝不补造**。四个问题各自的判据见 §6，逐项覆盖检查见 §9 与 `checks/checklist.md`。

## 2. 适用 / 不适用条件

**适用**（出现任一即进入本流程）：

- 任务要求生成、改写或补全「引言 / Introduction / 相关工作 / Related Work / 研究背景 / 研究空白 / 贡献」中的一部分或全部。
- 任务要求「补引用、核对引用、核对贡献、引用与论断对齐」。
- 任务提供论文材料 + 参考文献库，且要求产出可复核的成稿与来源记录。

**不适用**（不要套用本流程，改用对应做法）：

- 只要求把参考文献条目从一种引文格式转成另一种（无内容核验）→ 做纯格式转换，不做四问判据。
- 没有任何事实底稿/参考文献，只给一句「写一篇引言」→ 先索取材料；材料始终缺失时按 §8 的「文献库为空」处置并如实报告，不得虚构引用。
- 任务核心是生成实验数据、跑实验或伪造数字 → 拒绝，并说明这是本 Skill 的边界。

## 3. 输入契约

运行期输入固定为 `/input/case.json` 与 `/input/task.md`；题面提供的素材文件路径由二者给出。**不要根据文件名或标签假设内容**，必须实际打开文件读取。

从 `case.json` 与 `task.md` 中提取以下事实（字段名可能变化，按语义识别，缺失即记缺失）：

- `case_id`：优先取 `case_id`，其次 `id`；都没有则用 `case.json` 文件名并标注。
- `output_contract`：题面要求的全部输出字段（逐字保留；result.json 必须包含它们）。
- 事实底稿来源：论文草稿 / 方法说明 / 图表题注 / 实验表 / 结论段落 / 参考文献库（bibtex、json、ris、md 或 pdf 参考文献页）的文件路径或内嵌文本。
- 受众与文体：目标期刊/会议/学位、学科、是否为短篇会议引言（约 1–2 段）还是长综述式引言（多段 + 相关工作小节）。
- 格式约束：引文体系（数字 [1] / 作者-年份 / IEEE 序号）、语言（中文 / 英文 / 双语）、字数或段落上限、必填小节名。
- 已有素材中是否已写好部分引言（需要改写还是从零写）。

PDF 用平台的 pdf-text-tool 提取文字；扫描件（无文字层）先用 OCR-tool。**只依据真实读到的文本，不依据领域标签补造内容**。

## 4. 分步操作流程（按序执行，每步产出落盘）

> 工作目录 `/app/work`；最终产物与 result.json 放 `/app/output`。**尽早落盘、逐步改进**：先写可用的部分草稿，再迭代；任何一步失败都保留已完成的中间文件。

### 步骤 0：读题 + 建事实底稿目录

1. 读 `/input/case.json`、`/input/task.md`，记录 §3 的全部字段到 `/app/work/contract.md`。
2. 列出全部素材文件路径，逐个 `read`/pdf-text-tool 读取；把每份素材的**原文关键句**（不是自己的转写）摘录到 `/app/work/facts.md`，每条标注「文件 + 行号/页码 + 原文引用」。
3. 如果某素材打不开、乱码或无文字层，按 §8 对应行处置，不重试同一失败方式。

### 步骤 1：定位「本文」事实与「他人工作」事实

把 facts.md 分成两类：

- **本文事实（P）**：本文要解决的问题、方法（模型/算法/技术路线）、数据集与评价方式、图表编号与内容、实验结果数字、结论。**这些是贡献表述的唯一证据源**。
- **他人工作事实（W）**：每篇可引文献的——作者/年份/出处（DOI 或 URL）、解决的问题、方法路线、数据集与评价、**作者自己宣称的结论**、**适用条件**、**局限**。只记录原文写了的内容；没写就写「未报告」。

产出 `/app/work/paper_facts.md`（本文）与 `/app/work/works_facts.md`（他人，每篇一个小节）。

### 步骤 2：确定目标与格式约束

1. 从 contract.md 取受众/文体/格式。**明确写出**：引文体裁、引文体系、语言、字数上限、小节标题要求。
2. 若 task.md 未指明引文体系 → 默认「数字编号 [n]，按首次出现顺序」，并把该假设写入 result.json 的 `assumptions`。
3. 若未指明语言 → 默认用任务描述语言写正文，并在 result.json 标注。

### 步骤 3：给每篇候选文献建「事实卡」

对 works_facts.md 的每篇文献填一张卡（字段见 `schema/writing_schema.json` 的 `relatedWorkRow`）：

- `work_key`（如 `w1`、`smith2023`）、作者、年份、出处、DOI/URL（**照抄来源，来源没有就留空，绝不编 DOI**）
- `problem_setting`：解决什么问题、什么假设/设定
- `method_route`：技术路线（如「监督式对比学习」「符号回归」「基于图神经网络的预测」）
- `data_eval`：用什么数据、怎么评
- `stated_conclusion`：作者自己宣称的结论（原句或贴切转述 + 原文定位）
- `applicability`：作者声称/材料可支持的适用条件
- `limitation`：作者自己承认或材料中明确指出的局限（没有就写「未报告」，**不可替他写局限**）
- `evidence_loc`：以上各条的原文定位（文件+行号/页码）

一张卡只允许来自该文献自身的原文；跨文献混淆是硬错误。

### 步骤 4：建比较矩阵（分得清的机制）

1. 选一个**主分组维度**：优先 `problem_setting`（同类问题归一组），同一问题下按 `method_route` 细分；不要按时间或按作者顺序罗列。
2. 把事实卡排进矩阵（行=文献，列=问题设定 / 方法路线 / 数据与评价 / 结论 / 适用条件 / 局限），表格模板见 `templates/intro_structure.md`。
3. 在矩阵里只写**可在同一维度上比较**的差异：谁的设定更宽、谁的路线牺牲了什么、谁的评测覆盖了什么。写不出的比较项留空，不硬比。
4. 每组产出 1 句「组内差异句」：`A 与 B 都在 X 上……，但 A 用 Y 路线、限制在 Z，B 用 W 路线、牺牲了 V`。这句将成为相关工作段落的主干。

产出 `/app/work/comparison_matrix.md`。

### 步骤 5：只从已引文献的缺口推导空白（说得实的机制）

对每个候选空白，**先归类**，只允许以下四类（定义与最少证据数写入 `schema` 的 `gapRecord`）：

1. `shared_limitation`（共同限制）：≥2 篇已引文献的 `limitation` 字段存在同向缺口。
2. `uncovered_scenario`（未覆盖场景）：存在一个具体场景，任何已引文献的 `problem_setting`/`data_eval` 都没覆盖；要写清「哪篇覆盖了什么、差什么」。
3. `conflicting_conclusion`（冲突结论）：≥2 篇已引文献的 `stated_conclusion` 在同一指标上互相矛盾。
4. `no_basis`（无依据）：以上三类都凑不齐证据。**此时空白只能写成「候选空白（作者判断，不由已引文献推出）」或干脆不写空白**，绝不伪造一篇引用去背书。

每个空白记一张 `gapRecord`：`gap_type`、依据文献 keys、依据原文定位、`this_paper_fill`（本文哪个方法/实验/图对应填补）。**本文填补方式必须来自本文事实（P），不允许用他人工作的做法冒充本文贡献。**

产出 `/app/work/gaps.md`。

### 步骤 6：写四部分正文（每句带 claim ID）

按 `templates/intro_structure.md` 的骨架写。**边写边给每句话挂 claim 标签**，claim ID 形如 `c01`、`c02`，连续编号，段落级或句级皆可，但**每个含事实/判断的断言都必须有 ID**。四个部分的写法要求：

- **研究背景（立得住）**：先点出具体研究脉络（点名 2–3 个里程碑工作及其推进了什么），再落到**一个具体的、当前的未解决问题**（用技术约束/数据限制/评价缺口说清「为什么现在卡住」）。禁止出现「近年来受到广泛关注」「具有重要意义」这类无信息的空转句；每句要么有引用键，要么有具体事实依据。
- **相关工作（分得清）**：按步骤 4 的组写，每组一段；段首一句点出「这一组在研究什么问题」，随后用组内差异句比较；**转述他人工作必须用其 `stated_conclusion`/`applicability`/`limitation`，不写逐篇摘要**。每处转述末尾带该文献的引用键 + claim ID。
- **研究空白（说得实）**：直接复述步骤 5 得到的 `gapRecord`（类型 + 依据文献 + 局限/冲突/未覆盖处），再写「本文如何填补」。每句空白断言必须带依据的引用键；`no_basis` 类空白必须在正文中或 result.json 中标成「作者判断」。
- **贡献（对得上）**：用编号列表 1/2/3…，每条一个可核对的动作或结果，句式为「我们提出/实现了/证明了 X（对应方法 §/图/表/实验编号）」。**每条贡献末尾标注对应的本文证据定位**（方法段落、图号、表号、实验编号）；没有证据定位的贡献要么删、要么降级为「我们计划」并标未验证。

产出 `/app/output/draft.md`（可编辑正文）。

### 步骤 7：claim → 来源绑定（对得上的前半）

为 draft.md 里的每个 claim 在 `/app/work/source_map.json` 里填一条 `claimRecord`（schema 见 `schema/writing_schema.json`）：

- `claim_id`、`claim_text`、`claim_type`（见 schema 枚举）
- `source`：三选一，互斥——
  - `{ "citation_key": "w3" }`（指向 reference 条目）
  - `{ "evidence_loc": "facts.md#L42" }`（本文事实/文件定位）
  - `{ "author_judgment": true, "reason": "..." }`（作者判断/本技能推断，必须写理由）
- `status`：`cited`（有引用且已核对）、`unverified`（有引用但未核对原文）、`author_judgment`、`conflict`。
- `quote_or_paraphrase`：支撑该 claim 的原文摘句或紧贴转述。
- `needs_human`：布尔。转述超出原文、DOI 查不到、来源冲突时为 true。

规则：**每个 claim 必须有 source；没有 source 的 claim 在步骤 11 会被脚本判错**。

### 步骤 8：贡献 → 证据对齐（对得上的后半）

为每个贡献条目在 source_map.json 的 `contributions` 数组填一条 `contributionRecord`：

- `contribution_id`、`contribution_text`、`evidence`（数组：方法小节号 / 图号 / 表号 / 实验编号 / 公式号，来自本文事实 P）
- `evidence_status`：`verified`（正文里确有此证据）/ `missing`（找不到对应证据，须降级或删除）
- `overclaim_risk`：`none`/`soften`/`drop`。

任何 `evidence_status=missing` 的贡献在草稿中必须已被改写为「我们计划/我们假设」并在 result.json 的 `needs_human` 记录，否则视为未完成。

### 步骤 9：引用核对

1. 收集 draft.md 中出现的全部 `citation_key`，与参考库条目做集合运算：
   - 草稿引用了但库里没有 → 删除该引用并把 claim 降级为 `author_judgment`/`unverified`，记入 change log。
   - 库里有但草稿从未引用 → 保留在库中但标记 `uncited`（供作者判断是否遗漏关键工作）。
2. 逐条核对参考条目元数据（作者/年份/出处/DOI）与来源文件是否一致；有网络时用 `web_fetch`/`web_search` 校验 DOI/URL 能否解析，**查不到只标 `metadata_verified=false`，不补造**。
3. 数字引用按首次出现顺序重排编号，使 [1]..[n] 连续无冲突；作者-年份体系则保证 (作者, 年) 与库一致。
4. 把「关键工作 / 代表性工作 / 近期进展」三类覆盖情况写进 result.json 的 `citation_coverage`（见 §7）。

### 步骤 10：写结果与产物

在 `/app/output/` 落盘：

1. `draft.md`：四部分正文 + 文末（或独立文件）`source_map.md`（claim→来源表、比较矩阵、gap 推导链、贡献→证据表的人类可读版）。
2. `comparison_matrix.md`：从 `/app/work` 复制。
3. `source_map.json`：机器可读的来源映射（与 `schema/writing_schema.json` 对齐）。
4. `result.json`：见 §7 输出契约。**必须**包含 `case_id` 和题面 `output_contract` 的每个字段；缺少任何字段都算未完成。

**先落盘一版可用的 result.json（status 可为 partial），再继续改进**，防止超时丢结果。

### 步骤 11：自查 + 脚本校验

1. 跑 `python3 scripts/claim_map_check.py --source-map /app/output/source_map.json`（脚本只依赖标准库；若参考库单独存为 `/app/work/references.json` 再追加 `--references /app/work/references.json`，缺省用 source_map.json 内的 `references` 数组）。
   - 退出码 0=通过；1=警告（如存在 `unverified`/`author_judgment`/`uncited`）；2=硬错误（缺 case_id、缺 source 的 claim、缺 evidence 的贡献、gap 类型不合法、citation_key 无定义）。**退出码 2 必须修复后再交**。
2. 按 `checks/checklist.md` 逐项打勾，把结果写进 result.json 的 `verification`。
3. 修复所有「四问」未通过项；改完重跑脚本，直到无退出码 2。

## 5. 领域规则（四问的判据 → 可执行检查）

把题面四个问题翻译成**写作时的硬规则**；每条的核对动作见 `checks/checklist.md`。

**立得住（背景）**
- R1 背景必须点名 ≥2 个具体工作/技术里程碑（带引用），禁止「近年来受到广泛关注」式空转。
- R2 背景必须落在一个具体的未解决问题上，并给出**至少一个技术约束/数据限制/评价缺口**作为「为什么现在值得做」的理由。
- R3 背景里每个事实句要么有引用键，要么有本文事实定位，要么标作者判断。

**分得清（相关工作）**
- R4 相关工作按 `problem_setting` 或 `method_route` 分组，每组一段；组内用同一维度比较（含各自取舍/代价），不按时间罗列。
- R5 对每篇工作的转述只能来自它的 `stated_conclusion`/`applicability`/`limitation`；来源没写的局限一律写「未报告」，不代写。
- R6 同一句话里不得把 A 的结论安到 B 头上（由步骤 3 的事实卡保证）。

**说得实（研究空白）**
- R7 每条空白必须归类为 `shared_limitation`/`uncovered_scenario`/`conflicting_conclusion`/`no_basis` 之一，前两类/冲突类必须给出 ≥2（冲突）或 ≥1（未覆盖场景）篇依据文献及原文定位。
- R8 空白段必须写「本文如何填补」，且填补方式来自本文事实 P。
- R9 `no_basis` 类空白不得伪装成有文献支持；必须标「作者判断」。

**对得上（贡献）**
- R10 每条贡献对应一个本文证据（方法/图/表/实验/公式），证据定位可回到正文。
- R11 每条引用键都能在参考库中找到且元数据真实；DOI 查不到只标未核实，不编造。
- R12 贡献不夸大适用范围：只声称本文实验/方法实际支持的范围；超出部分写「我们计划/假设」。

## 6. 输出契约

`/app/output/result.json` 结构（完整 JSON Schema 见 `schema/writing_schema.json` 的 `WritingResult`）：

```json
{
  "case_id": "<from case.json>",
  "status": "success | partial | failed",
  "output_contract": { "<题面要求的每个字段，逐字保留>" },
  "assumptions": [ "<步骤2做出的默认假设>" ],
  "artifacts": {
    "draft": "/app/output/draft.md",
    "source_map_md": "/app/output/source_map.md",
    "comparison_matrix": "/app/output/comparison_matrix.md",
    "source_map_json": "/app/output/source_map.json"
  },
  "claims": [ "<claimRecord…>" ],
  "contributions": [ "<contributionRecord…>" ],
  "gaps": [ "<gapRecord…>" ],
  "citation_coverage": {
    "key_works": ["<已覆盖的关键工作键>"],
    "representative_works": ["<代表性工作键>"],
    "recent_works": ["<近期进展键>"],
    "uncited_in_library": ["<库中有但未引用的键>"],
    "missing_from_library": ["<草稿引用但库中没有的键>"]
  },
  "verification": {
    "four_questions": { "stand_firm": "pass|fail|na", "group_clearly": "...", "gap_grounded": "...", "aligned": "..." },
    "checklist_path": "/app/output/checklist_result.md",
    "script_exit_code": 0
  },
  "change_record": [ { "file": "...", "what": "...", "why": "...", "claim_ids": ["..."] } ],
  "needs_human": [ "<必须人工确认的项>" ],
  "uncertainty": [ "<不确定/冲突项>" ],
  "material_gaps": [ "<材料缺失项>" ]
}
```

字段语义与可取值以 `schema/writing_schema.json` 为准；`output_contract` 里若题面另有字段名，**原样放入**，不要重命名。

## 7. 证据 / 来源定位规则

- 每条 claim 的 `evidence_loc`/`quote_or_paraphrase` 必须能回到具体位置：文件路径 + 行号/页码；PDF 用「页码 + 段落/图号」；网页用 URL + 段落。
- 转述他人工作：`quote_or_paraphrase` 必须是原文献里找得到的句子或紧贴转写；超出原文的推断 → `author_judgment: true` + 理由 + `needs_human: true`。
- 引用元数据（作者/年/出处/DOI）只能从参考库或原文抄；来源没有的字段留空，写 `null`，禁止补造。
- 冲突：两份材料对同一事实给出不同值时，两条都保留、都标 `conflict`，在 `uncertainty` 说明，不静默取其一。

## 8. 不确定性与异常处理（异常矩阵）

识别方式 = 触发条件；处置 = 必须执行的动作，且**不要用另一种方式重试同一失败**。

| 异常 | 识别方式 | 处置 |
|---|---|---|
| 文献库为空 / 无引用 | case.json 无 references/bibtex，或库为空 | 不虚构引用。背景只用本文事实写；相关工作节写成「材料未提供参考文献」；空白标 `no_basis` 或不写；贡献仍可从本文事实写；status=partial，记入 material_gaps。 |
| 引用在来源中找不到 | draft 引用了键 X，但参考库无 X，或库中 X 无正文支撑 | 删除该引用，把对应 claim 降级为 `author_judgment`/`unverified`；记 change_record；不替换成无关文献。 |
| 来源文件打不开 / 无文字层 | pdf-text-tool 返回空或乱码 | 先 OCR-tool；仍失败则标「来源不可读」，该文献移出比较矩阵并说明原因；不凭标签猜内容。 |
| 目标格式/引文体系未知 | task.md 未指定 | 用默认：数字 [n] 按首次出现顺序；小节名用四问默认名；把假设写入 `assumptions`。 |
| 不支持的语言 / 输出语言无法保证 | 任务要求非 zh/en，或无法确认术语准确 | 尽力用目标语言写；拿不准的术语用目标语言 + 中文/英文括注；无法完成时输出英文版并标 partial，记 uncertainty。 |
| 空白缺乏依据 | 步骤 5 凑不出 shared_limitation/uncovered_scenario/conflicting_conclusion | 写 `no_basis`：正文标「候选空白（作者判断）」，或省略空白；绝不伪造引用背书。 |
| 来源冲突 | 两份材料对同一数字/结论不一致 | 都保留、标 `conflict`、记 uncertainty，不静默二选一。 |
| 贡献缺证据 | 某贡献找不到方法/图/表/实验对应 | 降级为「我们计划/假设」并标未验证，或删除；记 change_record。 |
| DOI 解析失败 / 无网络 | 校验 DOI 时 fetch/search 失败 | 保留引用但 `metadata_verified=false`；不编 DOI；记 uncertainty。 |
| 超字数 | 草稿超过约束 | 先删空转句/冗余修饰，**不删 claim→来源绑定**；仍超则报告边界。 |
| 引用编号冲突/重复 | 脚本报重复或断号 | 按首次出现顺序重排 [1]..[n]；保持 claim→键映射不变，只改显示编号。 |
| 运行超时/请求用尽 | 接近 900s 或 64 请求预算 | 立即落盘当前 partial 结果 + result.json（status=partial），在 needs_human 写清未完成部分。 |

## 9. 自查清单（速查，详细版在 checks/checklist.md）

提交前逐项确认：

1. 四部分齐全且顺序为 背景→相关工作→空白→贡献（或按题面要求）。
2. 背景点名 ≥2 个具体工作/里程碑，且落在具体未解决问题上（无「近年来受到广泛关注」）。
3. 相关工作按问题/路线分组，每组含同维度比较句，无逐篇摘要。
4. 每条空白有 gap_type 与依据文献（no_basis 除外并已标注）。
5. 每条贡献有本文证据定位（方法/图/表/实验/公式）。
6. 每个含事实/判断的 claim 有 source（引用键 / 文件定位 / 作者判断）。
7. 草稿引用的每个键在参考库存在；库中未引用项已记录。
8. 引用元数据来自来源，DOI 查不到已标 false，未编造。
9. `result.json` 含 `case_id` 与题面 `output_contract` 全部字段。
10. `scripts/claim_map_check.py` 退出码非 2；四问 verification 无 fail。

## 10. 相比裸 Agent 的质量增益

**裸 Agent 常见错误 → 本 Skill 如何防止**

| 裸 Agent 常见错误 | 本 Skill 的防止机制 |
|---|---|
| 背景写成「近年来受到广泛关注」空转 | R1–R3 + 步骤 6 要求点名里程碑、落到具体未解决问题，checklist 第 2 条逐字拦截 |
| 相关工作逐篇摘要拼接、按年份罗列 | 步骤 3–4 强制建事实卡与比较矩阵，R4–R6 要求同维度比较句 |
| 替别人写局限/结论，或张冠李戴 | 事实卡只允许来自该文献原文；`limitation` 缺则写「未报告」 |
| 空白凭空说「少有研究」 | 步骤 5 把空白归类为 4 类并给最少证据数；`no_basis` 必须显式标注 |
| 贡献写成「做了很多工作」但无对应证据 | 步骤 8 每条贡献绑定方法/图/表/实验，`evidence_status=missing` 强制降级/删除 |
| 引用编造、DOI 编造、引用与论断脱节 | 步骤 7/9 逐条绑定 + 元数据回源核对 + 脚本校验 citation_key 集合 |
| 把假设/推断写成事实 | claim `status` 枚举 + `author_judgment` 强制写理由 |

**公平自评方法（可复现）**：同一份案例输入、同一模型与工具权限下，分别用「不加载 Skill 的裸流程」和「本 Skill 流程」各跑一遍，统计四个客观计数：(a) 无来源的 claim 数；(b) 逐篇摘要式段落数（未按维度比较）；(c) 无文献依据的空白断言数；(d) 无证据定位的贡献数。本 Skill 的目标是四项计数都降到 0，且引用可逐条回到来源。对比时记录同一输入路径、同一提示模型、同一运行时长上限，避免把「换模型/换输入」的差异计入增益。

## 11. 资源文件清单

- `README.md`：调用方式、方法、限制、失败处理、自查、最小示例。
- `templates/intro_structure.md`：四部分逐节模板 + 比较矩阵表 + claim→证据表。
- `checks/checklist.md`：四问逐项核对清单。
- `schema/writing_schema.json`：claim→来源、贡献→证据、gap、比较矩阵、result.json 的 JSON Schema。
- `scripts/claim_map_check.py`：标准库校验脚本（`python3`，无第三方依赖）。
