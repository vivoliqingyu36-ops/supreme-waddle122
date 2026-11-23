# LaTeX 写作与编译 — 验收检查清单

每个案例交付前逐项打勾。四个问题（编译得通 / 改得对 / 交得可用 / 复现得了）与
检查项一一对应；每项都给出**可执行的验证命令或判据**，不做空泛检查。

记号：`[ ]` 未做，`[x]` 通过，`[-]` 不适用（必须写一句原因），`[!]` 未通过（必须进
异常矩阵并保留边界说明）。

---

## 问题一：编译得通（在指定模板与发行版下按预期轮次通过）

- [ ] 主文件唯一确定：`grep -n '\\\\documentclass' *.tex` 只命中一个主文件；其余
      文件都是被 `\input`/`\include` 引用的子文件或片段。
- [ ] 模板类文件存在：主文件里的 `\documentclass{...}` 对应的 `.cls` 能在项目目录
      或系统 `kpsewhich <name>.cls` 找到；找不到时已按异常矩阵处置。
- [ ] 运行 `python3 src/build.py --workdir <项目> --main <主文件>` 返回退出码 0，
      JSON 中 `converged == true`。
- [ ] `error_count == 0`：最终 `.log` 无 `! ...` / `LaTeX Error:` / `Emergency stop`
      行（`build_report.json` 的 `errors` 为空）。
- [ ] 每个历史错误都能定位：`errors[].file` 与 `errors[].line` 非空（`<main>` 与
      行号 0 只在引擎确实不报位置时允许），且 `category` 命中分类表而非全为 OTHER。
- [ ] 级联已回卷：修复顺序为「根因 → 重跑 → 再取下一个根因」，报告里不出现只修了
      第一条错误、后面错误原样残留的情况。
- [ ] `rerun_needed == false`：最终日志无 `Rerun to get cross-references right` /
      `Rerun to get citations correct`。
- [ ] 辅助文件已稳定：连续两次引擎遍之间 `.aux/.toc/.lof/.lot/.bbl/.out` 的 md5 全
      相同（`build_report.json` 的 `aux_snapshot` 与收敛记录佐证）。
- [ ] 引用/文献已收敛：`broken_reference_count == 0`（无未定义或重复定义标签）。

## 问题二：改得对（公式/表格/交叉引用/文献/模板必填项符合原文意图与模板）

- [ ] 公式符号一致：每个 `\label{eq:...}` 与正文 `\eqref`/`\ref` 一一对应，公式编号
      与引用文本中的编号一致；变量正斜体、上下标、单位与底稿一致（逐项对照源材料，
      不新增材料外符号）。
- [ ] 公式编号正确：`equation`/`align` 等环境的编号序列连续，`\tag{}`/`\nonumber`
      的使用与原文意图一致。
- [ ] 表格数值一致：把渲染出的表格与源材料逐格比对数字（用 `pdf-text-tool` 提取
      PDF 表格文本回读，而不是只看源码）。
- [ ] 表格列数与列宽：每个 `tabular`/`tabularx` 的列格式数 = 每行单元格数；无
      `Overfull \hbox` 于表格处；宽表用 `tabularx`/`longtable`/`p{}` 固定宽，不靠
      `\resizebox`/`\scalebox` 掩盖。
- [ ] 交叉引用正确：每个 `\ref`/`\eqref`/`\pageref` 的 key 在全文有且仅有一个
      `\label`；`\autoref`/`\cref` 的目标类型与文字一致。
- [ ] 文献引用正确：每个 `\cite`/`\citep`/`\citet` 的 key 在 `.bib` 有唯一条目；
      每个被引条目的作者/年份/标题与源材料一致；`\bibliographystyle` 与模板要求一致
      （如 IEEEtran → `IEEEtran`，elsarticle → `elsarticle-num` 等）。
- [ ] 模板必填项齐备：`\title`、`\author`、机构/邮箱、`\date`、摘要、关键词、
      `\begin{document}` 按模板 README 补齐；模板的 `\thanks`/作者脚注、页眉页脚、
      章节格式未缺项。
- [ ] 版式合规：页边距、字号、图表题注位置、三线表样式、参考文献排序由模板宏包
      决定，不手工 `\vspace`/`\hspace` 硬凑。

## 问题三：交得可用（交付可编辑、可维护源码，不是 PDF/截图/片段）

- [ ] 交付 `.tex` 主文件 + 全部子文件 + `.bib` + 项目内 `.cls/.sty/.bst`（若使用），
      全部为 UTF-8 文本；PDF/PNG 仅作为**预览**并列明。
- [ ] 不交付孤立片段：把改动写回完整工程（`\input` 的子文件都在），不出现一段
      无法独立编译的 `\begin{document}...\end{document}` 缺头的片段。
- [ ] 干净环境重编译通过：删除 `*.aux *.toc *.lof *.lot *.bbl *.out *.fls *.fdb_latexmk`
      后按记录命令重跑，退出码 0 且 `converged == true`（验证不依赖上次残留）。
- [ ] 源码可维护：无 `\input` 绝对路径；子文件边界清晰；修复处有 `% [fix] 原因`
      注释说明改了什么、为什么。
- [ ] 预览可见：PDF 能打开且页数合理；首页 PNG 用 `pdf-render-tool` 或 `pdftoppm`
      渲染，放在 `/app/output/preview/`，文件名与主文件同名。
- [ ] 结果 JSON 完整：`/app/output/result.json` 含 `case_id`、`output_contract`
      要求的全部字段、`status`、`build`（指向 build_record）、`sources`、`changes`、
      `uncertainty`、`limits`。

## 问题四：复现得了（他人按记录得到同一产物）

- [ ] 记录发行版与引擎：`build_record.json` 有 `distro`、`engine`、`engine_version`。
- [ ] 记录宏包与字体版本：从 `.log` 抽取的 `packages[]`（名称/日期/版本）与
      `fonts[]` 已写入；模板类版本单独记录（`template.name/version/date/source`）。
- [ ] 记录精确命令与轮次：`reproducibility.exact_commands[]` 与 `passes[]` 可逐条
      重放；手动多遍时写清 `pdflatex → bibtex → pdflatex → pdflatex` 的顺序。
- [ ] 干净重建一致性：删除辅助文件后重跑，PDF 的 md5 忽略 `/CreationDate`、
      `/ModDate`、`/ID` 后一致（日期/ID 是引擎每次写入的元数据，非内容差异）。
- [ ] 人工确认与替换已标：任何宏包/字体/模板替换（如缺宏包改用等价物）在
      `reproducibility_notes` 写明「替换了什么 → 用什么替代 → 对版式可能的影响」。
- [ ] 未解决项显式标注：无法编译、材料缺口、需人工确认的项写入 `uncertainty`/
      `limits`，不冒充已通过。

---

## 运行前自检（交包前在作者本地跑一遍）

```bash
# 1) 脚本语法与最小示例
python3 -m py_compile src/build.py
python3 src/build.py --workdir example --main main.tex   # 期望退出码 0

# 2) schema 与报告可解析
python3 - <<'PY'
import json
json.load(open('schema/latex_schema.json'))
json.load(open('example/build_report.json'))
print("ok")
PY

# 3) 全包仅 UTF-8 文本、无符号链接
find . -type f ! -name '*.pyc' -exec file {} + | grep -v -E 'UTF-8|ASCII|Python|JSON|text'
find . -type l   # 期望为空
```

凡打 `[!]` 的项，必须在 `result.json` 的 `limits` 里逐条保留边界说明，不得静默略过。
