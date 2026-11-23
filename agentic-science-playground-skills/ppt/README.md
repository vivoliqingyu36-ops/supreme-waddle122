# 论文转学术 PPT — Skill 包

把一篇科研论文**结构性地改写**成可讲、可核验、可编辑的学术 PPT：页级大纲 + 每页证据映射 +
讲解备注 + 模板合规排版 + 真实渲染预览 + 版本记录。核心主张是「不是把段落切成行，而是一次结构重写」。

本包是「运行期 Agent 的指导书 + 一组真实可用的后处理资源」。平台运行时把它安装到
`/skills/weekly-skill`，再由 DeepSeek Harness 在 3 个固定科研案例上执行。本包**不含任何
预置答案或正式测试输出**，只给可泛化流程与工具。

## 目录结构

```
ppt/
├── SKILL.md                    # 运行期主指令（YAML frontmatter + 分步流程 + 领域规则 + 异常矩阵 + 自查 + 增益）
├── README.md                   # 本文件
├── src/ppt_outline.py          # 纯标准库 Python：页级大纲构建 + 证据映射 + 契约校验（可运行，非占位）
├── schema/ppt_schema.json      # paper_skeleton / slide_outline / result.json 三份结构契约
├── templates/slide_outline.md  # 可复用页级大纲 + 证据映射表模板
└── checks/checklist.md         # 六方向 → 具体检查的核对清单
```

## 方法说明

六步链路，每步都有机器可查的闸门：

1. **主线提取**：从论文抽「问题 → 缺口 → 方法 → 关键证据 → 结论 → 限制」，每条带 `locator`；
   主结论与支撑性细节分离，形成页序可讲的 `narrative_arc`。
2. **证据索引**：每张图/表/公式/数据建 `EvidenceItem`，标注 `kind`（figure/table/formula/data）、
   `role`（data/schematic/illustration）、`owner`（paper/cited/other）、`label`（逐字编号）、
   `locator`、`data_points`（逐字数字/单位/条件）。
3. **页级大纲**（`src/ppt_outline.py build`）：按 canonical 顺序分页，一页一主张，绑定证据并复制
   locator/label，自动生成 `data_verbatim` 与 `evidence_map`。
4. **契约校验**（`validate`）：一页一主张、引用有 locator、页数 ≤ 上限、数字/单位逐字、
   示意图不冒充数据、他人结果不归属本文、备注不逐字重复、证据覆盖完整、页序正确。
5. **模板排版**：读 master/layout 产 `template_spec.json`，按占位符填内容，处理长标题/多图/大表。
6. **导出渲染**：交 `.pptx` 源 + PDF/PNG 预览 + 版本记录，跨机可复现。

`src/ppt_outline.py` 是**确定性后处理器 + 契约门**，不解析 PDF 二进制、不渲染 PPTX；解析用平台的
`pdf-text-tool`/`pdf-render-tool`/`ocr-tool`，写 deck 用 `scientific-python`（python-pptx），
渲染用 `office-renderer`（或 LibreOffice headless）。

## 调用方式（运行期 Agent 视角）

```bash
# 1) 校验器自检（确认环境与脚本可用）
python3 /skills/weekly-skill/src/ppt_outline.py self-test

# 2) 生成一份合成演示输入，看接口长什么样（EXAMPLE，非正式案例）
python3 /skills/weekly-skill/src/ppt_outline.py demo --out /app/work/demo_skeleton.json

# 3) 从 paper_skeleton.json 生成页级大纲 + 证据映射并校验契约
python3 /skills/weekly-skill/src/ppt_outline.py build /app/work/paper_skeleton.json \
  --out /app/work/slide_outline.json --limit 12 --template /app/work/template_spec.json

# 4) 对已有大纲重新校验（exit 0=契约成立，3=违约，2=用法错，4=缺文件）
python3 /skills/weekly-skill/src/ppt_outline.py validate /app/work/slide_outline.json --limit 12
```

完整运行流程见 `SKILL.md` 第 0–9 步；输入/输出字段见 `schema/ppt_schema.json`。

## 适用范围与限制

**适用**：有文本层或可 OCR 的科研论文/预印本/技术报告（PDF/Markdown/HTML）+ 一个可编辑 PPTX 模板
或起始 deck；需要页级主张、证据映射、讲解备注、导出预览。

**限制（诚实声明）**
- 本 Skill **不重绘科研图**：只按 bbox 裁剪论文原图并保留 `Figure N` 标号；图形美化/重绘不在范围。
- 本 Skill **不生成论文未给出的新结论**；主线、数字、单位、结论一律来自原文。
- 无模板时退化为纯结构大纲（slide_outline.json + notes.md + Markdown 预览），无法满足「按占位符排版」
  的评分点，会如实标 `status=partial` + `not_reported`。
- 表格/多图/长标题的版面适配是启发式（节选/换行/降字号），极端排版需人工复核渲染 PNG。
- 公式为图片（E3）时只能做「字符/符号核对」，不保证完整 LaTeX 还原。
- `role`（data vs schematic）与 `owner`（paper vs cited）依赖 Agent 正确判断；拿不准必须标
  `ambiguous`/`heuristic_guess` 而非默认成 data/paper。

## 失败处理

- 加密 PDF、无文本层、字体缺失、模板缺失、占位符不足、页数超限等见 `SKILL.md` 异常矩阵 E1–E12。
- 部分页失败 → `status=partial`，`limits[]` 写页码与原因；整体失败 → `status=failed`。
- 任何工具失败 → 降级路径（text→render+OCR→仅结构大纲）；每步看 `[exit code: N]` 并排查。
- 重复运行应幂等；有差异写 `change_log`。

## 自查方法

1. `python3 src/ppt_outline.py self-test`（校验器 9 项通过）。
2. `python3 src/ppt_outline.py validate slide_outline.json --limit N`（契约 0 错误）。
3. 逐项执行 `checks/checklist.md`（六方向 30+ 条），不通过写 `result.json.uncertainty[]`。
4. 渲染 PDF/PNG 逐页目测（标题/表格页重点），用 pdf-text-tool 抽 PDF 文本核对数字/单位/bullet。
5. 用 `schema/ppt_schema.json` 校验 `result.json` 必填字段（可用 jsonschema 工具；无则人工对 required）。

## 最小示例（EXAMPLE）

以下输入/输出均为**合成演示**，不冒充正式案例结果。完整合成输入用
`python3 src/ppt_outline.py demo` 生成。

EXAMPLE — 输入 `paper_skeleton.json`（截取）：

```json
{
  "paper_id": "demo-paper-0001",
  "meta": {"title": "Synthetic demonstration of the paper-to-academic-PPT contract",
           "authors": ["A. Example"], "source_file": "demo_paper.pdf"},
  "mainline": {
    "problem": {"claim": "Current method X fails for rare, low-sample-size conditions.",
                "locator": {"page": 1, "section": "Abstract"}},
    "gap": {"claim": "No existing approach separates the confounding factor C.",
            "locator": {"page": 2, "section": "Introduction"}},
    "method": {"claim": "We propose a two-stage estimator that controls C via stratified re-weighting.",
               "refs": ["formula:1", "fig:1"], "locator": {"page": 3, "section": "Methods"}},
    "key_evidence": [
      {"id": "ev1", "claim": "The proposed estimator reduces bias by 41% versus the baseline.",
       "refs": ["fig:2", "tab:1"], "bullets": ["bias metric on held-out set", "n=120, five seeds"],
       "locator": {"page": 4, "section": "Results", "where": "Table 1 caption"}}
    ],
    "conclusion": {"claim": "Two-stage stratified re-weighting gives lower bias without losing coverage.",
                   "refs": ["fig:2"], "locator": {"page": 6, "section": "Discussion"}},
    "limitations": [{"claim": "Assumes C is observed; unobserved confounders remain open.",
                     "locator": {"page": 6, "section": "Discussion"}}]
  },
  "evidence_index": [
    {"id": "fig:2", "kind": "figure", "role": "data", "owner": "paper", "label": "Figure 2",
     "caption": "Bias vs. baseline across five seeds (box plot).",
     "locator": {"page": 4, "section": "Results", "where": "Figure 2"},
     "data_points": [{"value": "41", "unit": "%", "condition": "n=120, five seeds",
                      "locator": {"page": 4, "where": "Figure 2 y-axis"}}]}
  ]
}
```

EXAMPLE — 运行：

```bash
python3 src/ppt_outline.py build paper_skeleton.json --out slide_outline.json --limit 10
```

EXAMPLE — 示意输出 `slide_outline.json`（截取一个证据页）：

```json
{
  "index": 5,
  "role": "evidence",
  "claim": "The proposed estimator reduces bias by 41% versus the baseline.",
  "bullets": ["bias metric on held-out set", "n=120, five seeds"],
  "evidence": [
    {"ref": "fig:2", "use": "data", "label": "Figure 2",
     "locator": {"page": 4, "section": "Results", "where": "Figure 2"}}
  ],
  "data_verbatim": [
    {"ref": "fig:2", "value": "41", "unit": "%", "condition": "n=120, five seeds",
     "locator": {"page": 4, "where": "Figure 2 y-axis"}}
  ],
  "notes": "Lead with the number the figure shows. State the condition before the number.",
  "claim_locator": {"page": 4, "section": "Results", "where": "Table 1 caption"}
}
```

EXAMPLE — `slide_outline.json.contract`（示意）：

```json
{
  "slide_limit": 10,
  "slide_count": 9,
  "checks": {
    "one_claim_per_page": true,
    "all_refs_located": true,
    "no_schematic_as_data": true,
    "no_other_attribution": true,
    "data_verbatim_ok": true,
    "notes_non_verbatim": true,
    "coverage_complete": true,
    "narrative_order_ok": true,
    "count_within_limit": true
  },
  "errors": [],
  "warnings": []
}
```

EXAMPLE — 解释：证据页只承载一条主张（`claim`），bullet 是支撑短语；`fig:2` 的编号与
`data_verbatim` 的 `41`/`%` 逐字保留并带 locator；备注不含页面文字逐字片段。以上仅说明接口。
