# literature-translator

可被 Agent 调用的科研文献翻译 Skill：把论文翻译成**可复核**的双语对照结果。
它不替代翻译模型，而是给翻译过程加上四层“账本”——锁定术语表、段号 1:1 对齐、
受保护的数字/单位/公式/引用、逐段依据与不确定标注——让结果能被第三方逐条核验。

## 文件结构

```
SKILL.md                        运行期唯一指导（前端/流程/规则/异常矩阵）
README.md                       本文件
src/translate.py                Python3 标准库脚本（分段/术语/保护/对齐/QA）
templates/term_glossary.md      术语表格式模板（6 列表格）
schema/translation_schema.json  术语条目/对齐段/result.json 的 JSON Schema
checks/checklist.md             四问题 → 具体检查项的核对清单
```

## 快速使用（Agent 运行期）

运行期环境：输入 `/input/case.json` 与 `/input/task.md`，工作目录 `/app/work`，
输出 `/app/output`。脚本在 `<SKILL_DIR>/src/translate.py`。

```bash
# 0. 读输入
cat /input/case.json /input/task.md

# 1. PDF -> 文本层（脚本自动尝试 PyMuPDF/pypdf/pdfminer/pdftotext）
python3 <SKILL_DIR>/src/translate.py extract --pdf /input/paper.pdf --out /app/work/source.txt

# 2. 源文分段（生成 P0001.. 主键）
python3 <SKILL_DIR>/src/translate.py segment --source /app/work/source.txt \
  --out /app/work/source_paragraphs.json --text-out /app/work/source_paragraphs.txt

# 3. 术语候选（人工审校后把 status 改 locked）
python3 <SKILL_DIR>/src/translate.py candidates --source /app/work/source.txt \
  --out /app/work/glossary.md --domain "materials science"

# 4. 保护数字/单位/引用/公式（并生成占位符掩码文本）
python3 <SKILL_DIR>/src/translate.py protect --source /app/work/source.txt \
  --out /app/work/protected.json --mask-out /app/work/masked.txt

# 5. 逐段翻译（见 SKILL.md 4.5 的提示模板）得到 /app/work/target_masked.txt，
#    每段带 [P####] 标记；然后恢复占位符：
python3 <SKILL_DIR>/src/translate.py restore --masked /app/work/target_masked.txt \
  --tokens /app/work/protected.json --out /app/work/target.txt

# 6. 对齐 + 双语稿
python3 <SKILL_DIR>/src/translate.py align --source /app/work/source_paragraphs.json \
  --target /app/work/target.txt --out /app/work/align.json --md-out /app/output/bilingual.md

# 7. QA（退出码 0=通过；2=有问题，按 issues 修复后重跑）
python3 <SKILL_DIR>/src/translate.py qa --source /app/work/source_paragraphs.json \
  --target /app/work/target.txt --glossary /app/work/glossary.md --out /app/work/qa.json

# 8. 组装 /app/output/result.json（schema/translation_schema.json）
```

## 方法说明

- **术语稳**：翻译前建术语表（6 列：term/translation/variants/context/
  first_location/status）。`locked` 即全文唯一译名；`qa` 逐段检查“源文出现该术语
  → 目标段必须出现规范译名（数量不少于出现次数）”，并检查术语是否被漏译。
- **段落全**：分段器以空行 + 标题/图注/公式为边界，页/列换行不作段边界；
  目标译文必须带 `[P####]` 标记；`qa` 比对缺失/多余/错序/重复段号。
- **关系准**：`protect` 把数字、单位、`[1,3]`/作者-年份引用、Fig./Table/Eq./
  Section 编号、行内公式抽成 `⟨ID⟩` 占位符，译后 `restore` 原样回填；`qa` 再查
  `token_missing`（逐字保留）与 `number_drift`（数字多重集一致），并给出
  否定/限定可能丢失的提示。图/表编号允许“Fig. 1”→“图 1”式局部化，编号必须保留。
- **可核验**：双语稿每段并列源文/译文/依据/不确定；不确定片段用
  `⟦译文或原文⟧【原因】` 标注，进 `result.uncertainties`，绝不静默掩盖。

## 适用范围与限制

- 面向英文（及常见西文）学术文献；中文目标语为默认，其他目标语需自建对应
  否定/限定词表（`src/translate.py` 顶部常量）。
- 分段是启发式的：复杂双栏、行内图文混排、无空行的扫描件需要人工抽查段边界；
  公式/表格为图片时脚本无法自动识别，须按异常矩阵 A-3 人工处理。
- 术语抽取是候选挖掘（缩略语、化学式、高频 n-gram、大写短语），不是最终术语表；
  必须人工审校后再 `locked`。
- 数字/单位/引用的正则覆盖常见形态，冷门单位或自造记号可能漏保护——`protect`
  输出的掩码文本必须肉眼过一遍。
- 不保证译文文采；只保证四项目标（术语/段落/关系/可核验）可测、可修、可复核。

## 失败处理

- 脚本退出码：0=OK；1=用法/IO/解析错误；2=QA 发现问题（报告已写出）；3=必需
  输入缺失（需人工/Agent 干预）。
- 无文本层 / 扫描件 / 加密 PDF / 原文残缺等：按 `SKILL.md` 第 8 节异常矩阵处置，
  并在 `result.status` 与 `change_log` 中如实记录。
- 任何 QA error 无法消除时，只能通过显式 `uncertain` 标注收口，不能删除检查项。

## 自查方法

见 `checks/checklist.md`。提交前必做 G 组：`result.json` 合法且含 `case_id` 与
`output_contract` 全部字段；`bilingual.md` 每段有源文/译文/依据；`uncertain`
无遗漏；同输入重复运行结构一致（幂等）。

## 最小示例（EXAMPLE）

以下为**示意**，输入与输出均为示例，不是任何正式案例结果。

输入 `source.txt`（片段）：
```
Abstract

Monolayer molybdenum disulfide (MoS2) is a two-dimensional semiconductor.
The band gap of MoS2 is approximately 1.8 eV.
```

运行：
```bash
python3 src/translate.py segment --source source.txt --out source.json
python3 src/translate.py protect --source source.txt --out protected.json --mask-out masked.txt
```

`masked.txt` 示意：
```
Abstract

Monolayer molybdenum disulfide (MoS2) is a two-dimensional semiconductor.
The band gap of MoS2 is approximately ⟨NUMBER_0001⟩⟨UNIT_0002⟩.
```

术语表（`templates/term_glossary.md` 格式，节选）：
```
| term | translation | variants | context | first_location | status |
|---|---|---|---|---|---|
| monolayer | 单层 | single layer | Monolayer molybdenum disulfide | P0002 | locked |
| band gap | 带隙 | bandgap | the band gap of MoS2 | P0002 | locked |
| MoS2 | MoS2 | | kept untranslated | P0002 | locked |
```

译文（带段号，节选，示意）：
```
[P0002] 单层二硫化钼（MoS2）是一种二维半导体。MoS2 的带隙约为 ⟨NUMBER_0001⟩⟨UNIT_0002⟩。
```

`restore` 后：
```
[P0002] 单层二硫化钼（MoS2）是一种二维半导体。MoS2 的带隙约为 1.8 eV。
```

`qa` 示意输出（error=0 时通过）：
```
paragraphs: source=2 target=2
errors=0 warnings=0
missing_target=[] extra_target=[] order_issues=0
```

以上为接口与流程示意；`result.json` 的完整字段见 `schema/translation_schema.json`。
