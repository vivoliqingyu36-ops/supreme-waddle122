---
name: nanopublication-extractor
description: >
  把一篇科研论文的关键结论拆成若干条各自可判断真假的原子断言，为每条断言绑定最小充分证据片段与
  可指向的原文位置（页码/段落/句子/图表/公式），并记录 断言→证据→论文→作者→年份→版本 的完整溯源链，
  最后导出机器可解析的 result.json（字段与 schema/nanopub_schema.json 一致，无需人工清洗）。
  触发词：Nanopublication、断言拆解、断言粒度、证据绑定、证据对齐、来源追溯、provenance、
  assertion decomposition、evidence binding、source metadata、科研阅读、拆得细、对得上、追得回、读得懂、
  最小充分证据、受控关系词表、result.json 结构化导出。
  不触发：纯摘要/翻译/问答且不要求回到原文证据的任务；无任何可读文本且无 OCR 条件的扫描材料
  （此时只输出"无法解析"说明，不伪造内容）；不要求结构化断言输出的通用写作任务。
---

# Nanopublication 抽取 Skill（阅读14）

## 1. 用途

把固定科研案例中的论文结论转换为**可独立核验、可回到原文、可机器解析**的断言集合，交付 `/app/output/result.json`。
核心对应题面四问：

- **拆得细**：一段结论拆成若干条"单一主体 + 单一关系 + 单一对象 + 保留条件/限定"的断言；复合句的并列与因果结构被逐条拆开；绝不把整段摘要塞进一个 `text` 字段。
- **对得上**：每条断言绑定**最小充分证据片段**（逐字引文/图表描述/公式），片段给出可指向的原文位置（页码、段落、句子、图/表/公式编号、字符偏移）。
- **追得回**：`断言 → 证据 → 论文 → 作者 → 年份 → 版本 → 标识符(DOI/PMID/arXiv/URL)` 链路完整，他人能按记录逐条回到原文复核。
- **读得懂**：导出遵守 `schema/nanopub_schema.json` 的字段与枚举，合法 UTF-8 JSON，下游程序可直接解析，无人工清洗步骤。

## 2. 适用 / 不适用条件

**适用**：输入含论文全文/段落文本 + 任务要求"拆分断言、绑定证据、给出来源、结构化导出"；需要把结论变成可逐条验证的知识单元。

**不适用 / 需降级**：
- 扫描版 PDF 无文本层且运行时无 OCR 可用：只能标注 `status=partial`、逐断言 `status="not_extractable"`，不猜测文字内容。
- 只有结论、没有可指向的原文：不做"编造证据"式绑定，断言标 `status="unsupported"`。
- 任务只要求摘要/翻译、不要求回到原文证据：不套用本流程。
- 材料缺失（论文文件不存在）：按第 9 节异常矩阵降级为 `partial` 并写清边界。

## 3. 输入契约（运行期路径）

运行期原始输入是 `/input/case.json` 与 `task.md`；素材按题面提供。**必须实际读文件**，不得凭文件名或标签脑补内容。按顺序：

1. 读 `/input/case.json`：取 `case_id` 与 `output_contract`（若有）中的字段名，作为 `result.json` 的必含字段来源。
2. 读 `task.md`：确认本案例要求抽取的是哪类结论（全文/摘要/某章节/图表结论）。
3. 在工作目录递归查找素材（`ls`/`glob`）：论文 PDF、已抽取文本 `.txt`、`material.json`/`corpus-manifest.json`（若有 DOI/作者/版本/哈希/许可证清单）。
4. 文本优先用 `pdf-text-tool` 抽取；判型用 `file`。抽取失败/无文本层见第 9 节异常矩阵。
5. 把抽取出的正文保存为 `/app/work/paper.txt`（供 `src/nanopub.py --text` 做引文回验），并保留原始 PDF 路径。

## 4. 分步操作流程

### 步骤 0 — 建立来源表（`sources[]` 的事实来源）
为每篇论文建一行 `source`：`source_id`（建议 `src-1`）、`kind`、`title`、`authors`（字符串数组，`FamilyName, GivenName`）、`year`（整数，未知用 `null` 并在 `note` 说明）、`version`、`identifiers`（DOI 优先，其次 PMID/PMCID/arXiv/URL/publisher_id）、`container`（期刊/卷/期/页）。
- 元数据**以材料内的清单/PDF 首页为准**，不凭题面标签补造；清单与正文不一致时以清单为准并把差异写进 `conflicts`。
- 版本字段必须存在：`published`/`author-accepted`/`preprint-v1`/`v1`/`v2`/`unknown` 之一；同一论文多个版本时各建一行 source 并在 `note` 互指。

### 步骤 1 — 抽取正文并建立位置索引
- 用 `pdf-text-tool` 得到逐页文本；记录**页码**为原文页码（PDF 标签页，不是文件内自增序号；两者不同时以 PDF 页面标签为准并注明）。
- 给每页建"段落序号（1-based）→ 段落文本"索引；段内句子按 1-based 编号。`location` 一律引用这个索引：`page`、`section`、`paragraph`、`sentence`，另给 `pointer`（如 `"p.3, Results, para 2, sent 1"`）。
- 引文 `quote` 必须能通过 `grep`/脚本在 `/app/work/paper.txt` 中命中；命中不了就缩短引文或换相邻句，仍不行 → 见异常矩阵。

### 步骤 2 — 定位候选结论句
只对"论文自己给出的结论/发现"建断言：`Results`/`Discussion`/摘要中的发现句、明确的数量/比较/因果/关联陈述。综述转述他人结论、方法步骤、背景常识**不作为本论文的断言**（除非任务明确要求，此时 `certainty.level` 必须标注并写依据）。

### 步骤 3 — 拆解断言（拆得细）
对每个候选结论句，产出若干条断言，每条满足：
1. **一个主体 + 一个关系 + 一个对象**：`subject.label`、`relation`、`object.label` 非空且各为单一实体；主体与对象不同名（同名即主体混淆）。
2. **一句一断言**：`text` 只允许一个句子/一个主张；原文多句时逐句拆开。
3. **并列拆分**：
   - 复合主体 "A and B cause X" → 若 A、B 是各自独立的实体：拆成 "A causes X" 与 "B causes X"；若原文把 "A and B" 当作一个复合物/组合（如 "A and B form a complex"），保留为一条并注明。
   - 复合宾语 "X increases Y and Z" → "X increases Y"、"X increases Z"。
   - 复合谓语 "X increases Y and decreases Z" → "X increases Y"、"X decreases Z"（两条的关系动词、方向各写各的）。
   - 用 `python3 src/nanopub.py decompose --text "<原句>"` 得到并列/因果/条件标记与拆分建议，**逐条回原文验证**后再落字段；脚本建议不是最终答案。
4. **因果链拆分**："X causes Y, which leads to Z" → "X causes Y" 与 "Y leads_to Z" 两条，各自绑定各自证据；不在一条里把 X→Z 直接写成因果。
5. **保留条件/限定**：原文的限定（物种、细胞系、剂量、时间、温度、对照组、设置、人群、in vitro/in vivo、比较对象）**不得丢弃**，填入 `conditions[]`（`slot` + `value`，可加 `verbatim` 原短语）。条件只限定这条断言，不另立一条断言。
6. **极性/量词**：否定主张（"X did not increase Y"）`polarity="negated"`；量词 `all/some/none/specific/not_stated` 照原文，原文没写就 `not_stated`。
7. **关系动词映射到受控词表**（第 5 节）；映射后写入 `relation`（snake_case）+ `relation_type`（类）+ `direction`（符号）。词表外的动词用最接近的受控动词并在 `decomposition.note` 写明映射，脚本会提示 warning 而非静默通过。
8. **每条写 `source_text`**（该断言所来源的原句逐字文本），供脚本做"条件是否被丢弃/是否仍含并列"的机械校验。

### 步骤 4 — 绑定证据（对得上）
对每条断言：
1. 找到**最小充分片段**：最短的一段原文，只要它还包含"主体 + 关系语义 + 对象"（或关键定量数据）。宁可一句，不要整段；把引文缩到承载该主张的最小跨度，并在 `sufficiency.minimality_note` 说明如何裁剪。
2. `evidence_binding.quote`：`quote_type="verbatim"` 时逐字抄录（线性化，不"还原"上下标）；证据在图中 → `quote_type="figure_description"` + `location.figure="Fig. 2B"` + 描述轴/数值/方向；在表中 → `table_description`；在公式 → `equation`。
3. `location`：填 `page/section/paragraph/sentence` 或 `figure/table/equation` + `pointer` + 可选 `span{start,end,text_file}`（在 `paper.txt` 里的 0-based 偏移）。
4. `relation_to_assertion`：`direct`（引文直接陈述该关系）、`inferred`（从图表数据/统计/多句合取读出，`sufficiency.reason` 必须写明推理步骤）、`context`（只是背景，**不能**支撑断言）。
5. `sufficiency.judgment`：`sufficient`（引文单独即可支撑）、`partial`（缺条件/比较对象）、`insufficient`（不支撑）。`judgment != sufficient` 或 `relation_to_assertion != direct` 时 `sufficiency.reason` 必填。
6. 用 `--text paper.txt` 让脚本回验 verbatim 引文是否真的在正文里；不在 → 修引文，不靠记忆。

### 步骤 5 — 补齐溯源链（追得回）
每条断言填 `provenance`：
```json
{"source_id": "src-1", "evidence_id": "e1", "assertion_id": "a1",
 "chain": ["a1", "e1", "src-1"]}
```
- `chain` 顺序固定为 `[assertion_id, evidence_id, source_id]`，脚本逐项核对。
- `source_id` 必须存在于 `sources[]`；`evidence_id` 必须等于该断言 `evidence_binding.evidence_id`。
- 确保 `sources[]` 每行都有 `title + authors + year + version + identifiers`，缺任何一项脚本报 error。

### 步骤 6 — 质量检查（五类问题逐条排查）
按 `checks/checklist.md` 与脚本报告排查，并对照这五类可复现判定：
1. **断言过宽（over_broad_assertion）**：`text` 多句、含并列连词、含因果链、`text` 超 280 字符、或 `source_text` 含限定短语但 `conditions[]` 为空 → 拆开或补条件。
2. **证据不足（insufficient_evidence）**：引文不含主体也不含对象、引文只是背景（`context` 却标 `supported`）、`status=supported` 但 `sufficiency.judgment=insufficient`、引文不在正文中 → 修引文或降级 `status="unsupported"`。
3. **关系类型错误（wrong_relation_type）**：`relation` 动词的类与 `relation_type` 不一致（如 `increases` 配 `associative`）、`relation` 符号与 `direction` 矛盾（如 `increases` 配 `negative`）→ 对齐受控词表。
4. **主体混淆（subject_confusion）**：主体与对象同名、关系方向反了（把"X 受 Y 调节"写成 "X regulates Y"）、转述他人结论当本论文结论 → 回原文改方向/改标注。
5. **来源缺失（missing_source）**：`provenance.source_id` 不在 `sources[]`、来源缺作者/年份/版本/标识符 → 补来源或修引用。

### 步骤 7 — 机械校验（读得懂）
```bash
python3 src/nanopub.py validate --result draft.json \
  --schema schema/nanopub_schema.json --text /app/work/paper.txt --out /app/work/validation_report.json
# exit 0=干净, 1=有 error（必须修到 0 error）, 2=仅有 warning（逐条判定后修复或注明保留）
python3 src/nanopub.py export --result draft.json --out /app/output/result.json \
  --schema schema/nanopub_schema.json --text /app/work/paper.txt --report /app/work/validation_report.json
```
- `export` 会规范化键序、补默认值、把 `quality.checks/issues/summary` 写入产物，输出**合法、可解析、带换行与 2 空格缩进**的 UTF-8 JSON。
- 修复到 `validate` 无 error 再 `export`；warning 允许保留，但必须在 `uncertainty` 或 `decomposition.note` 里写明原因。

### 步骤 8 — 写 result.json
1. 以 `/input/case.json` 的 `output_contract` 字段为准：把 contract 要求的**全部字段**原样并入 `result.json`，再加本包标准字段。
2. 必含：`case_id`（抄自 `/input/case.json`）、`status`（`success`/`partial`/`failed`）、`sources`、`assertions`、`quality`、`unreported`、`conflicts`、`uncertainty`、`change_log`。
3. `status` 与事实一致：全部必需断言可抽取且校验通过 → `success`；部分来源/断言不可用但输出了可用子集 → `partial`；无可用文本 → `failed`。
4. 把可编辑中间产物（`draft.json`、`validation_report.json`、`paper.txt`）也放 `/app/output/`（或子目录），便于复核。

### 步骤 9 — 复查与重复运行一致性
- 重跑一遍 `validate`，确认 exit 0；同一输入重复运行产出相同断言 id/证据 id/链（脚本无随机性，排序确定性）。
- 逐条过 `checks/checklist.md`，把未通过项修复或显式写入 `uncertainty`。

## 5. 领域规则（受控词表）

**实体类型 `entity_type`**：`gene`、`protein`、`drug`、`compound`、`disease`、`phenotype`、`cell_type`、`cell_line`、`organism`、`pathway`、`process`、`method`、`metric`、`dataset`、`model`、`other`。

**关系类 `relation_type`** 与常见动词映射（`relation` 用 snake_case）：

| relation_type | 常见 relation 动词 | direction |
|---|---|---|
| causal（正向） | increases, promotes, induces, activates, upregulates, enhances, accelerates, stimulates | positive |
| causal（负向） | decreases, inhibits, suppresses, downregulates, blocks, reduces, impairs, prevents, attenuates | negative |
| causal（方向不明） | causes, leads_to, results_in, contributes_to, requires, mediates, modulates, regulates, depends_on, drives, triggers | neutral |
| associative | associated_with, correlates_with, predicts, linked_to | neutral |
| comparative | greater_than, less_than, equivalent_to, differs_from | 按词义 positive/negative/neutral |
| definitional | is_a, part_of, expresses, encodes, binds, localizes_to, interacts_with, composes, contains, has_property | neutral |
| quantitative | measured_as, has_value, has_rate, has_prevalence, has_sensitivity | neutral |
| methodological | evaluated_by, detected_by, measured_by, treated_with, compared_against | neutral |

规则：`relation` 必须小写 snake_case；`relation_type` 是闭集枚举；`polarity ∈ {affirmative, negated}`；`direction ∈ {positive, negative, neutral, not_applicable}`；`certainty.level ∈ {reported, inferred, speculative}`；`relation_to_assertion ∈ {direct, inferred, context}`；`sufficiency.judgment ∈ {sufficient, partial, insufficient}`；`quote_type ∈ {verbatim, paraphrase, figure_description, table_description, equation}`；`status ∈ {supported, unsupported, conflict, not_extractable}`。

**四条硬规则**：
- **拆得细**：一断言一主张；并列/因果拆开；条件保留在 `conditions[]`，不写进对象也不丢弃。
- **对得上**：每条断言必须可指向原文位置；引文逐字且最小；`context` 不当证据；图表/公式证据用 `figure_description`/`table_description`/`equation` 并给编号。
- **追得回**：`provenance.chain == [assertion_id, evidence_id, source_id]`；`sources[]` 缺一不可（作者/年份/版本/标识符）；版本与标识符能定位到具体文献版本。
- **读得懂**：字段与枚举遵守 `schema/nanopub_schema.json`；`export` 后产物可直接 `json.load`；不把自由文本塞进枚举字段；未报告写 `unreported`，冲突写 `conflicts`，不确定写 `uncertainty`。

## 6. 输出契约

`/app/output/result.json` 顶层结构（完整字段定义见 `schema/nanopub_schema.json`，`additionalProperties: true` 允许并保留 case 的 output_contract 字段）：

```json
{
  "schema_version": "1.0.0",
  "case_id": "<抄自 /input/case.json>",
  "status": "success | partial | failed",
  "generated_at": "<ISO-8601 UTC>",
  "sources": [
    {"source_id":"src-1","kind":"paper","title":"...","authors":["Doe, Jane"],
     "year":2024,"version":"published",
     "identifiers":{"doi":"10.xxxx/xxxx","pmid":"...","arxiv":"...","url":"..."},
     "container":{"journal":"...","volume":"...","pages":"..."},"note":""}
  ],
  "assertions": [
    {
      "assertion_id":"a1","text":"<单一句子，条件保留>","source_text":"<原句逐字>",
      "subject":{"label":"kinase X","type":"protein","normalized":"X"},
      "relation":"increases","relation_type":"causal","direction":"positive",
      "polarity":"affirmative","object":{"label":"phosphorylation of Y","type":"phenotype"},
      "quantifier":"not_stated","conditions":[{"slot":"cell_line","value":"HEK293T","verbatim":"In HEK293T cells"}],
      "certainty":{"level":"reported","basis":"<依据>"},
      "decomposition":{"method":"condition_extraction|direct|coordination_split|causal_split","note":"<拆解说明>"},
      "evidence_binding":{
        "evidence_id":"e1","quote":"<最小充分片段>","quote_type":"verbatim",
        "location":{"page":3,"section":"Results","paragraph":2,"sentence":1,
                    "figure":null,"table":null,"equation":null,
                    "pointer":"p.3, Results, para 2, sent 1",
                    "span":{"start":120,"end":210,"text_file":"paper.txt"}},
        "relation_to_assertion":"direct|inferred|context",
        "sufficiency":{"judgment":"sufficient|partial|insufficient","reason":"<依据，必要时必填>","minimality_note":"<裁剪说明>"}
      },
      "provenance":{"source_id":"src-1","evidence_id":"e1","assertion_id":"a1","chain":["a1","e1","src-1"]},
      "status":"supported|unsupported|conflict|not_extractable"
    }
  ],
  "quality":{"summary":{...},"checks":[...],"issues":[...]},
  "unreported":[{"subject":"...","what_missing":"...","note":"..."}],
  "conflicts":[{"subject":"...","side_a":{"source_id":"src-1","quote":"..."},"side_b":{"source_id":"src-1","quote":"..."},"note":"并列保留"}],
  "uncertainty":[{"subject":"...","level":"low|medium|high","note":"..."}],
  "change_log":[{"step":"...","action":"...","reason":"..."}]
}
```

## 7. 证据 / 来源定位规则

1. 每条断言有 `evidence_binding.location` 至少一个定位字段（`page/section/paragraph/sentence/figure/table/equation/pointer`）；`verbatim` 引文另给 `span` 偏移。
2. 位置是**原文页码/段落/句子/图表编号**，不是自造的序号；材料只给 JATS 段落 ID 时 `page=null` 且 `pointer` 写段落 ID，**禁止**把段落 ID 换算成页码。
3. `quote` 逐字且最小：脚本用 `--text` 回验是否命中；命中不了就改短/换句，不靠记忆补引文。
4. 图表证据：`location.figure="Fig. 2B"` + `quote_type="figure_description"` + `quote` 写"该面板横轴/纵轴/数据方向"的结构化描述；看不到像素/数值时只写"正文未报告该值"。
5. 同篇多格式（正文 + 出版社 XML）不算两个来源；同一论文不同版本才各建一行 source 并在 `note` 互指。
6. 转述他人结论（"X et al. reported ..."）不当作本论文断言；确需抽取时 `certainty.level` 标注转述来源，不得冒充原作者直接断言。

## 8. 不确定性与异常处理（异常矩阵）

| 异常 | 判定 | 处置 |
|---|---|---|
| 扫描版 PDF 无文本层 | 无法抽取文字 | 先试 `ocr-tool`；有 OCR → 用 OCR 文本，`uncertainty` 标 OCR 误差，引文用 OCR 文本；无 OCR → `status=partial`，逐断言 `status="not_extractable"`，`note` 写"无文本层，人工接管位置=第 N 页图/正文"，不猜内容 |
| 加密 PDF | 无法打开 | `status=partial`，`sources[].status="unparseable"`，`note` 写加密原因；有密码且题面提供则解密重试，否则不猜 |
| 原文无法访问（DOI 死链/无权限/只给摘要） | 元数据可用但正文不全 | 仅对已获文本建断言；拿不到的章节标 `unreported`；`sources[].status="unreachable"`，用已确认的元数据，不补造正文 |
| 证据在图里 | 引文非文本 | `quote_type="figure_description"` + `location.figure/table` 编号 + 结构化描述 + `relation_to_assertion="inferred"` + `sufficiency.reason` 写推理步骤 |
| 断言找不到支撑片段 | 无证据 | `status="unsupported"`、`sufficiency.judgment="insufficient"`、`reason` 写"全文无支撑句"，写入 `unreported`；**不编造引文** |
| 断言 ↔ 证据冲突（引文与断言方向/主体不一致，或源内两处矛盾） | 冲突 | 断言 `status="conflict"`，保留断言与证据，`conflicts[]` 并列记录两侧定位；不擅自删一边、不抹平 |
| 缺字段（作者/年份/版本/DOI 任一缺失） | 溯源不完整 | 写 `"unknown"`（年份 `null`）+ `note` 说明为何缺；`validate` 报 error 时必须修到：有作者、年份 1400–2100、版本、≥1 标识符；无法确认就显式 `unknown` 并 `uncertainty` 标注，不猜 |
| DOI 解析失败/格式异常 | 标识符可疑 | 保留原串 + `note`"DOI 未验证"，`validate` 给 warning；不臆造 DOI |
| 编号冲突（重复 assertion_id/evidence_id/source_id） | 引用混乱 | 重新编号为全局唯一；脚本报 error，修到 0 error |
| 文本乱码/编码错误 | 无法读取 | `file` 判型 → UTF-8 → latin-1 兜底；仍失败 `status="failed"` + reason |
| 图表像素不可见/数值不可读 | 数值缺失 | 写 `unreported`"正文未报告该值/图不可读"，不据不可见图反推数值 |

## 9. 自查清单（交付前逐项勾选）

见 `checks/checklist.md`。核心：① 每条断言一个主张、无并列/因果残留、条件已保留；② 每条引文最小且能在 `paper.txt` 中命中；③ `provenance.chain` 完整且 source 元数据齐全；④ `export` 产物可 `json.load` 且无 error。

## 10. 相比裸 Agent 的质量增益

| 裸 Agent 常见错误 | 本 Skill 如何防止 |
|---|---|
| 把整段摘要塞进一个"断言"字段 | 步骤 3 逐条拆解规则 + 脚本：多句/超长/含并列或因果链 → 报 error/warning |
| 丢条件限定（"在 XX 细胞中"被丢弃） | 步骤 3 第 5 条：条件必须进 `conditions[]`；脚本对比 `source_text` 的条件短语与 `conditions[]`，丢条件 → warning |
| 引文是整段而非最小片段、或引文不在原文 | 步骤 4 最小充分裁剪 + `--text` 回验，引文命中不了 → error |
| 把"相关"写成"导致"（关系类型错误） | 受控词表 + 脚本校验 `relation`↔`relation_type`、符号↔`direction` |
| 主体与对象弄反 | 脚本报 subject==object、主体混淆 issue；步骤 6 逐条回原文核方向 |
| 来源缺作者/年份/版本/DOI | `sources[]` 必填 + 脚本报 error；缺则显式 `unknown` 不猜 |
| 断言与证据冲突被抹平 | `conflicts[]` 并列保留，脚本不删边 |
| 图表结论找不到文字证据 | `figure_description` + 编号 + 推理步骤，标 `inferred` |

**可复现的公平对照**：同一 `/input/case.json` + 同一论文材料下，统计 (1) 含多句/并列的"过宽断言"条数、(2) `verbatim` 引文命中率（脚本 `--text` 校验）、(3) `provenance.chain` 完整率、(4) `relation` 受控词表覆盖率、(5) `export` 后 `json.load` 是否一次成功。五项分别与本 Skill 输出对比即可复现增益；脚本无随机性，重复运行结果一致。

## 11. 运行脚本说明

本包安装于 `/skills/weekly-skill/`（脚本 `/skills/weekly-skill/src/nanopub.py`、schema `/skills/weekly-skill/schema/nanopub_schema.json`、模板 `/skills/weekly-skill/templates/nanopub.template`、清单 `/skills/weekly-skill/checks/checklist.md`、示例 `/skills/weekly-skill/examples/synthetic_assertions.json`）。运行时若 `/app/work` 与脚本不同目录，用绝对路径调用；三个子命令：

- `python3 src/nanopub.py validate --result draft.json [--schema schema/nanopub_schema.json] [--text paper.txt] [--out report.json]` → 校验断言粒度/证据绑定/溯源/可解析性，打印报告，exit 0/1/2。
- `python3 src/nanopub.py export --result draft.json --out result.json [--schema ...] [--text ...] [--report ...]` → 校验通过后写规范化 result.json（键排序、默认值、`quality` 合并），有 error 时拒绝导出并返回 1。
- `python3 src/nanopub.py decompose --text "<一个原句>" [--json]` → 输出并列/因果/复合主体/条件标记与拆分建议（**建议需回原文验证，非最终答案**）。
- `python3 src/nanopub.py --self-test` → 用内置合成 EXAMPLE 自检脚本可用性（示例数据，非正式案例）。
