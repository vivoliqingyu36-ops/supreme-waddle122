# 阅读01｜文献文档解析 — Skill 包

把科研 PDF 解析成**可复核的结构化结果**：正文逐字提取（不漏行/不混入页眉页脚）、
多栏阅读顺序还原（不串栏/不错行）、章节与表格结构与公式符号重建（拆得清）、
每个块都能指回原文页码+区块（核得回）。

本包是「运行期 Agent 的指导书 + 一组真实可用的后处理资源」。平台运行时把它安装到
`/skills/weekly-skill`，再由 DeepSeek Harness 在 3 个固定科研案例上执行。
本包**不含任何预置答案或正式测试输出**，只给可泛化流程与工具。

## 目录结构

```
reading01/
├── SKILL.md                    # 运行期主指令（YAML frontmatter + 分步流程 + 异常矩阵 + 自查）
├── README.md                   # 本文件
├── src/pdf_parse.py            # 纯标准库 Python 后处理：行块组装/多栏重排/表格重建/证据ID
├── schema/output_schema.json   # result.json 的结构契约（字段+证据+uncertainty）
├── schema/span_schema.json     # src/pdf_parse.py 的输入契约（span 坐标格式）
└── checks/checklist.md         # 四个问题的逐项核对清单
```

## 方法说明

核心思路：**不重复造 PDF 二进制解析器，而是「抽取 → 归一化 → 版面判定 → 结构重建 → 证据回写」**。

1. **抽数**：优先 `pdf-text-tool` 拿文本层（含坐标）；无文本层/扫描件走
   `pdf-render-tool` 渲染页面 + `ocr-tool` 识别，产出同样的 span 列表。
2. **归一化**：把工具输出归一化为 `schema/span_schema.json` 的 span 格式
   （`{page, x0,y0,x1,y1, text, size, font}`）。
3. **版面判定与重排**（`src/pdf_parse.py assemble`）：
   - 纵向投影 + 逐水平条带内部沟槽投票 → 判定列带；缩进/通栏标题不会误判成栏；
   - 每个列带独立按 y 聚合行（**防止左右栏同行 y 合并**）；
   - 通栏元素作为「锚点」切分页面，锚点之间的内容按（列, y, x）排阅读顺序；
   - 每页输出 `blocks[]`（含 `block_id`、`bbox`、`lines[]`、`reading_order`）。
4. **表格重建**（`src/pdf_parse.py table`）：给定区域内的 span 用 x0/y0 聚类成网格，
   由 `x1/y1` 外推 `colspan/rowspan` 与 `merged_into` 归属；空而未解释的格标 `uncertainty`。
5. **公式/特殊字符**：识别数学/希腊字形行，保留 Unicode 原文并附 LaTeX 等价
   （`GREEK_MAP`），不确定处标 `heuristic_guess`。
6. **证据回写**：所有产物带 `page + block_id + bbox + span_ids + source`，按
   `schema/output_schema.json` 写入 `/app/output/result.json`。

## 调用方式（运行期 Agent 视角）

```bash
# 1) 先把抽取工具的 span 输出归一化成 schema/span_schema.json
python3 /skills/weekly-skill/src/pdf_parse.py assemble spans.json --out blocks.json

# 2) 表格单独重建（region 为 x0,y0,x1,y1，单位 pt；由渲染图目测或表格候选给出）
python3 /skills/weekly-skill/src/pdf_parse.py table spans.json --page 3 --region 60,180,500,600 --out table3.json

# 3) 自检核心函数（不写文件）
python3 /skills/weekly-skill/src/pdf_parse.py self-test

# 4) 生成一份合成演示输入，看接口长什么样
python3 /skills/weekly-skill/src/pdf_parse.py demo --out demo_spans.json
```

> 注意：`pdf_parse.py` 是**后处理器**，不直接解析 PDF 二进制、也不做 OCR；
> 它的输入是带坐标的 span 列表。文本层抽取用平台的 `pdf-text-tool`，
> 扫描件用 `pdf-render-tool` + `ocr-tool`（详见 SKILL.md 第 4 步）。

## 适用范围与限制

**适用**
- 有文本层或可 OCR 的科研论文/综述 PDF（单栏、双栏、多栏；含表格、公式、参考文献）。
- 需要「逐字 + 可复核 + 阅读顺序正确」的下游任务：翻译、问答、知识提取、复现。

**限制（诚实声明）**
- `pdf_parse.py` 的列带判定与合并单元格推断是**启发式**：极端错位、旋转页（未归一化
  rotate）、任意重叠文本框、竖排文本可能出错；出错处写入 `uncertainty`。
- 无坐标的纯文本走 `--from-text` 退化路径（每行一个全宽 span），只能得到单栏行序，
  **不能**还原多栏。
- 公式的 LaTeX 还原是「字符保真 + 提示」，不是完整 LaTeX 重排版；上下标若由排版位移
  实现，需结合渲染图人工确认。
- 加密 PDF、无文本层且 OCR 质量过低、字体 ToUnicode 缺失导致乱码等，按 SKILL.md
  异常矩阵处置并如实标注，不猜补。

## 失败处理

- 任何抽取工具失败 → 降级到下一工具路径（text → render+ocr → 仅 render 供人工）。
- 解析只有部分页成功 → `status=partial`，`limits[]` 写明失败页与原因。
- 重复运行应幂等：相同 `block_id` 顺序、相同文本；有差异写 `change_log`。

## 自查方法

1. 跑 `python3 src/pdf_parse.py self-test`，确认核心逻辑可用。
2. 逐项执行 `checks/checklist.md`（四个问题 → 具体检查 → 失败写 uncertainty）。
3. 用 `schema/output_schema.json` 校验 `result.json` 必填字段。
4. 渲染页面图像与 `result.json` 的 `page/bbox` 对照抽查（首/中/末页 + 每张表）。

## 最小示例（EXAMPLE）

以下输入/输出均为**合成演示**，不是正式案例结果。

EXAMPLE — 输入 `spans.json`（截取，完整用 `pdf_parse.py demo` 生成）：

```json
{
  "source": "demo.pdf",
  "unit": "pt",
  "origin": "top-left",
  "pages": [{
    "page": 1,
    "width": 612.0,
    "height": 792.0,
    "spans": [
      {"text": "A Two-Column", "x0": 70, "y0": 60, "x1": 200, "y1": 75, "size": 18},
      {"text": "Left paragraph line 0", "x0": 60, "y0": 100, "x1": 230, "y1": 110, "size": 10},
      {"text": "Right column line 0", "x0": 320, "y0": 99, "x1": 470, "y1": 109, "size": 10}
    ]
  }]
}
```

EXAMPLE — 运行：

```bash
python3 src/pdf_parse.py assemble spans.json --out blocks.json
```

EXAMPLE — 示意输出（截取，`blocks.json`）：

```json
{
  "source": "demo.pdf",
  "per_page": [{
    "page": 1,
    "columns": [
      {"index": 0, "x0": 0.0, "x1": 275.0},
      {"index": 1, "x0": 275.0, "x1": 612.0}
    ],
    "blocks": [
      {"block_id": "p1-b00", "page": 1, "order": 0, "role": "heading",
       "text": "A Two-Column", "bbox": {"page": 1, "x0": 70, "y0": 60, "x1": 200, "y1": 75},
       "confidence": "high", "uncertainty": []},
      {"block_id": "p1-b01", "page": 1, "order": 1, "role": "body",
       "text": "Left paragraph line 0",
       "bbox": {"page": 1, "x0": 60, "y0": 100, "x1": 230, "y1": 110},
       "confidence": "high", "uncertainty": []}
    ]
  }]
}
```

EXAMPLE — 示意解释：双栏页被判定为 2 列（`columns`），左栏内容（`order:1`）排在右栏
内容之前；每个块带 `block_id` 与 `bbox` 可回原文。`R1C1` 等表格单元格用
`python3 src/pdf_parse.py table spans.json --page 1 --region ...` 单独重建为网格。

以上示意输出仅说明接口，**不冒充正式案例结果**。
