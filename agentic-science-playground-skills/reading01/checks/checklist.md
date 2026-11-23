# 自查清单：文献 PDF 解析「四个问题」逐项核对

本清单是 SKILL.md 第 9 步的执行版。每条检查都要么通过、要么把失败点写进
`result.json` 的 `uncertainty[]`（带 `kind`/`page`/`block_id`），不要静默放过。
「比对原文」一律指比对 `pdf-render-tool` 渲染出的页面图像，而不是比对自己的提取结果。

---

## 问题一「提得全」——不漏行、不丢段、不混入页眉页脚

- [ ] 1.1 页数一致：`document.page_count` 与渲染图页数一致；每页都在 `body` 或 `tables/formulas/figures` 中有对应产物。
- [ ] 1.2 行数核对：对每页取渲染图，数出正文可见文本行；`result.json` 该页 `body` 块 `lines[]` 总行数与其一致（±允许误差时记录）。
- [ ] 1.3 题注齐全：每张图/表都有 `caption` 且逐字与渲染图题注一致；题目 `figure_id`/`table_id` 与 `caption_block_id` 一一对应。
- [ ] 1.4 脚注齐全：正文中的脚注标记（`1、*、†、‡、§`）在 `footnotes[]` 中都有对应条目；标记与脚注文本配对正确。
- [ ] 1.5 参考文献齐全：`references[]` 条数与原文参考文献区条目数一致；每条 `raw_text` 逐字（含标点、DOI 大小写）。
- [ ] 1.6 页眉页脚隔离：出现在 ≥2 页同一位置且文本重复的行（含期刊名、页码、running title）必须在 `headers_footers[]`，不得出现在 `body[].text` 中。
- [ ] 1.7 页码不被当正文：形如 `1`、`12`、`iv` 且位于页边 12% 内的行已归入 `headers_footers` 的 `page_number`。
- [ ] 1.8 首尾不截断：每页第一个和最后一个正文块与渲染图首/末正文行一致（抽查首尾各 3 页）。
- [ ] 1.9 空文本/乱码标记：提取为空的 span 或 `�` 替换字符已记录为 `unreadable`，未用近义字补写。

## 问题二「排得对」——多栏/跨栏/跨页顺序正确，不串栏不错行

- [ ] 2.1 列数正确：双栏页在 `per_page[].columns`（或脚本 `assemble` 输出）中为 2 列，单栏页为 1 列；列边界 x 与渲染图沟槽一致。
- [ ] 2.2 列优先顺序：任取一双栏页，左栏最后一段在阅读顺序上先于右栏第一段；`body[].order` 单调且无穿插。
- [ ] 2.3 不跨栏拼接：没有一行文本同时含左栏尾词与右栏首词（即相邻段落没被拼成一句）；`body[].text` 的换行保留原文换行。
- [ ] 2.4 通栏元素锚定：跨两栏的标题/大表/大公式被识别为 spanning，插入位置正确（在它上方的两栏内容之后、下方的两栏内容之前）。
- [ ] 2.5 跨页续段：上一页末句未完（无句末标点）且下一页首行无缩进时，检查是否为跨页续段；是则在两页块上都标 `continued`，不是则不改动。
- [ ] 2.6 边注不混入正文：页面侧边短注释已单独成块，不插入正文流。

## 问题三「拆得清」——章节/表格/公式结构还原

- [ ] 3.1 章节层级：`sections[]` 的 `level` 与原文编号层级一致；`parent_section_id` 正确；标题块 `role=heading` 且 `heading_block_ids` 指向标题块。
- [ ] 3.2 表格行列：每张 `table.n_rows × n_cols` 与渲染图可见行列一致（有合并单元格时按最大网格计）。
- [ ] 3.3 单元格归属：每个非空单元格 `cell_id`/`row`/`col` 唯一；`merged_cells` 的 owner 正确；无单元格错位到相邻行/列。
- [ ] 3.4 合并单元格：`rowspan`/`colspan` 与渲染图边框一致；推断出的合并都带 `uncertainty`（坐标外延是启发式）。
- [ ] 3.5 跨页续表：`continued_on` 指向下一页同一表的 `table_id`；表头重复出现时 `header_rows` 已标。
- [ ] 3.6 公式上下标：公式行 `text` 与渲染图逐字符一致；上下标若为 Unicode 上下标字符（`x²`、`aᵢ`）保留原字符，若为排版位移则记录 `superscript_note`。
- [ ] 3.7 希腊字母/特殊符号：公式与正文中的希腊字母、`± × ≤ ≥ ≈ ∑ ∫ ∂ √` 等保留原文 Unicode；`special_chars[]` 给出 LaTeX 等价。
- [ ] 3.8 公式编号：`equation_number` 与原文编号一致（如 `(3)`）；编号与公式块关联正确。

## 问题四「核得回」——可追溯、读不出如实标

- [ ] 4.1 块级证据：`body` 每个块都有 `page` + `block_id` + `bbox` + `span_ids`（或 `source`）。
- [ ] 4.2 表格证据：每张表都有 `page` + `bbox` + `evidence.block_ids/span_ids`。
- [ ] 4.3 公式/图证据：每条公式/图都有 `page` + `bbox`（或 `image_ref` 渲染裁剪）。
- [ ] 4.4 参考文献证据：每条引用有 `page` + `block_id`，能指回原文。
- [ ] 4.5 证据覆盖：`evidence.coverage.blocks_with_evidence == total_blocks`；缺失的块必须出现在 `unreadable[]` 或 `uncertainty[]`。
- [ ] 4.6 读不出诚实标注：模糊、被遮挡、乱码（`�`、字体失配）、无文本层且 OCR 置信度低的区域，全部标 `unreadable` 或 `heuristic_guess`，绝不用上下文猜测填字。
- [ ] 4.7 未报告/冲突：题面要求但原文未报告的内容标 `not_reported`；原文自相矛盾标 `conflict`，两处证据都要给出。
- [ ] 4.8 来源链：`result.json` 的 `tool_path` 记录实际用的抽取工具（pdf-text-tool / pdf-render-tool+ocr-tool / mixed）。

---

## 交付前最后 3 项

- [ ] `result.json` 含 `case_id` 与 `output_contract` 要求的全部字段；用本仓库 `schema/output_schema.json` 校验通过。
- [ ] 可编辑产物（Markdown/HTML/JSON）与渲染预览（PNG/PDF）都在 `/app/output`，预览页号与 `page` 字段一致。
- [ ] 重跑一遍 `src/pdf_parse.py` 得到相同 `block_id` 顺序与文本（幂等）；差异写进 `change_log`。
