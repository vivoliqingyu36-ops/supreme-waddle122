# 自查清单 — 论文转学术 PPT（六方向 → 具体检查）

每条检查都有「怎么查」和「不通过怎么标」。不通过项**必须**写入
`result.json.uncertainty[]`（带 `kind/detail/locator`），不得静默放过。
先跑机器检查，再跑人工抽查；两者结论都要留痕。

```bash
# 机器检查：契约校验（0 退出 = 契约成立，3 = 违约）
python3 /skills/weekly-skill/src/ppt_outline.py validate slide_outline.json --limit N
python3 /skills/weekly-skill/src/ppt_outline.py self-test   # 校验器自身可用
```

## 方向 1 — 论文主线提取（problem → method → evidence → conclusion）

- [ ] 1.1 `narrative_arc` 顺序 = title → problem → gap → method → evidence* → conclusion → limitations → (backup/thanks)，无倒置。
  - 查：`contract.checks.narrative_order_ok == true`；缺 `problem/method/conclusion` 即错。
- [ ] 1.2 结论页主张能回答问题页主张（不是摘要复读）。
  - 查：读 problem.claim 与 conclusion.claim 两句话，人工判断是否构成「问题→答案」；不构成 → `kind:ambiguous`。
- [ ] 1.3 主结论与支撑性细节分离：主结论只出现在 conclusion 页 claim；支撑细节在 evidence 页 bullets 或 backup 页。
  - 查：grep conclusion.claim 是否在其它页重复出现；出现即错。
- [ ] 1.4 每页 `claim_locator` 非空，且 page/section 能在原文定位。
  - 查：`python3 -c` 遍历 slides 检查 `claim_locator`；缺失 → 补或标 `not_reported`。

## 方向 2 — 页结构与信息分层（一页一主张、密度受控）

- [ ] 2.1 每页恰好一条 claim（`contract.checks.one_claim_per_page == true`）。
- [ ] 2.2 每页 bullets ≤ 6，每条 ≤120 字符，短语式（不以句号结尾）。
  - 查：validate 输出；句号结尾是 warning，仍建议改写为短语。
- [ ] 2.3 单页正文密度 ≤ 600 字符（claim+bullets），超了要拆页或删点。
  - 查：validate 的 density warning；仍超 → 拆页。
- [ ] 2.4 长段落已改写为可讲短语，而非「段落切行」：任何 bullet 不得含完整长句/分号堆叠。
  - 查：抽查 3 页 bullets，读出声是否 ≤ 5 秒可讲完；否则改写。

## 方向 3 — 图表引用与证据保留（编号/单位/条件/归属）

- [ ] 3.1 `contract.checks.all_refs_located == true`：每处图/表/公式/数据引用有 `ref` 且 ref 在 `evidence_index`，并有 locator。
- [ ] 3.2 `contract.checks.data_verbatim_ok == true`：数字与单位与 evidence_index 里 `data_points` 逐字一致；改过即错。
- [ ] 3.3 `contract.checks.no_schematic_as_data == true`：示意图（role=schematic/illustration）不得 use=data，不得当实验数据展示。
- [ ] 3.4 `contract.checks.no_other_attribution == true`：cited/other 结果只能 use=reference，且 notes 有「先前/他人/据文献」标注。
- [ ] 3.5 图上编号与正文引用一致：label 逐字等于证据索引 label（如 "Figure 2"），不重号、不指向不存在的图。
  - 查：validate 的 label 比对；再人工抽查 1–2 处原文引用。
- [ ] 3.6 单位与必要条件保留：每个 data_verbatim 有 unit 或 unit_absent=true，condition 记录 n/p/温度/方法变体。
  - 查：遍历 `data_verbatim`，unit 为 null 且无 unit_absent → 错。
- [ ] 3.7 证据覆盖完整：`contract.checks.coverage_complete == true`；evidence_index 每条要么 used 要么 status=unused + unused_reason。

## 方向 4 — 讲解逻辑与备注（过渡/强调/补充，不逐字重复）

- [ ] 4.1 `contract.checks.notes_non_verbatim == true`：notes 不含 claim/bullets 逐字文本（≥8 字符子串）。
- [ ] 4.2 每页（title/thanks 除外）notes 非空；title/thanks 页 notes 可空。
  - 查：validate 的 notes 缺失错误。
- [ ] 4.3 notes 说明三件事之一：与上页的过渡、本页要强调的数字/单位、被问时的 backup 证据。
  - 查：抽 3 页 notes 人工读；只复述页面内容即不通过。
- [ ] 4.4 引用他人结果的页，notes 必须含归属标记（先前/他人/据文献/prior work）。

## 方向 5 — 模板约束与版面适配（占位符/字号/配色/页脚）

- [ ] 5.1 每页 `layout.layout_name` 存在于模板可用 layouts 列表；`placeholder_map` 覆盖本页需要的占位符。
  - 查：用 python-pptx 读模板 layouts，逐页比对；缺占位符 → 换 layout 或合并内容。
- [ ] 5.2 标题、正文字号/字体/配色沿模板主题，未覆盖主题颜色与字体。
  - 查：生成后用 python-pptx 读每个 shape 的 font.name/size/color，与主题对比。
- [ ] 5.3 页脚规则遵守：会议名/页码/单位名按模板页脚填，无越界。
  - 查：读 slide master 的 footer placeholder，逐页核对。
- [ ] 5.4 无溢出：长标题已截断/换行；多图并排不超画布；大表已节选/分栏，无文本出框。
  - 查：渲染 PDF/PNG 逐页目测，重点看标题与表格页；发现溢出 → 改 overflow_plan 后重渲。
- [ ] 5.5 单页字符/子弹不超模板约束（title_max_chars / body_max_chars / body_max_bullets）。
  - 查：与 template_spec.constraints 对照。

## 方向 6 — 导出渲染与可编辑性（字体/图形/项目符号不崩、可复核复跑）

- [ ] 6.1 交付可编辑源文件（.pptx）且每页可独立编辑（不是整页一张图）。
  - 查：python-pptx 能列出每页 shape 数量与文本；全图页 → 标 `kind:heuristic_guess`。
- [ ] 6.2 交付真实渲染预览：PDF（整份）+ 至少首页/结果页/表格页的 PNG。
  - 查：`ls /app/output`，文件存在且非空；文件名含 page 编号。
- [ ] 6.3 导出后字体/图形/项目符号不崩：PDF 文本可选（非图片化）、bullet 符号保留、图形未丢。
  - 查：pdftotext 或 pdf-text-tool 抽 PDF 文本比对；渲染 PNG 目测 bullet/图。
- [ ] 6.4 换机可复现：`versions` 记录 template_file、template_sha256、fonts、software（python-pptx/LibreOffice/字体名与版本）、skill_version。
  - 查：`result.json.versions` 字段齐；缺模板哈希 → 现算 `sha256sum template.pptx`。
- [ ] 6.5 重跑幂等：同输入、同模板、同 limit 重跑，页序/claim/refs 一致；有差异写 `change_log` 说明。
  - 查：跑两次 `build`，`diff` 两份 outline（忽略时间戳字段）。

## 通用

- [ ] 7.1 `result.json` 含 `case_id` + 题目 `output_contract` 全部字段。
- [ ] 7.2 `status` 如实：全成功 `success`；部分页失败 `partial`（limits[] 写页码与原因）；整体失败 `failed`。
- [ ] 7.3 缺失/不确定/冲突已标 `uncertainty[]`，未编造数字、单位、图表编号、结论。
