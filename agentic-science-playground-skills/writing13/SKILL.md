---
name: latex-writer-builder
description: >
  LaTeX 学术写作、迁移与编译修复技能。触发词：LaTeX、.tex、.bib、公式、表格、
  交叉引用、参考文献、模板、期刊/会议/学位论文模板、编译、编译错误、pdflatex、
  xelatex、lualatex、latexmk、bibtex、biber、排版、可复现构建、reproducibility、
  compile、cross-reference、bibliography。任务要求“编译得通/改得对/交得可用/复现得了”
  之一即触发。用于：把事实底稿写成或改写成可编译的 LaTeX 源码，按指定模板与 TeX
  发行版编译通过，定位每个错误到 文件:行号:根因，校验公式/表格/引用/文献/模板必填项，
  交付可编辑源码 + 编译日志 + PDF/PNG 预览，并记录可复现的构建环境。
  何时不触发：纯文本改写且明确禁止使用 LaTeX；输入只有 PDF 且任务不要求转写为 TeX；
  无任何编译/排版/引用/公式/表格需求。
---

# LaTeX 写作与编译（writing13）

## 1. 用途

把「科研材料 + 写作任务」变成**能按指定模板编译通过、可继续编辑、可被他人复现**的
LaTeX 成果。核心闭环是：

> 勘察工程 → 分类编译错误并修复根因 → 跑编译循环直至收敛 → 校验内容与模板 → 记录
> 构建环境与精确命令 → 交付源码 + 日志 + 预览 + 结构化结果。

本技能围绕题面四个问题逐条兑现：**编译得通、改得对、交得可用、复现得了**。

## 2. 适用 / 不适用条件

适用：迁移到模板、修复编译错误、写/改公式、表格、交叉引用、参考文献、双语/结构化
LaTeX 稿件；任何“把文字变成可编译 .tex 并交付预览”的任务。

不适用（直接按普通文本任务处理，不跑编译循环）：任务明示“不要 LaTeX”；输入只有
PDF 且不要求转写 TeX；没有公式/表格/引用/模板/编译要求。

## 3. 输入契约

运行时原始输入固定为 `/input/case.json` 与 `/input/task.md`；素材按题面给出（可能
含 `.tex`、`.bib`、`.cls/.sty/.bst` 模板、Word/文本底稿、PDF）。开工第一件事：

1. 读 `/input/case.json` 与 `/input/task.md` 原文，不要凭标签猜内容。
2. 从题面/`case.json` 抄出 `output_contract` 的**全部字段名**（若没有，用 §7 的标准
   契约）。`case_id` 从 `case.json` 取。
3. 列出全部输入文件与路径；把 PDF/图片先经平台 `pdf-text-tool`/`ocr-tool` 提取文字，
   **不要**把 PDF 当成源码内容。
4. 工作目录 `/app/work`（不存在就 `mkdir -p`）；最终产物与可编辑文件放 `/app/output`。

本技能自带资源（相对本 SKILL.md 所在目录，运行时通常在 `/skills/weekly-skill/`）：
`src/build.py`（编译循环 + 日志分类 + 收敛报告）、`schema/latex_schema.json`（构建记录
schema）、`checks/latex_checklist.md`（验收清单）。开工先 `ls` 确认这些路径；找不到时
用正文流程手工等效执行（流程不依赖脚本也能做）。

## 4. 分步操作流程（按顺序执行，每步可复现）

### 步骤 0 — 定位本技能资源

```bash
SKILL_DIR=$(dirname "$(find / -name 'SKILL.md' -path '*latex*' 2>/dev/null | head -1)")
ls "$SKILL_DIR/src" "$SKILL_DIR/schema" "$SKILL_DIR/checks"
```

`SKILL_DIR` 无法定位时继续用正文命令手工执行；脚本只是加速器。

### 步骤 1 — 勘察工程结构（写一张 inventory 清单）

在 `/app/work` 内执行并记录：

1. 列文件：`find . -type f | sort`，识别 `*.tex *.bib *.cls *.sty *.bst *.pdf *.docx`。
2. 找主文件：`grep -n '\\\\documentclass' ./*.tex`。主文件 = 含 `\documentclass`
   且不被其他文件 `\input`/`\include` 的文件；子文件 = 只含 `\begin{document}` 之后
   片段的 `.tex`。
3. 读主文件导言区（`\documentclass` 到 `\begin{document}` 之间），列出：
   - 文档类及选项：`\documentclass[options]{class}`
   - 宏包及选项：所有 `\usepackage[...]{...}`（注意加载顺序）
   - 字体/引擎线索：`fontspec`/`xeCJK`/`ctex`/`unicode-math` ⇒ 需 xelatex/lualatex；
     仅 `CJK` 或 GBK 编码 ⇒ 需兼容处理。
   - 文献：`\bibliographystyle{...}`、`\bibliography{...}`、`\usepackage[...]{biblatex}`
   - 模板必填占位：`\title`、`\author`、`\date`、摘要、关键词、页眉页脚命令。
4. 找 `.bib`：`grep -n 'bibliography{' ./*.tex` 里的名字对应的文件是否存在；
   记录 `.bib` 条目数与键（`grep -n '^@' *.bib`）。
5. 找模板类文件：`kpsewhich <类名>.cls`（系统版本）与项目目录内的同名 `.cls`；
   记下二者路径与版本（版本从 `.log` 的 `Document Class:` 行或 `.cls` 头部注释读）。
6. 把以上写成 `/app/work/inventory.md`（项目结构 + 主文件 + 导言区清单 + bib + 模板
   版本）。这一步是后续“改得对”“复现得了”的证据底座。

### 步骤 2 — 建立基线：先编译一次，拿到全部错误

```bash
cd /app/work
python3 "$SKILL_DIR/src/build.py" --workdir . --main <主文件> --report build_report.json
echo "exit=$?"
```

- `build.py` 只调用 `pdflatex/xelatex/lualatex`、`bibtex/biber`、`latexmk`，输出
  `build_report.json`（结构见 `schema/latex_schema.json`）并打印到 stdout。
- 引擎选择：默认 `pdflatex`；检测到 `fontspec`/`xeCJK`/`ctex` 改 `--engine xelatex`
  （或 `lualatex`）；模板 README 有明确引擎要求时以模板为准。
- 读 `build_report.json` 的 `errors[]`：**不要只看第一条**。按 `category` 分组，按
  §5 决策树的优先级确定修复顺序。

### 步骤 3 — 按决策树分类并修复根因（循环：修一批 → 重跑 → 再取下一批）

修复原则：
- **先修根因、后看级联**。`EMERGENCY_STOP`、`FILE_ENDED_SCANNING`、`RUNAWAY_ARGUMENT`
  几乎总是前面某个错误的后果；前面根因修掉后它们自动消失。
- **每次只改一批同一根因的错误**，改完立即重跑 `build.py`，用新报告的
  `error_count`/`errors[]` 判断是否推进，避免一次改多处导致无法归因。
- 每处修改在源码里加注释 `% [fix] <category> <原因>`；同时在
  `/app/work/fix_log.md` 记 `文件:行: 改前 → 改后 → 原因`（这是 result.json 的
  `changes` 与 `errors_fixed` 来源）。

决策树（`category` → 动作）见 **§5 领域规则**，异常（缺类文件/缺宏包/缺字体/权限/
缺 bib/模板不兼容）见 **§8 异常矩阵**。

### 步骤 4 — 跑编译循环并收敛

`build.py` 已实现循环：引擎遍 →（需要时）`bibtex` → 再引擎遍，直到
`.aux/.toc/.lof/.lot/.bbl/.out` 相邻两遍 md5 全相同、日志无 `Rerun to get ...`、
且无未定义/重复引用。判据写在报告字段：

- `converged == true` 且 `error_count == 0` 且 `broken_reference_count == 0` ⇒ 通过。
- 未收敛：看 `errors[]` 与 `warnings[]` 继续修，重跑。
- 无 `latexmk` 需求时用 `--latexmk` 也可以（latexmk 自定轮次），但**最终记录仍以
  显式命令列表为准**（`reproducibility.exact_commands`）。

若没有 `build.py`，手工等价序列（记入 reproducibility）：

```bash
pdflatex -interaction=nonstopmode -file-line-error -recorder main.tex
bibtex main            # 仅当存在 \bibliography / \cite 时
pdflatex -interaction=nonstopmode -file-line-error -recorder main.tex
pdflatex -interaction=nonstopmode -file-line-error -recorder main.tex
```

收敛判据：末遍日志无 `Rerun to get ...`，且 `grep -c '^!' main.log` 与
`grep -c 'LaTeX Error' main.log` 均为 0。

### 步骤 5 — 内容与模板校验（改得对）

逐项对照源材料，用命令取证，不回看源码“以为对”：

1. **公式**：`grep -n '\\\\label{eq:' *.tex` 得公式标签；`grep -n '\\\\ref\|\\\\eqref' *.tex`
   得引用；逐对核 key 唯一、编号与正文叙述一致、符号/上下标/单位与底稿一致。
2. **表格**：`grep -n 'begin{tabular' *.tex` 逐表核对「列格式数 == 每行单元格数」；
   用 `pdf-text-tool` 提取渲染后的表格数字与源材料逐格比对（数字必须能回溯到来源）。
   宽表不得用 `\resizebox/\scalebox` 掩盖，改用 `tabularx`/`longtable`/`p{宽}`。
3. **交叉引用**：每个 `\ref` 的 key 有且仅有一个 `\label`；`\autoref/\cref` 目标类型
   正确；最终 `build_report.json` 的 `broken_reference_count == 0`。
4. **文献**：每个 `\cite` key 在 `.bib` 有唯一条目；被引条目作者/年份/标题与源材料
   一致；`\bibliographystyle` 与模板匹配；biber 项目用 `--bib biber`。
5. **模板必填项**：按模板 README 逐项打勾（标题/作者/机构/邮箱/日期/摘要/关键词/
   图表题注/参考文献样式/页码格式）。缺失但材料可提供的补上；材料没有的标
   `uncertainty`，不编造。
6. **干净重建**：`rm -f *.aux *.toc *.lof *.lot *.bbl *.out *.fls *.fdb_latexmk` 后重跑
   `build.py`，必须再次 `converged == true`（证明不依赖上次残留）。

### 步骤 6 — 记录构建环境（复现得了）

`build.py` 已自动写入 `distro`、`engine`、`engine_version`、`packages[]`（名/日期/版本，
来自日志 `Package: ...`）、`fonts[]`、`commands[]`、`passes[]`。补记：

1. 模板版本：`grep -n 'Document Class:' main.log`（类名/日期/版本）。
2. latexmk 版本：`latexmk --version | head -1`（用了才记）。
3. 把「模板名+版本、宏包/字体版本、精确命令、轮次、任何替换」合并写入
   `build_record.json`，并用 `schema/latex_schema.json` 校验
   （`python3 -c "import jsonschema,json; jsonschema.validate(json.load(open('build_record.json')), json.load(open('$SKILL_DIR/schema/latex_schema.json')))"`；
   无 jsonschema 时至少 `json.load` 验证可解析）。

### 步骤 7 — 交付（交得可用）

在 `/app/output` 落盘：

1. **可编辑源码**：主 `.tex` + 全部子 `.tex` + `.bib` + 项目内 `.cls/.sty/.bst`（如用）。
   这是主产物；PDF 只是预览。
2. **编译日志**：`jobname.log`（保留完整日志，供复核定位）。
3. **构建记录**：`build_record.json`（含 `errors_fixed[]`、`reproducibility`）。
4. **预览**：渲染出的 `jobname.pdf`；再用 `pdf-render-tool`（或 `pdftoppm -png -r 150`
   首页）生成 `preview/jobname-p1.png`，便于人工快速核验。
5. **`result.json`**：见 §7 输出契约。

### 步骤 8 — 写 result.json 并自查

按 §7 逐字段写 `/app/output/result.json`；再跑 `checks/latex_checklist.md` 逐项打勾，
任何 `[!]` 项写进 `limits`。最后确认 `case_id` 与 `output_contract` 字段齐全。

## 5. 领域规则

### 5.1 编译错误决策树（category → 根因 → 修法 → 验证）

| category | 常见根因 | 具体动作 | 验证 |
|---|---|---|---|
| `MISSING_CLASS` | 模板 `.cls` 不在项目/系统 | 见 §8-缺类文件 | 重跑无该错误 |
| `MISSING_PACKAGE` | 宏包未安装或拼错 | 见 §8-缺宏包；先确认拼写（`kpsewhich x.sty`）再装/替换 | 重跑无该错误 |
| `MISSING_FONT` | 字体缺失（xelatex/fontspec 常见） | 见 §8-缺字体 | 重跑无该错误 |
| `UNDEFINED_CONTROL_SEQUENCE` | 宏拼写错 / 缺包 / 引擎错 | 1) `grep` 该宏定义处；2) 查它属于哪个宏包并确认已 `\usepackage`；3) 纯拼写错就改正；4) `\frac`→`\dfrac` 需 amsmath | 重跑无该错误 |
| `BAD_MATH` | `$`/`\(`/`\right`/上下标不配对 | 定位到行，读上下文配平 `$...$`、`\left...\right`、`^`/`_` 只带一个 token | 重跑无该错误 |
| `RUNAWAY_ARGUMENT` / `FILE_ENDED_SCANNING` | 花括号/环境不闭合（多为上游错误级联） | 先修同文件更早的根因；确认无上游后再查该行括号配对（可用编辑器括号匹配） | 重跑无该错误 |
| `TABLE_OVERFLOW` | 列太宽/维度爆炸 | 改列宽 `p{}`/`tabularx`/`longtable`；删掉 `\resizebox` 掩盖；核对列数与单元格数 | 日志无 `Overfull \hbox` 于该表处 |
| `UNDEFINED_REFERENCE` | `\label` 缺失或未到收敛遍 | 确认目标 `\label{...}` 存在且唯一；多遍后仍 undefined 才是真缺 label，补上 | `broken_reference_count==0` |
| `UNDEFINED_CITATION` | `.bib` 缺条目 / bibtex 未跑 / key 拼错 | `grep '@.*{<key>' *.bib`；缺条目见 §8-缺 bib | `broken_reference_count==0` |
| `MULTIPLY_DEFINED_LABEL` | 同名 `\label` 两处 | 改名一处并同步所有 `\ref` | 重跑无该警告 |
| `CAPACITY_EXCEEDED` | 结构过深/过长 | 拆分过深嵌套、长段落或超大表 | 重跑无该错误 |
| `EMERGENCY_STOP` | 前序错误级联 | **永远不单独修它**；找 `errors[]` 里比它更早/更上层的根因 | 根因修复后自动消失 |
| `OTHER` | 未分类 | 原文摘录报错，查 `.log` 上下文 5 行，人工归类 | 记录归类结论 |

### 5.2 修复顺序（优先级从高到低）

1. `MISSING_CLASS` / `MISSING_PACKAGE` / `MISSING_FONT`（阻塞一切）
2. `UNDEFINED_CONTROL_SEQUENCE`
3. `RUNAWAY_ARGUMENT` / `FILE_ENDED_SCANNING` / `BAD_MATH`（语法）
4. `TABLE_OVERFLOW` / `CAPACITY_EXCEEDED`
5. `UNDEFINED_REFERENCE` / `UNDEFINED_CITATION` / `MULTIPLY_DEFINED_LABEL`（先靠多遍收敛，再补标签/条目）
6. `OVERFULL/UNDERFULL`（只修表格与断行的明显溢出，不逐条追逐全文 overfull）

### 5.3 常见模板的引擎/文献/必填速查（无此类模板时跳过）

| 模板 | 引擎 | 文献 | 必填注意 |
|---|---|---|---|
| IEEEtran | pdflatex | `IEEEtran` + `IEEEtran.bst` | `\thanks` 作者脚注、作者 block 顺序、`\IEEEauthorblockN/A` |
| elsarticle | pdflatex | `elsarticle-num` 等 | `\author[aff]{...}`、`\ead{}` 邮箱、`\begin{abstract}`、`\begin{keyword}` |
| revtex4-2 | pdflatex | `apsrev` 或 biblatex | `\affiliation`、`\date{\today}`、`\begin{abstract}` |
| acmart | pdflatex | `ACM-Reference-Format` | `\author` 须配 `\affiliation`+`\email`，`\keywords`、`\begin{CCSXML}` |
| 学位论文（自建 cls） | 以 README 为准 | 以模板为准 | 封面字段、承诺书、目录、摘要关键词 |

模板 README 与 `.cls` 注释是必读项；README 与本表冲突时以 README 为准。

### 5.4 事实与来源一致性（写作红线）

- 任何数字、术语、引用、图表、论断必须能在输入材料里回溯（记文件+位置/页码）。
- 不新增材料外事实；材料不足写 `uncertainty`，冲突写两者并标注，缺项写 `limits`。
- 改写只改表达与排版，不改数值、作者、年份、结论。

## 6. 输出契约

`/app/output/result.json` 必含（JSON，UTF-8）：

```json
{
  "case_id": "<case.json 里的 id>",
  "status": "ok | partial | failed",
  "output_contract": { "<题面声明的全部字段，原样补齐>" },
  "main_result": {
    "deliverables": ["main.tex", "sections/intro.tex", "refs.bib", "template.cls"],
    "main_tex": "main.tex",
    "pdf_preview": "main.pdf",
    "png_preview": "preview/main-p1.png"
  },
  "build": {
    "build_record": "build_record.json",
    "converged": true,
    "error_count": 0,
    "broken_reference_count": 0
  },
  "sources": [{"claim": "关键数字/结论", "source": "输入文件路径", "location": "章节/行/页码"}],
  "changes": [{"file": "main.tex", "line": 12, "before": "...", "after": "...", "reason": "..."}],
  "uncertainty": ["无法确认/材料不足项"],
  "limits": ["边界与未完成项"]
}
```

- 若 `case.json`/`task.md` 声明了 `output_contract`，**原样复制其字段**并填值，不得
  自创或改名；上面 `main_result/build/sources/changes/uncertainty/limits` 是补充证据
  字段，始终保留。
- `status`：全部通过=ok；有可交付但存在缺口=partial；无法编译/无法完成=failed（
  `limits` 必须说明原因）。

## 7. 证据 / 来源定位规则

- 编译证据：`jobname.log` + `build_report.json`（`errors[]` 的 `file:line:category`）。
- 内容证据：每个数字/引用用「源文件 + 位置」登记到 `sources[]`；公式/表格改动登记到
  `changes[]`，且源码留 `% [fix]` 注释。
- 复现证据：`build_record.json` 的 `distro/engine/packages/fonts/commands/passes` 与
  `reproducibility_notes`。
- 引用与标签：一律 `grep` 源码取证（`\label/\ref/\cite/\bibliography`），不凭记忆。
- 不得把「我改好了」当证据；每项证据都要有可复核的文件或命令输出。

## 8. 不确定性与异常处理

### 8.1 异常矩阵

| 异常 | 处置 | 交付时标注 |
|---|---|---|
| 缺类文件 `.cls` | 1) `kpsewhich <x>.cls` 系统是否有；2) 项目内找同名文件；3) 都没有：若题面允许替换，用最接近的已装模板（如 IEEEtran/elsarticle/article）并把替换写进 `reproducibility_notes`；若不允许替换，`status=failed/partial`，交付「已完成内容 + 缺口说明」。**不得伪造类文件** | `limits` + `reproducibility_notes` |
| 缺宏包 `.sty` | 1) 确认拼写；2) `kpsewhich` 是否已装；3) `tlmgr install <pkg>`（需网络+权限，无权限则跳过）；4) 用等价宏包替换（如 `subfig`↔`subcaption`、`epsfig`↔`graphicx`）并记录替换；5) 改不动就标 partial | `changes` + `reproducibility_notes` |
| 缺字体 | `font-discovery` 或 `fc-list` 查可用字体；xelatex/fontspec 项目把 `\setmainfont` 指到可用字体并记录映射；pdflatex 的 Type1 字体缺了先看是否装对应宏包（如 `mathptmx` 装 times） | `reproducibility_notes` |
| 权限不足（读/写） | 不 `chmod` 系统目录；把工程复制到可写的 `/app/work` 再操作；产物写 `/app/output`；源文件只读则复制后编辑副本并注明 | `limits` |
| 报错级联 | 识别：`EMERGENCY_STOP`/`FILE_ENDED_SCANNING` 跟在真实根因之后；修根因→重跑→级联自动消失；不要把级联当独立错误逐条修 | `errors_fixed`（按根因一条记录） |
| 缺 `.bib` | 材料含参考文献元数据 → 据其**合成** `.bib` 条目并在每条 `% [fix] synthesized from <源>` 标注；材料没有且必须引用 → `uncertainty` + 尽量从公开 DOI/标题检索补全（检索结果需真实，DOI 不可编造）；确实补不齐 → partial | `uncertainty` + `.bib` 注释 |
| 模板不兼容（引擎/编码） | 1) 查模板 README 引擎要求；2) `fontspec/xeCJK/ctex/unicode-math` ⇒ 换 xelatex/lualatex；3) GBK 源码先 `iconv -f GBK -t UTF-8` 转码；4) 模板版本与稿件结构不匹配时记录差异并适配（迁移必填项） | `build` + `reproducibility_notes` |
| 输出目录不存在/只读 | `mkdir -p /app/output`；只读则写 `/app/work` 并在 result 里写真实路径 | `limits` |
| 引擎缺失 | `command -v pdflatex xelatex lualatex`；都没有 → `status=failed`，交付已完成源码与缺口 | `limits` |

### 8.2 不确定项原则

材料缺失、数值冲突、模板要求无法满足、检索不到真实来源 → 一律写 `uncertainty`/
`limits`，**不猜测、不编造、不静默省略**。可以交付的部分照常交付并标注边界。

## 9. 自查清单

逐项执行 `checks/latex_checklist.md`（四问 → 具体检查 + 验证命令）。快速核心五项：

1. `build.py` 退出码 0 且 `converged==true`、`error_count==0`、`broken_reference_count==0`。
2. `errors[]` 每条都有 `file:line:category`，且修复顺序遵循 §5.2 优先级。
3. 公式/表格/引用/文献/模板必填项均与源材料逐项对照过（有 `sources[]` 可回溯）。
4. 干净重建（删辅助文件重跑）仍 `converged==true`。
5. `result.json` 含 `case_id` + `output_contract` 全部字段 + `status/sources/changes/uncertainty/limits`。

## 10. 相比裸 Agent 的质量增益

| 裸 Agent 常见错误 | 本技能如何防止 |
|---|---|
| 只看第一条报错就修，级联错误残留 | `build.py` 一次给出全部 `errors[]` 且分类；§5.2 规定根因优先、级联最后 |
| 把 `Overfull hbox` 当致命错误反复折腾 | 分类为警告；只修表格/断行的实质溢出，不逐条追逐 |
| undefined ref/cite 当语法错误乱改源码 | 先靠多遍收敛判据判断，真缺 `\label`/`.bib` 条目才动手 |
| 交付 PDF/截图/孤片段当结果 | §7 明确主产物是可编辑源码，PDF/PNG 只是预览，片段必须写回完整工程 |
| 不记录模板/宏包/字体版本与命令，别人复现不了 | `build_record.json` + schema 强制记录 distro/engine/packages/fonts/commands/passes |
| 数字/引用凭记忆改，无法回溯 | `sources[]` + `% [fix]` 注释 + 每处改动入 `changes[]` |
| 缺宏包就卡死或瞎猜 | §8 异常矩阵给出 查拼写→kpsewhich→tlmgr→等价替换→标注 的完整阶梯 |
| 换引擎后旧字体/编码崩盘 | §4 步骤1 识别 fontspec/xeCJK/ctex 与 GBK，按引擎与编码适配 |

**公平自评方法**：同一工程、同一环境，对比「加载本技能」与「不加载」：
- 编译成功率 = 收敛构建数 / 总构建数；
- 修复正确率 = 首轮定位到根因（file:line:category 命中）的修复数 / 总修复数；
- 平均定位-修复轮次 = 从基线到 `converged==true` 的 `build.py` 调用次数。
三项都取同输入、同命令、同超时，结果写入 `result.json` 的 `limits`/附注（如平台要求）。
