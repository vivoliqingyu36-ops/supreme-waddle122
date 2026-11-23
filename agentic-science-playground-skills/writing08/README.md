# intro-related-work-writer — 引言与相关工作写作 Skill

把一份科研事实底稿（论文草稿、方法/图表/实验说明、参考文献库）加工成可进入论文的「研究背景 / 相关工作 / 研究空白 / 贡献」四部分，并把每条事实、转述、空白和贡献绑定到来源证据或显式标注为作者判断。核心判据是题面四问：**立得住、分得清、说得实、对得上**。

## 1. 调用方式

- 安装：把本目录（含 `SKILL.md` 与四个资源）装入 `/skills/weekly-skill`；平台运行时输入为 `/input/case.json` 与 `/input/task.md`。
- 触发：任务文本含「写引言 / 引言写作 / introduction / 相关工作 / related work / 研究背景 / 研究空白 / research gap / 贡献 / contributions / 补引用 / 核对引用 / 核对贡献 / citation check」等词，且任务目标是生成或核验引言与相关工作，即按 `SKILL.md` §2 进入流程。
- 执行：按 `SKILL.md` §4 步骤 0→11 顺序执行；工作目录 `/app/work`，最终产物放 `/app/output`，其中 `result.json` 必须含 `case_id` 与题面 `output_contract` 的全部字段。
- 依赖：`scripts/claim_map_check.py` 仅用 Python 3 标准库（`json`、`sys`、`argparse`、`re`），无需第三方安装。

## 2. 方法说明

四个问题的判据被翻译成可执行的抽取、分组、推导、对齐规则：

1. **立得住**：背景必须点名 ≥2 个具体工作/技术里程碑（带引用），并落在一个具体未解决问题上，给出至少一个技术约束/数据限制/评价缺口作为「为什么现在值得做」。禁止「近年来受到广泛关注」式空转。
2. **分得清**：给每篇候选文献建一张只来自其原文的事实卡（问题设定 / 方法路线 / 数据与评价 / 结论 / 适用条件 / 局限），再按主维度分组建比较矩阵；组内写「同维度差异句」，不写逐篇摘要。来源没写的局限写「未报告」。
3. **说得实**：每个空白先归类为 `shared_limitation`（≥2 篇共同限制）/ `uncovered_scenario`（具体场景未被覆盖）/ `conflicting_conclusion`（≥2 篇冲突）/ `no_basis`（无依据，须标作者判断）四类之一，并给出依据文献与原文定位；空白段必须写「本文如何填补」，填补方式来自本文事实。
4. **对得上**：每条贡献绑定本文证据（方法/图/表/实验/公式）；每个 claim 绑定来源（引用键 / 文件定位 / 作者判断）；引用键与参考库做集合核对；DOI 查不到只标未核实，不编造。

通用化设计：本流程不依赖具体学科或论文；分组维度、claim 类型、gap 类型是可复用的判据，任何学科（计算、实验、理论）都能用同一套事实卡和矩阵操作。

## 3. 适用范围与限制

- 适用：有事实底稿 + 参考文献库的引言/相关工作写作、改写、补引用、贡献核验；中文/英文均可。
- 限制：
  - **不生产事实**：所有数字、结论、引用必须来自输入材料；材料没有的一律写「未报告/作者判断」，不编造。
  - **不做纯格式转换**：只把 bib 格式 A 转成 B 且不核验内容的任务，直接用格式工具，不套本流程。
  - **依赖材料质量**：文献库为空或 PDF 无文字层时，只能产出 partial 结果（见 §5）。
  - 无法联网时 DOI 校验降级为「未核实」，不影响成稿但会记入 uncertainty。
- 边界：本 Skill 不运行实验、不生成数据、不替代作者对「空白是否值得做」的最终判断（no_basis 空白一律交人工）。

## 4. 失败处理

按 `SKILL.md` §8 异常矩阵执行，要点：

- 文献库为空 → 不虚构引用，相关工作总结为「材料未提供」，空白标 no_basis，status=partial。
- 引用查不到原文 → 删引用、claim 降级为作者判断/未核实，记 change_record。
- 空白缺乏依据 → 写 no_basis 并显式标注，绝不伪造引用背书。
- 来源冲突 → 双保留、标 conflict、记 uncertainty，不静默取其一。
- 超时/预算用尽 → 立即落盘 partial result.json，needs_human 写清未完成部分。
- 校验脚本退出码 2（硬错误）→ 修复后再交付；退出码 1（警告）→ 在 uncertainty/needs_human 说明。

## 5. 自查方法

1. 跑 `python3 scripts/claim_map_check.py --source-map /app/output/source_map.json`（参考库单独存为文件时追加 `--references <refs.json>`；缺省用 source_map.json 内的 `references` 数组），退出码必须非 2。
2. 按 `checks/checklist.md` 逐项核对四问（pass/fail/na），把结果写进 result.json 的 `verification`。
3. 复核三条「一票否决」：四部分是否齐全且承接；每个含事实/判断的 claim 是否都有来源；每条贡献是否都有本文证据定位。

## 6. 最小调用示例（EXAMPLE）

> 以下为**示意**，不是任何正式案例的答案；输入输出均人工构造以说明接口。

**输入 `/input/case.json`（节选，示意）**

```json
{
  "case_id": "demo-0001",
  "output_contract": { "draft": "string", "source_map": "string", "verification": "string" },
  "materials": {
    "paper_facts": "/input/paper_facts.md",
    "references": "/input/refs.json"
  },
  "constraints": { "venue": "ML conference", "citation_style": "numeric", "language": "en", "max_words": 600 }
}
```

**`/input/paper_facts.md`（节选，示意）**

```markdown
## 本文事实
- 问题：现有 A 类方法在低样本时梯度不稳定（证据 P1）。
- 方法：提出带稳定项的 B 方法（§3，公式 (2)）。
- 实验：在 C 基准上比 A 类方法高 2.1 分（表 1，图 2）。
## 参考文献要点
- w1 (A类奠基)：监督式路线，结论是标准监督下有效，局限是依赖大量标注。
- w2 (A类改进)：自监督路线，结论是小样本可训练，局限是仅验证到 3 个任务。
```

**执行（Agent 按 SKILL.md 步骤 0–11 操作后）**

```text
/app/output/draft.md            # 四部分正文
/app/output/source_map.md       # claim→来源、比较矩阵、gap 链、贡献→证据
/app/output/comparison_matrix.md
/app/output/source_map.json
/app/output/result.json
```

**示意 `result.json`（节选）**

```json
{
  "case_id": "demo-0001",
  "status": "success",
  "output_contract": { "draft": "/app/output/draft.md", "source_map": "/app/output/source_map.md", "verification": "/app/output/checklist_result.md" },
  "claims": [
    { "claim_id": "c01", "claim_text": "低样本下 A 类方法梯度不稳定", "claim_type": "background_problem",
      "source": { "citation_key": "w1" }, "status": "cited", "quote_or_paraphrase": "w1 报告在训练样本 <100 时梯度方差增大", "needs_human": false }
  ],
  "contributions": [
    { "contribution_id": "g1", "contribution_text": "提出带稳定项的 B 方法", "evidence": ["§3", "公式(2)"], "evidence_status": "verified", "overclaim_risk": "none" }
  ],
  "gaps": [
    { "gap_id": "g1", "gap_type": "shared_limitation", "basis_works": ["w1", "w2"], "basis_loc": "refs.json#w1.limitation; refs.json#w2.limitation",
      "this_paper_fill": "B 方法的稳定项（§3）" }
  ],
  "verification": { "four_questions": { "stand_firm": "pass", "group_clearly": "pass", "gap_grounded": "pass", "aligned": "pass" }, "script_exit_code": 0 },
  "needs_human": [], "uncertainty": [], "material_gaps": []
}
```

> 以上标注 EXAMPLE 的均为示意数据，不冒充正式案例结果。

## 7. 文件清单

| 文件 | 用途 |
|---|---|
| `SKILL.md` | Skill 本体：用途、适用/不适用、输入输出契约、步骤 0–11、四问规则、异常矩阵、自查、增益说明 |
| `README.md` | 本文件 |
| `templates/intro_structure.md` | 逐节写作模板 + 比较矩阵表 + claim→证据表 |
| `checks/checklist.md` | 四问逐项核对清单 |
| `schema/writing_schema.json` | claim→来源、贡献→证据、gap、比较矩阵、result.json 的 JSON Schema |
| `scripts/claim_map_check.py` | 标准库校验脚本 |
