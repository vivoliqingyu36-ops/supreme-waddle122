---
name: literature-knowledge-graph
description: >
  从两篇独立科学论文（JATS 段落文本 + corpus-manifest + material.json 段落索引）抽取科研实体与关系、
  绑定原文证据（source_id + JATS paragraph_id + 原文短引）、做跨篇别名/同义/同物对齐（合并与不合并都留记录）、
  导出可查询图谱并用脚本校验后运行查询、产出带证据的结果子图与 result.json。
  触发词：文献知识图谱、实体关系抽取、科研阅读、别名归一、来源绑定、证据定位、图谱查询、增量更新、
  primary-material、secondary-material、corpus-manifest、material.json、JATS 段落、抽得准、连得对、对得齐、查得到回得去。
  不触发：纯问答/摘要、单一 PDF 无文本层且无 JATS 段落索引、不要求回到原文证据的通用写作任务。
---

# 文献知识图谱构建 Skill（阅读15）

## 1. 用途

把**两篇独立、真实、许可可再分发**的论文文本（`primary-material.json` + `secondary-material.json`，均按 JATS 段落给出）转换为一张**带证据、可查询、可复核**的知识图谱，交付：

- 节点：科研实体（研究者、材料、方法、任务、指标、结论），每个实体绑定 `source_id + paragraph_id + quote`；
- 边：有证据的关系（类型、方向、适用条件、证据强度），不把共现/综述转述/推测当直接证据；
- 对齐记录：跨篇候选同一概念**合并依据**与**不得合并**的冲突/不同对象；
- 查询：≥3 个实际执行的查询及结果子图与证据；
- `result.json`：含 `case_id` 与全部输出契约字段、状态、来源、不确定性、变更记录。

核心目标对应题面四问：**抽得准 / 连得对 / 对得齐 / 查得到、回得去**（逐项检查见 `checks/checklist.md`）。

## 2. 适用 / 不适用条件

**适用**：输入包含论文段落文本 + 段落索引 + 来源清单；任务要求实体关系抽取、证据绑定、图谱导出或查询；需要跨篇对齐与来源回查。

**不适用 / 需降级**：
- 只有单一 PDF 且无文本层、无 JATS 段落 ID：只能标注"无法解析"，不伪造段落位置；
- 任务只要求摘要/翻译、不要求回到原文证据：不套用本流程；
- 材料缺失（任一论文文件不存在）：按 12.1 异常矩阵降级为 partial，不编造另一篇内容。

## 3. 输入契约（运行期路径）

运行期原始输入是 `/input/case.json` 与 `task.md`；素材按题面提供（本包通过 `environment/resources.yaml` 声明，相对该文件路径查找）。**必须实际读文件**，不得凭文件名或标签脑补内容。按以下顺序定位：

1. 读 `/input/case.json`：取 `case_id`、`output_contract`（若有）中的字段名与必需项，作为 `result.json` 的字段来源。
2. 在工作目录内查找（`ls`/`glob` 递归）：
   - `corpus-manifest.json`：列出每篇论文的 DOI、作者、来源哈希、许可证；
   - `material.json`：两篇正文段落的汇总索引（paragraph_id 列表）；
   - `primary-material.json`：第一篇论文正文（JATS 段落）；
   - `secondary-material.json`：第二篇论文正文（JATS 段落）；
   - 可选 `secondary-publisher.xml`：供核对行内公式/上下标线性化，不替代正文段落。
3. 用 `read`/文本工具读上述文件内容；二进制或超大文件先 `file` 判型、按 UTF-8 读取（失败再 latin-1 兜底，见 12.2）。
4. 建立**来源表**（第 5 步），随后进入分步操作。

## 4. 输入硬约束（必须逐条遵守）

1. **位置 = JATS 段落 ID，不是 PDF 页码**。本包无 PDF 页码；禁止把自建的"第 1 页/第 2 页"写成原文页码，禁止推断页码。`paragraph_id` 一律原样抄录材料里的段落 ID。
2. **根 DOI/title/authors 只属于第一篇**。不得套到 `secondary-material.json`；第二篇的 DOI/authors 以 `corpus-manifest.json` 中对应条目为准。
3. **两篇是独立论文**。同篇出现多种文件格式（如正文 + publisher.xml）**不算跨篇证据**。
4. **相同通用方法/材料术语 ≠ 相同实例**。两篇都用 "logistic regression" 或 "AuNPs"，不代表用了同一模型实例、同一物理样品、同一数据集或同一实验条件。只有原文明确指向同一对象才可合并。
5. **不得跨篇合成一个结论**。不得把两篇的条件、样本、数值结果拼成一条"合并结论"；每篇的结论独立绑定各自 `source_id`。
6. **行内公式/上下标被线性化**。按线性化文本抄录引文，不"还原"上下标，也不据公式反推数值。
7. **不提供图像像素、补充附件、底层临床/实验数据**。不得推断图表/附件/底层数据里的数值；只能引用正文明确陈述的内容。
8. **未报告值保留为"未报告"，源内冲突保留并列**。不填 0、不选边、不抹平。

## 5. 分步操作流程

### 步骤 0 — 建立来源表（每篇一行，作为全部 source_id 的事实来源）
对 `corpus-manifest.json` 中每篇论文生成一行：
```
source_id（本图谱内唯一，建议 "primary" / "secondary" 或取 DOI 的稳定短前缀）
| display_title | doi | authors | source_hash | license
```
确认清单里各字段不串篇：根 DOI/title/authors 归 `primary`；`secondary` 用清单中自己那行。

### 步骤 1 — 建段落索引
从 `material.json` 得到每篇的段落列表（`paragraph_id` → 文本或起始位置）。若 `material.json` 只有汇总 ID，用 ID 在对应 `*-material.json` 内定位段落。任何段落 ID 都**原样保留**，不重编号、不转页码。

### 步骤 2 — 固定实体/关系类型（受控词表）
- 实体类型 `entity_type`：`researcher`（研究者/机构/团队）、`material`（材料/样品/试剂/模型实例/数据集）、`method`（方法/流程/算法）、`task`（研究任务/目标）、`metric`（指标/测量量/评估指标）、`conclusion`（结论/发现/主张）。
- 关系类型 `relation_type`：`USES`（使用）、`COMPARES`（比较）、`OUTPERFORMS`（优于）、`SUPPORTS`（支持）、`CONTRADICTS`（矛盾）、`SAME_AS`（跨篇/同篇对齐合并）、`DISTINCT_FROM`（判定为不同对象，显式记录）。
- 证据强度 `strength`：`direct`（原文直接陈述，可建边）、`paraphrase`（作者转述他人/综述转述，弱证据，建边必须注明转述属性且不冒充对原研究者的直接断言）、`inferred`（上下文推断，默认**不建边**、只记候选）、`cooccurrence`（仅共现，**不得建边**）、`speculation`（推测/可能，**不得建边**）。
完整定义与字段见 `schema/kg_schema.json`。

### 步骤 3 — 逐篇逐段抽取实体（抽得准）
对每一篇、每一段：
1. 只抽取**原文真实出现**的对象；不因领域常识补实体（例：原文没提 "sensitivity" 就不建 metric 节点）。
2. 每个实体记录：`id`（`{source_id}.{entity_type}.{序号}`）、`type`、`canonical_name`（规范化名）、`source_id`、`paragraph_id`、`quote`（**逐字短引**，线性化原文，≤ 约 200 字符）、`aliases`（该段出现的缩写/变体，见步骤 4）、`strength`、`note`。
3. 区分**作者自述**与**他人转述**：引文中是 "we used/our results" → 自述；是 "X et al. reported/shown" → 转述，实体照抽但 `strength=paraphrase` 并在 `note` 标明转述来源。
4. 数值型结论只在正文明确给出时抽取（例："accuracy = 0.82 on set A"）；正文没给数值就写 `note:"数值未报告"`。

### 步骤 4 — 归一与对齐（对得齐）
**同篇内部**先归一：同一 source_id 内，仅当缩写展开、大小写、连字符/空格变体、全称-简称**可确证指同一对象**（原文给出 "… (X)" 或 "X, i.e., …" 之类）才合并；否则保留别名列表但**不新建节点**。合并方式：保留一个 canonical 节点，`aliases` 汇总，`merge_of` 列出被并入的临时 id。

**跨篇候选合并**必须过**两步同一指称测试**（两条件同时满足才合并）：
- (a) **字符串别名可对应**：缩写/大小写/连字符归一后能对上；
- (b) **同一指称**：原文或来源信息明确指向同一物理样品/模型实例/数据集/实验条件/同一个人，或两处引用同一文献给出同一对象。
只满足 (a) 不满足 (b) → **不合并**，建 `DISTINCT_FROM` 边并写 `conflict_note`（例："两篇均称 AuNPs，但粒径/合成条件不同，无证据为同一物理样品"）。
**不要强迫每个别名都合并**；没有证据就 keep-separate。所有合并与不合并都写入 `result.json.alignments`。

### 步骤 5 — 抽取关系（连得对）
每条边必须满足：**原文给出了关系语义**，且方向、适用条件与原文一致。
1. 边字段：`id`、`type`（relation_type）、`source`（头节点 id）、`target`（尾节点 id）、`direction`（`out`=source→target，`in` 表示反读）、`source_id`、`paragraph_id`、`quote`、`strength`、`conditions`（适用条件：数据集、粒径、人群、参数等，原文没有就写 `"not stated"`）、`note`。
2. `COMPARES`/`OUTPERFORMS` 必须写清**比较对象、比较维度（metric）与条件**；原文只说 "X 和 Y 都用了" 而无优劣/比较语义 → **不建 OUTPERFORMS**，最多建两条 `USES`。
3. **共现/综述转述/推测不得当直接证据**：`strength∈{cooccurrence, speculation, inferred}` 的关系写入 `result.json.non_edges`（负面证据记录），**不进入 nodes/edges 正式边表**，防止幻觉边。
4. 同篇多文件格式（正文 + publisher.xml）**不产生跨篇边**；跨篇边只当两篇各自原文可定位时才建。

### 步骤 6 — 构建图
按 `schema/kg_schema.json` 写出 `graph.json`（或直接写 `result.json` 的 `nodes`/`edges`）。节点 id 全局唯一；边的两端必须是已存在节点 id。用 `src/kg.py validate` 校验（重复节点、冲突节点、缺失证据、悬空端点、受控词表越界），修复到 0 error。

### 步骤 7 — 运行查询（查得到、回得去）
设计并**实际执行 ≥3 个查询**（示例：某方法用了哪些材料？某指标在哪两篇中被报告且数值为何？某跨篇候选实体是否合并及依据？两节点之间是否有路径？）。
查询类型（schema 定义）：`neighborhood`、`trace`、`path`、`node_by_name`、`node_by_type`、`edges_by_type`。每个查询用 `src/kg.py query` 跑出**结果子图**（含节点对象、边对象、每条证据的 source_id/paragraph_id/quote）。无结果 → `status:"empty"` 并写"为什么空"，不算错误。

### 步骤 8 — 写 result.json
写入 `/app/output/result.json`，字段 = 从 `/input/case.json` 的 `output_contract` 读到的全部字段 + 下述标准字段。必含：`case_id`、`status`（`success`/`partial`/`failed`）、`sources`、`nodes`、`edges`、`alignments`（合并 + 不合并）、`queries`（≥3 个，含结果与证据）、`non_edges`、`unreported`、`conflicts`、`uncertainty`、`change_log`。同时把可编辑产物（graph.json、query 结果 JSON）放 `/app/output/`。

## 6. 领域规则（抽/连/齐/查四条硬规则）

- **抽得准**：实体 = 原文对象；每个实体必须有 `quote`；无原文支撑的概念不建节点。数值只引正文明确给出者。
- **连得对**：关系类型+方向+条件 = 原文语义；`cooccurrence/speculation/inferred` 不建正式边；`paraphrase` 建边必注转述。
- **对得齐**：合并必须"字符串可对应 + 同一指称"双满足并写依据；不同对象显式 `DISTINCT_FROM`；同篇多格式不算跨篇证据。
- **查得到、回得去**：每个查询给结果子图 + 证据；每个节点/边含 `source_id + paragraph_id + quote`；位置是 JATS 段落 ID。

## 7. 输出契约

`/app/output/result.json` 结构（与 schema 的 `definitions` 一致；额外字段为 `output_contract` 要求项）：

```json
{
  "case_id": "<来自 /input/case.json>",
  "status": "success | partial | failed",
  "sources": [{"source_id":"primary","title":"...","doi":"...","authors":["..."],"source_hash":"...","license":"..."}],
  "nodes": [{"id":"primary.method.001","type":"method","canonical_name":"...","source_id":"primary","paragraph_id":"p-...","quote":"...","aliases":["..."],"strength":"direct","merge_of":[],"distinct_from":[],"note":""}],
  "edges": [{"id":"E001","type":"USES","source":"primary.method.001","target":"primary.material.001","direction":"out","source_id":"primary","paragraph_id":"p-...","quote":"...","strength":"direct","conditions":"not stated","note":""}],
  "alignments": [
    {"decision":"merge","canonical_id":"primary.material.001","merged_ids":["secondary.material.002"],"justification":"两篇均指向同一数据集 X（第1篇第p-X段/第2篇第p-Y段）","evidence":[{"source_id":"primary","paragraph_id":"p-X","quote":"..."},{"source_id":"secondary","paragraph_id":"p-Y","quote":"..."}]},
    {"decision":"keep_separate","ids":["primary.material.003","secondary.material.004"],"conflict_note":"两篇均称 AuNPs，但粒径与合成条件不同，无证据为同一物理样品"}
  ],
  "queries": [
    {"id":"Q1","question":"...","type":"neighborhood","params":{},"status":"answered|empty","result_nodes":[...],"result_edges":[...],"evidence":[{"element":"primary.material.001","source_id":"primary","paragraph_id":"p-...","quote":"..."}]}
  ],
  "non_edges":[{"claim":"...","strength":"cooccurrence|speculation|inferred","reason":"仅共现/推测，无直接证据","source_id":"...","paragraph_id":"...","quote":"..."}],
  "unreported":[{"subject":"...","what_missing":"...","note":"原文未报告"}],
  "conflicts":[{"subject":"...","source_a":{"source_id":"primary","paragraph_id":"...","quote":"..."},"source_b":{"source_id":"secondary","paragraph_id":"...","quote":"..."},"note":"两处陈述冲突，并列保留"}],
  "uncertainty":[{"subject":"...","note":"...","level":"low|medium|high"}],
  "change_log":[{"step":"...","action":"...","reason":"..."}]
}
```

## 8. 证据 / 来源定位规则

1. 每个**实质节点**与**每条边**必须有 `source_id + paragraph_id + quote` 三件套；`quote` 是逐字引文（线性化），不用意译替代。
2. `paragraph_id` 原样抄录材料的 JATS 段落 ID；材料缺段落 ID 时写 `"unlocated"` 并在 `note` 说明"段落定位缺失"，**不得**自行发明。
3. 引文必须能通过 `grep` 在对应材料文件里命中（抽查）；命中不了就缩短引文或换相邻句子，仍不行则标记 `uncertainty`。
4. 跨篇证据：每条跨篇边（`SAME_AS`/`DISTINCT_FROM` 或跨篇关系）两侧各给一条定位；**同篇多格式不算跨篇**。
5. 图表/公式/附件/底层数据不可见时，只写"正文未报告该值"，不据图/公式反推。

## 9. 不确定性与异常处理（异常矩阵）

| 异常 | 判定 | 处置 |
|---|---|---|
| 缺 `primary-material.json` 或 `secondary-material.json` | 无法建双源图 | status=`partial`，只对存在的一篇建图；`sources` 中缺的条目 `status:"missing"`；不编造另一篇 |
| 文本无法解析（二进制/乱码/无文本层） | 无法读取 | 先 `file` 判型；UTF-8 失败再 latin-1 兜底；仍失败 status=`failed` 并写 reason；不猜内容 |
| 实体同名不同物（homonym） | 不可合并 | 建两个节点 + `DISTINCT_FROM` 边 + `conflict_note` |
| 缩写无法确证展开 | 不可合并 | 保留原缩写节点，`note:"缩写展开无证据"` |
| 关系证据冲突（一处说优于、一处说相当） | 冲突 | 两条边都保留，`strength` 按各自原文，写进 `conflicts`，不擅自删除 |
| 查询无结果（无该节点/无路径） | 正常空结果 | `status:"empty"` + 说明"为何空"，不算失败 |
| DOI/authors 与清单不一致 | 元数据冲突 | 以 `corpus-manifest.json` 为准，`conflicts` 记录差异 |
| 段落 ID 重复或缺失 | 定位缺陷 | 原样保留，缺失写 `"unlocated"`，`uncertainty` 标注 |
| 未报告数值 | 缺失 | 写 `unreported`，不填 0/均值/猜测 |
| 源内两处陈述冲突 | 冲突 | 并列保留，`conflicts` 记录两处定位 |

## 10. 自查清单（交付前逐项勾选）

见 `checks/checklist.md`；核心：
1. 每个节点/边有三件套证据；quote 能 grep 命中；
2. 无 `cooccurrence/speculation/inferred` 进入正式边表；
3. 每个合并有依据、每个不合并有冲突说明；
4. 无 PDF 页码、无自造"第 1 页"；
5. 根 DOI/authors 只属于 primary；
6. 无跨篇合成结论；
7. ≥3 个查询已执行且有结果子图；
8. 未报告/冲突/不确定性已显式列出；
9. `result.json` 含 `case_id` 与 output_contract 全部字段。

## 11. 相比裸 Agent 的质量增益

| 裸 Agent 常见错误 | 本 Skill 如何防止 |
|---|---|
| 凭常识补 "accuracy/sensitivity" 等未出现的指标 | 步骤 3：实体必须有段落引文，无引文不建节点 |
| 把共现当关系、把综述转述当原作者结论 | 步骤 5 + 证据强度：`cooccurrence/paraphrase/speculation` 分级，弱证据不建或加注 |
| 跨篇把 "AuNPs" 一律合并成一个节点 | 步骤 4 两步同一指称测试：只别名对应不够，须原文指向同一实例 |
| 把两篇数值合成一条结论 | 硬约束 5：结论按 source_id 独立绑定 |
| 自造 PDF 页码 | 硬约束 1：位置一律 JATS 段落 ID |
| 说"图 2 显示…"却拿不到图 | 硬约束 7：不据不可见图/公式反推，只引正文 |
| 查询只给结论不给证据 | 步骤 7：每个查询输出结果子图 + 三件套证据 |
| 冲突证据擅自删一边 | 异常矩阵：冲突并列保留并记录 |

**可验证的公平对照**：同一 `/input/case.json` + 同一素材下，记录 (1) 节点数中带 quote 的比例、(2) 弱证据（cooccurrence/speculation）是否混入边表、(3) 合并数与不合并数、(4) 每个查询是否给定位；四项分别与本 Skill 输出对比，即可复现增益。

## 12. 运行脚本说明

本包资源安装后位于 `/skills/weekly-skill/`（脚本 `/skills/weekly-skill/src/kg.py`，schema
`/skills/weekly-skill/schema/kg_schema.json`，查询模板 `/skills/weekly-skill/templates/queries.template.json`，
检查清单 `/skills/weekly-skill/checks/checklist.md`）。运行时若 `/app/work` 与脚本不同目录，用绝对路径调用。

- `src/kg.py`：仅用标准库（json/argparse/collections），两个子命令：
  - `python3 src/kg.py validate --graph graph.json [--schema schema/kg_schema.json]` → 输出校验报告（error/warning），exit 码 0=通过、1=有 error、2=有 warning；
  - `python3 src/kg.py query --graph graph.json --queries queries.json --out query_results.json [--schema ...]` → 输出每个查询的结果子图与证据；
  - `python3 src/kg.py --self-test` → 用内置 EXAMPLE 图自检（示例数据，非正式案例）。
- 运行期把脚本产出的校验报告与 query_results.json 归入 `/app/output/`，并把查询结果合并进 `result.json.queries`。

## 13. 增量更新（新论文加入时）

保留既有节点 id 与编号；新论文以新 `source_id` 追加：
1. 新实体建新节点（不改旧 id）；
2. 候选同义/同物走步骤 4 两步测试，决定 `merge` 或 `DISTINCT_FROM`，写入 `alignments`；
3. 新关系建新边并绑定新 source 证据；
4. 冲突关系写 `conflicts`；旧查询结果可复跑（幂等：同一输入重复运行产出相同节点/边 id）。
