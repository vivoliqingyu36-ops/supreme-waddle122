# 核验清单：四问逐项勾选（checks/checklist.md）

在写 `result.json` 之前逐项勾选；任何一项未通过都先修复再交付。括号内标注可机械校验（M）或需人工核对（H）。

## 问 1 — 抽得准（实体是论文里真实出现的对象，不是模型补全的概念）

- [ ] （H）每个实体在对应段落引文 `quote` 中逐字出现；抽查 3 个节点，`grep` 引文能在材料文件中命中。
- [ ] （M）`python3 src/kg.py validate` 无"missing/empty 'quote'"类 error；所有实体含 `source_id + paragraph_id + quote`。
- [ ] （H）没有凭空补的实体：原文未提的指标/材料/结论不建节点（例：原文没写 sensitivity 就不建 sensitivity 节点）。
- [ ] （H）数值只引正文明确给出者；正文未给数值的节点 `note` 标注"数值未报告"，不填 0/均值/猜测。
- [ ] （H）作者自述与他人转述已区分：转述实体 `strength=paraphrase` 且 `note` 标明转述来源，不冒充原研究者自述。

## 问 2 — 连得对（关系类型、方向、适用条件与原文一致；无共现/转述/推测当直接证据）

- [ ] （M）`validate` 无 `strength 'cooccurrence'/'speculation'/'inferred' is forbidden on a formal edge` 类 error：弱证据全部在 `non_edges`，不在边表。
- [ ] （H）每条边的 `type + direction + conditions + quote` 与原文语义一致；`quote` 能读出该关系。
- [ ] （H）`OUTPERFORMS/COMPARES` 写清比较对象、指标与条件；原文只说共现/都使用时不建优劣边。
- [ ] （H）`paraphrase` 边已注明是转述，方向依据转述者表述，未当作对被转述者的直接断言。
- [ ] （H）无把"同篇多文件格式"当跨篇证据；跨篇边两侧各有各的 `source_id + paragraph_id + quote`。

## 问 3 — 对得齐（别名/缩写/大小写/同名冲突处理正确：不重复节点、不错误合并）

- [ ] （M）`validate` 无 `duplicate node id` error；节点 id 全局唯一。
- [ ] （M）`validate` 无"share canonical name ... have no SAME_AS/DISTINCT_FROM edge" warning：同名节点都已有对齐记录。
- [ ] （H）每个 `merge` 决策：`alignments` 里有"字符串别名可对应 + 同一指称（同一物理样品/模型实例/数据集/条件/人）"双重依据与两侧证据。
- [ ] （H）每个 `keep_separate` 决策：`alignments` 里有 `conflict_note` 说明为何相似但非同一对象（例：粒径/条件不同、不同数据集）。
- [ ] （H）只字符串相似、无同物证据的**未合并**（不强迫合并）；缩写无法确证展开时保留原缩写节点并注明。
- [ ] （H）相同通用术语（AuNPs / logistic regression 等）在两篇各自有节点时，只有原文指向同一实例才合并；否则保留两个节点 + `DISTINCT_FROM`。

## 问 4 — 查得到、回得去（图能回答真实查询；每个节点/边回到论文具体位置 + 原文片段）

- [ ] （H）已实际执行 ≥3 个查询（不止是列出查询意图），每个有 `result_nodes/result_edges/evidence`。
- [ ] （M）`python3 src/kg.py query ...` 的输出中，`answered` 查询数 ≥3，或空查询有 `empty_reason`。
- [ ] （H）每个查询的 `evidence` 条目含 `source_id + paragraph_id + quote`，能定位回原文。
- [ ] （H）位置是 JATS 段落 ID（`paragraph_id`），**无 PDF 页码、无自造"第 1 页"**；材料缺段落 ID 时写 `"unlocated"` 并说明。
- [ ] （H）查询无结果时 `status:"empty"` + 说明为何空，不编造结果。
- [ ] （H）未报告值、源内冲突已显式列在 `unreported`/`conflicts`，未抹平。

## 交付收口（每次交付前）

- [ ] （H）`result.json` 含 `case_id`（抄自 `/input/case.json`）与 `output_contract` 要求的全部字段。
- [ ] （H）`status` 与实际情况一致（`success`/`partial`/`failed`）；`change_log` 记录了关键步骤。
- [ ] （M）`kg_schema.json` 是合法 JSON；`kg.py --self-test` 通过（exit 0）。
- [ ] （H）无编造 DOI/页码/数值/分数；不确定项在 `uncertainty` 中显式标注。
