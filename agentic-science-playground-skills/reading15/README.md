# 文献知识图谱构建 Skill（阅读15）— 使用说明

把一个包含两篇独立论文的案例输入（`corpus-manifest.json` + `material.json` +
`primary-material.json` + `secondary-material.json`，JATS 段落文本）构建成一张**带原文证据、可查询、
可复核**的知识图谱，交付 `result.json`。核心是四个问题：**抽得准 / 连得对 / 对得齐 / 查得到、回得去**。

## 文件清单

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 运行期唯一操作手册：输入契约、分步流程、领域规则、异常矩阵、输出契约、自查清单 |
| `schema/kg_schema.json` | 节点/边/对齐/查询/结果的 JSON Schema（含受控词表枚举），也是 `kg.py` 的校验词表来源 |
| `src/kg.py` | 仅标准库的校验器 + 查询引擎（`validate` / `query` / `--self-test`） |
| `templates/queries.template.json` | 6 种查询的模板（neighborhood/trace/path/node_by_name/node_by_type/edges_by_type） |
| `checks/checklist.md` | 把四个问题逐条映射到可勾选的核验项 |
| `README.md` | 本文件 |

## 依赖与运行环境

- Python 3（仅标准库：`json`、`argparse`、`collections`、`re`、`sys`），无需 pip 安装。
- 所有文件 UTF-8 文本；`kg.py` 不依赖网络、不依赖第三方包。

## 调用方式

### 运行期（Agent 执行案例时的整体流程）

1. 读 `/input/case.json` 取 `case_id` 与 `output_contract` 字段名。
2. 在工作目录定位并读取 `corpus-manifest.json`、`material.json`、`primary-material.json`、
   `secondary-material.json`（可选 `secondary-publisher.xml`）。
3. 按 `SKILL.md` 第 5 节逐步抽取实体、关系、做对齐，产出 `graph.json`（结构与 `kg_schema.json` 一致）。
4. 校验：
   ```bash
   python3 src/kg.py validate --graph graph.json --schema schema/kg_schema.json
   # exit 0=干净, 1=有 error, 2=仅有 warning；报告 JSON 打印到 stdout，可用 --out 落盘
   ```
5. 写查询文件 `queries.json`（≥3 个查询），执行：
   ```bash
   python3 src/kg.py query --graph graph.json --queries queries.json --out query_results.json --schema schema/kg_schema.json
   ```
6. 把 `graph.json` 的节点/边、`query_results.json` 的查询结果、`alignments`/`non_edges`/`conflicts`/
   `unreported` 汇总写入 `/app/output/result.json`（必含 `case_id` 与 output_contract 全部字段）。

### 独立自检（不依赖案例文件）

```bash
python3 src/kg.py --self-test
```
用内置的合成 EXAMPLE 图（3 节点 + 2 边）跑一遍 validate + query，验证脚本可用。**该数据是示例，
不是任何正式案例的答案。**

## 方法说明

1. **证据绑定抽取**：每个实体 = 原文真实出现的对象，绑定 `source_id + paragraph_id + quote`
   （quote 为逐字、线性化引文）。位置是 JATS 段落 ID，不是 PDF 页码。
2. **证据强度分级**：`direct`（原文直接陈述）> `paraphrase`（作者转述他人/综述转述，弱证据）
   > `inferred`（上下文推断）。`cooccurrence`（仅共现）与 `speculation`（推测）**不得进入边表**，
   一律写 `non_edges`，防止把共现/转述/推测当成直接证据。
3. **两步同一指称测试**（跨篇对齐）：合并须同时满足 (a) 别名/缩写/大小写/连字符归一后可对应，
   (b) 原文指向同一物理样品/模型实例/数据集/实验条件/同一人。只满足 (a) 不满足 (b) → 不合并，
   显式记 `DISTINCT_FROM` + 冲突说明。**相同通用术语（如 "AuNPs"/"logistic regression"）不等于同一实例**。
4. **关系有方向有条件**：每条边含 `type`、`source→target` 方向、`conditions`（适用条件）、`strength`、
   以及三件套证据；`OUTPERFORMS` 必须写清比较对象、指标与条件。
5. **查询回证据**：`kg.py` 对每个查询输出结果子图（节点对象 + 边对象）与每条元素的证据。

## 适用范围与限制

- 输入是 JATS 段落文本 + 段落索引 + 来源清单；两篇独立论文共享一张图但各自保留 `source_id`。
- 不提供 PDF 页码：**任何位置字段只允许 JATS 段落 ID**；材料缺段落 ID 时写 `"unlocated"`，不自行发明。
- 不提供图像像素、补充附件、底层临床/实验数据：不据图/公式/附件反推数值，只引正文明确陈述。
- 行内公式/上下标已线性化：引文按线性化文本逐字抄录，不"还原"上下标。
- 只处理正文文本中可定位的实体/关系；不声称实体完整性（未报告即保留 `unreported`）。
- 通用到未见过的论文对：所有规则以"是否可回到原文定位"为准，不依赖任何具体主题词表。

## 失败处理

| 情况 | 处置 | 状态 |
|---|---|---|
| 某篇论文文件缺失 | 只对存在的一篇建图，`sources` 中标 `missing`；不编造另一篇 | `partial` |
| 文本乱码/无文本层 | `file` 判型 → UTF-8 → latin-1 兜底；仍失败写 reason，不猜内容 | `failed` |
| 校验发现 error | 修复后重跑 `validate` 直到 exit 0，再执行查询 | 重试 |
| 查询无结果 | 输出 `status:"empty"` + `empty_reason`，不算失败 | `success`（查询空） |
| 同名不同物 | 两个节点 + `DISTINCT_FROM` 边 + `conflict_note` | `success` |
| 关系证据冲突 | 两边都保留，写 `conflicts`，不擅自删除 | `success` |

## 自查方法

按 `checks/checklist.md` 逐项勾选，并用以下命令做机械校验：

```bash
python3 src/kg.py validate --graph graph.json --schema schema/kg_schema.json
```
机械校验覆盖：重复节点 id、重复边 id、缺失三件套证据、悬空端点、受控词表越界、
`cooccurrence/speculation/inferred` 混入边表、同名节点未对齐、SAME_AS/DISTINCT_FROM 缺对齐记录。
再人工抽查：任意 3 条节点/边的 `quote` 能否在对应材料文件里 `grep` 命中。

## 最小示例（EXAMPLE，非正式案例）

输入 `graph.json`：

```json
{
  "case_id": "EXAMPLE",
  "status": "success",
  "sources": [{"source_id":"primary","title":"Example A","doi":"10.0000/EXAMPLE.A","authors":["A. Author"],"source_hash":"0xdeadbeef","license":"CC-BY"}],
  "nodes": [
    {"id":"primary.method.001","type":"method","canonical_name":"citrate reduction","source_id":"primary","paragraph_id":"p-sec2-para1","quote":"AuNPs were synthesized by citrate reduction.","strength":"direct"},
    {"id":"primary.material.001","type":"material","canonical_name":"gold nanoparticles (AuNPs)","source_id":"primary","paragraph_id":"p-sec2-para1","quote":"gold nanoparticles (AuNPs) of ~13 nm diameter","aliases":["AuNPs"],"strength":"direct"},
    {"id":"primary.conclusion.001","type":"conclusion","canonical_name":"citrate reduction yields ~13 nm AuNPs","source_id":"primary","paragraph_id":"p-sec4-para2","quote":"citrate reduction yielded AuNPs of about 13 nm.","strength":"direct"}
  ],
  "edges": [
    {"id":"E001","type":"USES","source":"primary.method.001","target":"primary.material.001","direction":"out","source_id":"primary","paragraph_id":"p-sec2-para1","quote":"AuNPs were synthesized by citrate reduction.","strength":"direct","conditions":"not stated"},
    {"id":"E002","type":"SUPPORTS","source":"primary.material.001","target":"primary.conclusion.001","direction":"out","source_id":"primary","paragraph_id":"p-sec4-para2","quote":"citrate reduction yielded AuNPs of about 13 nm.","strength":"direct","conditions":"not stated"}
  ]
}
```

查询 `queries.json`：

```json
{"queries":[
  {"id":"Q1","question":"citrate reduction 用了哪些材料？","type":"neighborhood","params":{"node":"primary.method.001","max_depth":1}},
  {"id":"Q2","question":"E001 的证据是什么？","type":"trace","params":{"element":"E001"}}
]}
```

执行与示意输出（**示意，非正式案例结果**）：

```bash
python3 src/kg.py validate --graph graph.json --schema schema/kg_schema.json
# {"errors": [], "warnings": [], "counts": {"nodes": 3, "edges": 2, ...}}

python3 src/kg.py query --graph graph.json --queries queries.json --out query_results.json
# {"executed": 2, "answered": 2, "empty": 0}
```
`query_results.json` 中每个查询含 `result_nodes`、`result_edges`、`evidence`（每条证据含
`source_id`/`paragraph_id`/`quote`/`strength`）。
