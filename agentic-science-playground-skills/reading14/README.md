# Nanopublication 抽取 Skill（阅读14）— 使用说明

把一篇科研论文的结论转换成**可独立判断真假、可回到原文、可机器解析**的断言集合：
每条断言 = 单一主体 + 单一关系 + 单一对象 + 保留条件/限定，绑定**最小充分证据片段**与可指向的
原文位置，并记录 `断言 → 证据 → 论文 → 作者 → 年份 → 版本 → 标识符` 的完整溯源链，最终导出
`result.json`。核心是四个问题：**拆得细 / 对得上 / 追得回 / 读得懂**。

## 文件清单

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 运行期唯一操作手册：输入契约、分步流程、受控词表、异常矩阵、输出契约、自查清单、增益对照 |
| `schema/nanopub_schema.json` | 断言/证据绑定/溯源/result.json 的字段字典与枚举（也是 `nanopub.py` 的可选词表来源） |
| `src/nanopub.py` | 仅标准库的校验器 + 导出器 + 断言拆解建议工具（`validate` / `export` / `decompose` / `--self-test`） |
| `templates/nanopub.template` | 可复用断言/证据/溯源模板（JSON 骨架 + 字段速查表 + 合成示例） |
| `checks/checklist.md` | 把四个问题逐条映射到可勾选的核验项 |
| `examples/synthetic_assertions.json` | 12 条**合成**示例断言，覆盖并列/因果/条件/否定/图表/无证据/冲突等高频情形（全部虚构，非正式案例） |
| `README.md` | 本文件 |

## 依赖与运行环境

- Python 3（仅标准库：`json`、`argparse`、`re`、`sys`、`datetime`、`collections`），无需 pip、无网络。
- 所有文件 UTF-8 文本；脚本确定性（无随机数），重复运行产出相同报告。

## 调用方式

### 运行期（Agent 执行案例时的整体流程）

1. 读 `/input/case.json` 取 `case_id` 与 `output_contract` 字段名；读 `task.md`。
2. 定位论文材料并抽取正文到 `/app/work/paper.txt`（PDF 用 `pdf-text-tool`；扫描版先 `ocr-tool`）。
3. 按 `SKILL.md` 第 4 节：建立来源表 → 定位结论句 → 拆解断言 → 绑定证据 → 补溯源链，产出 `draft.json`。
4. 机械校验（引文回验 + 粒度 + 溯源）：
   ```bash
   python3 src/nanopub.py validate --result draft.json \
     --schema schema/nanopub_schema.json --text /app/work/paper.txt --out /app/work/validation_report.json
   # exit 0=干净, 1=有 error（修到 0）, 2=仅有 warning（判定后修复或注明保留）
   ```
5. 导出规范化结果：
   ```bash
   python3 src/nanopub.py export --result draft.json --out /app/output/result.json \
     --schema schema/nanopub_schema.json --text /app/work/paper.txt --report /app/work/validation_report.json
   ```
6. 确认 `result.json` 含 `case_id` + `output_contract` 全部字段 + `sources/assertions/quality/unreported/conflicts/uncertainty/change_log`。

### 独立自检（不依赖案例文件）

```bash
python3 src/nanopub.py --self-test
```
用内置合成 EXAMPLE 跑一遍 validate + decompose，验证脚本可用。**该数据是示例，不是任何正式案例的答案。**

### 拆解建议（辅助，不自动落库）

```bash
python3 src/nanopub.py decompose --text "TNF-alpha increased IL-6 and reduced IL-10 in macrophages, which led to a pro-inflammatory phenotype."
```
输出并列连词、因果链、复合主体/宾语、条件短语与拆分片段。**每个片段都必须回原文验证**后再写入断言。

## 方法说明

1. **断言粒度判据（拆得细）**：一条断言 = 一个主体 + 一个关系 + 一个对象 + 条件；复合主体/宾语/谓语的并列、因果链都拆成独立断言；条件/限定保留在 `conditions[]`。脚本用「多句 → error、超长 → warn、并列/因果标记 → warn、源句有条件但 `conditions[]` 为空 → warn」做机械校验。
2. **最小充分证据判据（对得上）**：`evidence_binding.quote` 是最短的一段原文，只要它仍承载"主体 + 关系语义 + 对象"；`location` 给页码/段落/句子/图/表/公式 + `pointer` + 字符偏移；`relation_to_assertion` 区分 `direct`（直接陈述）/`inferred`（读图/读数据，须写推理步骤）/`context`（只是背景，不得支撑）。脚本用 `--text` 回验 verbatim 引文是否真在正文里。
3. **受控关系词表映射（对得上）**：`relation` 为 snake_case 受控动词，`relation_type ∈ {causal, associative, comparative, definitional, quantitative, methodological}`，`direction ∈ {positive, negative, neutral, not_applicable}`；脚本校验"动词↔关系类""符号↔方向"是否一致，避免把"相关"写成"导致"。
4. **溯源链（追得回）**：`provenance.chain == [assertion_id, evidence_id, source_id]`；`sources[]` 每行必须有 `title + authors + year + version + identifiers`（DOI 优先）。脚本逐项核对并报 error。
5. **可解析导出（读得懂）**：`export` 输出键排序、2 空格缩进、`ensure_ascii=False`、补默认值、合并 `quality` 报告的 JSON，下游 `json.load` 即可。

## 适用范围与限制

- 输入为论文全文/段落文本；只处理**能回到原文定位**的结论，不声称断言完整性（未报告即 `unreported`）。
- 引文只来自实际抽取的文本/OCR；不据不可见图表或公式反推数值；行内公式/上下标被线性化时按线性化文本抄录，不"还原"。
- `decompose` 是启发式建议工具（正则标记扫描），覆盖常见并列/因果/条件，但不是句法解析器；最终拆分以回原文验证为准。
- 词表是受控推荐集：词表外动词允许保留但必须写 `decomposition.note`，脚本只 warning 不静默失败，以便泛化到未见论文。
- 版本链要求版本字段；多版本论文各建一行 source 并在 `note` 互指。

## 失败处理

| 情况 | 处置 | 状态 |
|---|---|---|
| 扫描版无文本层 | `ocr-tool`；无 OCR → `partial` + 逐断言 `not_extractable`，不猜内容 | `partial` |
| 加密 PDF | `sources[].status="unparseable"` + 原因；不猜 | `partial` |
| 原文无法访问 | 只对已获文本建断言，缺的章节写 `unreported`，`sources[].status="unreachable"` | `partial` |
| 证据在图里 | `quote_type="figure_description"` + `location.figure` + `inferred` + 推理步骤 | `success`（带推断标注） |
| 断言无支撑片段 | `status="unsupported"` + `sufficiency.judgment="insufficient"` + `unreported`，不编造引文 | `success` |
| 断言↔证据冲突 | `status="conflict"` + `conflicts[]` 并列保留，不删边 | `success` |
| 缺作者/年份/版本/标识符 | 显式 `unknown`（年份 `null`）+ `note`；脚本报 error 必须补齐或标注 | 修到 0 error |
| DOI 解析失败 | 保留原串 + `note`"未验证"，不臆造 DOI | `success`（warning） |
| 校验发现 error | 修复后重跑 `validate`/`export` 直到 exit 0 | 重试 |

## 自查方法

按 `checks/checklist.md` 逐项勾选；机械校验用：
```bash
python3 src/nanopub.py validate --result draft.json --schema schema/nanopub_schema.json --text /app/work/paper.txt
```
覆盖：多句/超长/并列/因果残留、条件是否被丢弃、verbatim 引文是否命中正文、引文是否提到主体/对象、
`relation`↔`relation_type`/`direction` 一致性、`provenance.chain` 是否等于 `[a,e,s]`、来源是否缺作者/年份/版本/标识符、
id 是否唯一。再人工抽查任意 3 条：引文能否在 `paper.txt` 中 `grep` 命中、拆解方向是否与原文一致。

## 最小示例（EXAMPLE，合成数据，非正式案例）

输入 `draft.json`（一条断言）：
```json
{
  "schema_version": "1.0.0",
  "case_id": "EXAMPLE",
  "status": "success",
  "sources": [
    {"source_id": "src-1", "kind": "paper", "title": "Example Paper (synthetic)",
     "authors": ["Doe, Jane"], "year": 2024, "version": "published",
     "identifiers": {"doi": "10.0000/EXAMPLE.000001"}}
  ],
  "assertions": [
    {
      "assertion_id": "a1",
      "text": "In HEK293T cells, kinase X increases phosphorylation of Y.",
      "source_text": "In HEK293T cells, kinase X increased the phosphorylation of Y (Fig. 2B).",
      "subject": {"label": "kinase X", "type": "protein"},
      "relation": "increases", "relation_type": "causal", "direction": "positive",
      "polarity": "affirmative",
      "object": {"label": "phosphorylation of Y", "type": "phenotype"},
      "conditions": [{"slot": "cell_line", "value": "HEK293T"}],
      "certainty": {"level": "reported", "basis": "verbatim sentence"},
      "decomposition": {"method": "condition_extraction"},
      "evidence_binding": {
        "evidence_id": "e1",
        "quote": "In HEK293T cells, kinase X increased the phosphorylation of Y (Fig. 2B).",
        "quote_type": "verbatim",
        "location": {"page": 3, "section": "Results", "paragraph": 2, "sentence": 1,
                     "pointer": "p.3, Results, para 2, sent 1"},
        "relation_to_assertion": "direct",
        "sufficiency": {"judgment": "sufficient", "reason": "verbatim causal statement"}
      },
      "provenance": {"source_id": "src-1", "evidence_id": "e1",
                     "assertion_id": "a1", "chain": ["a1", "e1", "src-1"]},
      "status": "supported"
    }
  ]
}
```

执行与示意输出（**示意，非正式案例结果**）：
```bash
python3 src/nanopub.py validate --result draft.json --schema schema/nanopub_schema.json --text paper.txt
# {"ok": true, "errors": [], "warnings": [], "counts": {"assertions": 1, "supported": 1, ...}}

python3 src/nanopub.py export --result draft.json --out result.json --schema schema/nanopub_schema.json --text paper.txt
# {"exported": true, "errors": 0, "warnings": 0, ...}
```
`result.json` 含 `quality.checks`（每条检查带 `question ∈ {split_fine, bind_evidence, trace_provenance, machine_readable}` 与 `pass/warn/fail`），下游可直接 `json.load`。

## 与正式案例的边界

本包不含任何正式案例答案、白板或预生成结果；`examples/synthetic_assertions.json` 与 `--self-test` 数据全部是
标记为 synthetic 的虚构内容。正式案例由平台运行时提供，Skill 只定义"如何拆、如何绑、如何回、如何导出"的通用流程。
